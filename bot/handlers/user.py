# Обработчики команд для обычных пользователей: /start, /pay, /status, /support
import logging
from datetime import datetime, timedelta
from html import escape
from typing import Optional
from urllib.parse import quote

import gspread
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from stripe import StripeClient

import asyncio

from bot.keyboards import (
    get_language_level_keyboard,
    get_tariff_keyboard,
    get_payment_link_keyboard,
    get_pending_curator_keyboard,
    get_pending_manager_keyboard,
    get_subscription_manage_keyboard,
    get_welcome_keyboard,
    get_calendar_keyboard,
    get_rsvp_only_decline_keyboard,
    get_rsvp_only_attend_keyboard,
    get_main_menu_keyboard,
    get_schedule_keyboard,
    get_main_reply_keyboard,
    get_event_navigation_keyboard,
)
from bot.texts import (
    ACTIVE_GROUP_JOIN_YES,
    ACTIVE_GROUP_JOIN_NO,
    NEW_WELCOME,
    NEW_WELCOME_2,
    NEW_LEVEL_SELECTED,
    TARIFF_SELECT,
    PENDING_CHECKOUT,
    PENDING_REMINDER_PAYMENT_HELP_REPLY,
    PENDING_REMINDER_QUESTION_REPLY,
    PENDING_REMINDER_THINKING_REPLY,
    PAYMENT_ERROR,
    ACTIVE_STATUS,
    PENDING_STATUS,
    NEW_STATUS,
    EXPIRED_STATUS,
    SUPPORT,
    format_text,
)
from bot.states import PaymentStates
from database.models import PaymentOrderStatus, PaymentProvider, UserStatus
from database.requests import (
    add_user,
    create_payment_order,
    get_recent_pending_payment_orders,
    get_user_analytics_profile,
    get_user_by_telegram_id,
    mark_user_thinking_for_broadcast,
    mark_user_pay_click,
    save_user_email,
    snooze_pending_followup_for_day,
    update_payment_order_status,
    update_user_language_level,
    update_user_status,
)
from services.analytics import track_event
from services.lavatop_api import get_lavatop_offer_id, get_lavatop_periodicity, init_lavatop
from services.payment_activation import activate_initial_subscription, calculate_initial_subscription_end
from services.stripe_api import create_checkout_session, create_customer_portal_session
from utils.config import Config
from utils.promo import maybe_send_promo

router = Router(name="user")
logger = logging.getLogger(__name__)
LAVATOP_PENDING_TIMEOUT_MINUTES = 5


async def _sync_user_reporting(
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client],
    telegram_id: int,
    event_name: str,
    *,
    journey: str = "core",
    onboarding_version: Optional[str] = None,
    step_key: Optional[str] = None,
    source: Optional[str] = None,
    provider: Optional[PaymentProvider] = None,
    metadata: Optional[dict] = None,
    once_per_user: bool = False,
) -> None:
    resolved_version = onboarding_version or await _resolve_user_onboarding_version(session, telegram_id)
    await track_event(
        session,
        telegram_id=telegram_id,
        journey=journey,
        onboarding_version=resolved_version,
        event_name=event_name,
        step_key=step_key,
        source=source,
        provider=provider,
        metadata=metadata,
        once_per_user=once_per_user,
        config=config,
        gspread_client=gspread_client,
    )


async def _resolve_user_onboarding_version(
    session: AsyncSession,
    telegram_id: int,
    fallback: str = "core",
) -> str:
    profile = await get_user_analytics_profile(session, telegram_id)
    if profile and profile.onboarding_version:
        return profile.onboarding_version
    return fallback


def _build_checkout_redirect_url(
    config: Config,
    provider: PaymentProvider,
    order_id: int,
) -> Optional[str]:
    if not config.webhook_public_url:
        return None
    base_url = config.webhook_public_url.rstrip("/")
    return f"{base_url}/r/checkout/{quote(provider.value)}/{order_id}"


def _is_valid_email(value: str) -> bool:
    value = value.strip()
    return "@" in value and "." in value.split("@")[-1]


def _format_checkout_currency(currency: str) -> str:
    normalized = currency.upper()
    if normalized == "EUR":
        return "€"
    if normalized == "RUB":
        return "₽"
    return normalized


def _build_user_status_text(user) -> str:
    username = f"@{user.username}" if user.username else "не указан"
    user_id = user.telegram_id
    end_date = user.subscription_end_date.strftime("%d.%m.%Y") if user.subscription_end_date else "нет"
    status_templates = {
        UserStatus.new: NEW_STATUS,
        UserStatus.pending: PENDING_STATUS,
        UserStatus.active: ACTIVE_STATUS,
        UserStatus.expired: EXPIRED_STATUS,
    }
    template = status_templates.get(user.status, NEW_STATUS)
    return format_text(template, username=username, user_id=user_id, end_date=end_date)


async def send_tariff_selection_card(message: Message, config: Config) -> None:
    """Отправляет текущую карточку тарифов с единым контентом."""
    await send_tariff_selection_to_chat(message.bot, message.chat.id, config)


async def send_tariff_selection_to_chat(bot, chat_id: int, config: Config) -> None:
    """Отправляет текущую карточку тарифов в чат по chat_id."""
    if config.prices_photo_id:
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=config.prices_photo_id,
                caption=TARIFF_SELECT,
                reply_markup=get_tariff_keyboard(
                    config.price_1_month,
                    config.price_3_months,
                    config.price_6_months,
                ),
                parse_mode="HTML",
            )
            return
        except Exception:
            logger.warning("Не удалось отправить фото тарифов, отправляем текстовую карточку", exc_info=True)

    await bot.send_message(
        chat_id=chat_id,
        text=TARIFF_SELECT,
        reply_markup=get_tariff_keyboard(
            config.price_1_month,
            config.price_3_months,
            config.price_6_months,
        ),
        parse_mode="HTML",
    )


async def open_payment_flow(
    *,
    message: Message,
    session: AsyncSession,
    config: Config,
    telegram_id: int,
    username: Optional[str],
    full_name: Optional[str],
    source: str,
    onboarding_version: Optional[str] = None,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """Единая точка входа в выбор тарифа для разных сценариев."""
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        user = await add_user(
            session=session,
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
        )

    if user.status != UserStatus.active:
        await update_user_status(session, telegram_id, UserStatus.pending)
        await mark_user_pay_click(session, telegram_id)
        logger.info("user_stage_changed user=%s stage=pending source=%s", telegram_id, source)

    await send_tariff_selection_card(message, config)
    await _sync_user_reporting(
        session=session,
        config=config,
        gspread_client=gspread_client,
        telegram_id=telegram_id,
        event_name="payment_flow_entered",
        journey="payment",
        onboarding_version=onboarding_version,
        step_key="payment_flow",
        source=source,
        metadata={"entrypoint": source},
    )
    asyncio.create_task(maybe_send_promo(message.bot, message.chat.id))


async def _build_customer_portal_url(
    user,
    config: Config,
    stripe_client: StripeClient,
) -> Optional[str]:
    if not user.stripe_customer_id or user.status != UserStatus.active:
        return None
    try:
        bot_username = config.bot_username.lstrip("@")
        return_url = f"https://t.me/{bot_username}?start=portal_return" if bot_username else "https://t.me"
        return await create_customer_portal_session(
            client=stripe_client,
            stripe_customer_id=user.stripe_customer_id,
            return_url=return_url,
        )
    except Exception as e:
        logger.warning("Не удалось создать customer portal для user=%s: %s", user.telegram_id, e)
        return None


async def _dismiss_pending_reminder_keyboard(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        logger.debug("Не удалось убрать клавиатуру pending reminder", exc_info=True)


async def _create_lava_payment(
    message: Message,
    session: AsyncSession,
    config: Config,
    email: str,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    if not message.from_user:
        return

    lavatop_client = init_lavatop(config)
    if lavatop_client is None or not config.lavatop_offer_1_month:
        await message.answer("LavaTop не настроен. Напишите /support")
        return

    await save_user_email(session, message.from_user.id, email)
    await update_user_status(session, message.from_user.id, UserStatus.pending)
    await mark_user_pay_click(session, message.from_user.id)
    logger.info("user_stage_changed user=%s stage=pending source=lavatop", message.from_user.id)

    pending_orders = await get_recent_pending_payment_orders(
        session=session,
        telegram_id=message.from_user.id,
        provider=PaymentProvider.lavatop,
        minutes=10080,
    )
    pending_timeout_cutoff = datetime.utcnow() - timedelta(minutes=LAVATOP_PENDING_TIMEOUT_MINUTES)
    for pending_order in pending_orders:
        try:
            remote_invoice = await lavatop_client.get_invoice(pending_order.external_invoice_id)
        except Exception as e:
            logger.warning(
                "LavaTop pay attempt: failed to fetch invoice state telegram_id=%s invoice=%s error=%s",
                message.from_user.id,
                pending_order.external_invoice_id,
                e,
            )
            continue

        remote_status = (remote_invoice.status or "").upper()
        if remote_status in {"FAILED", "CANCELLED", "EXPIRED"}:
            failed_status = PaymentOrderStatus.cancelled if remote_status == "CANCELLED" else PaymentOrderStatus.failed
            await update_payment_order_status(
                session=session,
                external_invoice_id=pending_order.external_invoice_id,
                status=failed_status,
                external_parent_invoice_id=remote_invoice.parent_invoice_id,
                external_customer_id=remote_invoice.parent_invoice_id or pending_order.external_customer_id,
            )
            logger.info(
                "LavaTop pay attempt: pending order closed telegram_id=%s invoice=%s remote_status=%s",
                message.from_user.id,
                pending_order.external_invoice_id,
                remote_status,
            )
            continue

        if remote_status in {"PAID", "SUCCESS", "COMPLETED"}:
            await update_payment_order_status(
                session=session,
                external_invoice_id=pending_order.external_invoice_id,
                status=PaymentOrderStatus.paid,
                external_parent_invoice_id=remote_invoice.parent_invoice_id,
                external_customer_id=remote_invoice.parent_invoice_id or pending_order.external_customer_id or pending_order.external_invoice_id,
            )
            await activate_initial_subscription(
                session=session,
                bot=message.bot,
                config=config,
                telegram_id=message.from_user.id,
                subscription_end=calculate_initial_subscription_end(pending_order.tariff),
                amount=remote_invoice.amount or pending_order.amount or 0,
                provider=PaymentProvider.lavatop,
                external_payment_id=pending_order.external_invoice_id,
                payment_customer_id=remote_invoice.parent_invoice_id or pending_order.external_customer_id or pending_order.external_invoice_id,
            )
            logger.info(
                "LavaTop pay attempt: activated already paid invoice telegram_id=%s invoice=%s",
                message.from_user.id,
                pending_order.external_invoice_id,
            )
            await message.answer(
                "Платёж уже подтверждён. Доступ активирован.",
                parse_mode="Markdown",
            )
            return

        is_stale_pending = pending_order.created_at is not None and pending_order.created_at < pending_timeout_cutoff
        same_email = (pending_order.email or "").strip().lower() == email.strip().lower()
        if remote_status in {"", "NEW", "CREATED", "PENDING", "IN_PROGRESS"} and is_stale_pending:
            await update_payment_order_status(
                session=session,
                external_invoice_id=pending_order.external_invoice_id,
                status=PaymentOrderStatus.failed,
                external_parent_invoice_id=remote_invoice.parent_invoice_id,
                external_customer_id=remote_invoice.parent_invoice_id or pending_order.external_customer_id or pending_order.external_invoice_id,
            )
            logger.warning(
                "LavaTop pay attempt: stale pending invoice marked failed telegram_id=%s invoice=%s age_limit_minutes=%s remote_status=%s",
                message.from_user.id,
                pending_order.external_invoice_id,
                LAVATOP_PENDING_TIMEOUT_MINUTES,
                remote_status,
            )
            continue

        if (
            remote_status in {"", "NEW", "CREATED", "PENDING", "IN_PROGRESS"}
            and pending_order.payment_url
            and same_email
        ):
            logger.info(
                "LavaTop pay attempt: reusing active invoice telegram_id=%s invoice=%s created_at=%s",
                message.from_user.id,
                pending_order.external_invoice_id,
                pending_order.created_at,
            )
            await message.answer(
                text=format_text(
                    PENDING_CHECKOUT,
                    period="1 месяц",
                    price=remote_invoice.amount or pending_order.amount or 0,
                    currency=_format_checkout_currency(remote_invoice.currency or pending_order.currency),
                ),
                reply_markup=get_payment_link_keyboard(
                    _build_checkout_redirect_url(config, PaymentProvider.lavatop, pending_order.id)
                    or pending_order.payment_url
                ),
                parse_mode="HTML",
            )
            await _sync_user_reporting(
                session=session,
                config=config,
                gspread_client=gspread_client,
                telegram_id=message.from_user.id,
                event_name="payment_flow_entered",
                journey="payment",
                step_key="payment_flow",
                source="pay_lava:reuse",
                provider=PaymentProvider.lavatop,
                metadata={"reuse_existing_order": True},
            )
            return

    invoice = await lavatop_client.create_invoice(
        email=email,
        offer_id=get_lavatop_offer_id(config, "1month"),
        periodicity=get_lavatop_periodicity("1month"),
        currency=config.lavatop_currency,
        payment_provider=config.lavatop_payment_provider or None,
        payment_method=config.lavatop_payment_method or None,
        buyer_language=config.lavatop_buyer_language,
    )

    if not invoice.id or not invoice.payment_url:
        raise ValueError("LavaTop не вернул payment URL")

    order = await create_payment_order(
        session=session,
        telegram_id=message.from_user.id,
        provider=PaymentProvider.lavatop,
        tariff="1month",
        email=email,
        external_invoice_id=invoice.id,
        amount=invoice.amount,
        currency=invoice.currency,
        payment_url=invoice.payment_url,
    )
    logger.info(
        "LavaTop pay attempt: created new invoice telegram_id=%s invoice=%s amount=%s currency=%s",
        message.from_user.id,
        invoice.id,
        invoice.amount,
        invoice.currency,
    )

    await message.answer(
        text=format_text(
            PENDING_CHECKOUT,
            period="1 месяц",
            price=invoice.amount,
            currency=_format_checkout_currency(invoice.currency),
        ),
        reply_markup=get_payment_link_keyboard(
            _build_checkout_redirect_url(config, PaymentProvider.lavatop, order.id)
            or invoice.payment_url
        ),
        parse_mode="HTML",
    )
    await _sync_user_reporting(
        session=session,
        config=config,
        gspread_client=gspread_client,
        telegram_id=message.from_user.id,
        event_name="payment_flow_entered",
        journey="payment",
        step_key="payment_flow",
        source="pay_lava:new",
        provider=PaymentProvider.lavatop,
        metadata={"tariff": "1month"},
    )


# =============================================================================
# /start — приветствие и выбор уровня языка
# =============================================================================

@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session: AsyncSession,
    config: Config,
    state: FSMContext,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Обработчик команды /start.
    1. Сохраняет пользователя в БД (если нового)
    2. Запускает онбординг с кружком и демо AI
    """
    user = message.from_user
    if not user:
        return

    # Добавляем пользователя в БД (или получаем существующего)
    db_user = await add_user(
        session=session,
        telegram_id=user.id,
        username=user.username,
        full_name=user.full_name,
    )

    from bot.handlers.starts_onboarding import send_starts1_onboarding

    await send_starts1_onboarding(message, session, config, gspread_client, source="/start")


@router.callback_query(F.data.startswith("level:"))
async def callback_language_level(callback: CallbackQuery, session: AsyncSession) -> None:
    """
    Обработчик выбора уровня языка (callback: level:A1-A2 или level:B1-B2).
    """
    if not callback.data or not callback.from_user:
        return

    # Извлекаем уровень из callback_data
    level = callback.data.split(":")[1]  # "A1-A2" или "B1-B2"

    # Сохраняем уровень в БД
    await update_user_language_level(session, callback.from_user.id, level)

    await callback.answer(f"Уровень {level} сохранён!")
    await callback.message.edit_text(
        format_text(NEW_LEVEL_SELECTED, level=level),
        parse_mode="Markdown",
    )


# =============================================================================
# /pay — выбор тарифа и оплата
# =============================================================================

@router.message(Command("pay"))
async def cmd_pay(
    message: Message,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Обработчик команды /pay.
    Показывает клавиатуру с тарифами и фото.
    Меняет статус на PENDING и записывает время захода.
    """
    # Проверяем, нет ли уже активной подписки
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if user and user.status == UserStatus.active:
        await message.answer(
            "У вас уже есть активная подписка!\n\n"
            "Управление подпиской: /status",
            parse_mode="Markdown"
        )
        return
    
    await open_payment_flow(
        message=message,
        session=session,
        config=config,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        source="/pay",
        onboarding_version=await _resolve_user_onboarding_version(session, message.from_user.id),
        gspread_client=gspread_client,
    )


@router.message(Command("pay_lava"))
async def cmd_pay_lava(
    message: Message,
    session: AsyncSession,
    config: Config,
    state: FSMContext,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    if not message.from_user:
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if user and user.status == UserStatus.active:
        await message.answer(
            "У вас уже есть активная подписка!\n\nУправление подпиской: /status",
            parse_mode="Markdown",
        )
        return

    if user is None:
        await add_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        user = await get_user_by_telegram_id(session, message.from_user.id)

    email = None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1:
        candidate = parts[1].strip()
        if _is_valid_email(candidate):
            email = candidate

    if email is None and user and user.email and _is_valid_email(user.email):
        email = user.email

    if email is None:
        await state.set_state(PaymentStates.waiting_for_lava_email)
        await message.answer("Отправьте email для оплаты через LavaTop")
        return

    try:
        await state.clear()
        await _create_lava_payment(message, session, config, email, gspread_client)
    except Exception:
        await message.answer(PAYMENT_ERROR, parse_mode="Markdown")


@router.message(PaymentStates.waiting_for_lava_email)
async def handle_lava_email(
    message: Message,
    session: AsyncSession,
    config: Config,
    state: FSMContext,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    if not message.text or not _is_valid_email(message.text):
        await message.answer("Нужен корректный email для оплаты через LavaTop")
        return

    try:
        await state.clear()
        await _create_lava_payment(message, session, config, message.text.strip(), gspread_client)
    except Exception:
        await message.answer(PAYMENT_ERROR, parse_mode="Markdown")


@router.callback_query(F.data.startswith("tariff:"))
async def callback_tariff(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    stripe_client: StripeClient,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Обработчик выбора тарифа (callback: tariff:1month или tariff:3months).
    Меняет статус на pending и генерирует ссылку на оплату Stripe.
    """
    if not callback.data or not callback.from_user:
        return

    # Проверяем, нет ли уже активной подписки
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if user and user.status == UserStatus.active:
        await callback.answer("У вас уже есть активная подписка!", show_alert=True)
        return

    tariff = callback.data.split(":")[1]  # "1month", "3months" или "6months"
    await callback.answer()

    # Определяем цену и период
    if tariff == "1month":
        price = config.price_1_month
        period = "1 месяц"
    elif tariff == "3months":
        price = config.price_3_months
        period = "3 месяца"
    else:  # 6months
        price = config.price_6_months
        period = "6 месяцев"

    # Меняем статус пользователя на pending
    await update_user_status(session, callback.from_user.id, UserStatus.pending)

    await mark_user_pay_click(session, callback.from_user.id)
    logger.info("user_stage_changed user=%s stage=pending source=tariff_selected tariff=%s", callback.from_user.id, tariff)

    # Генерируем ссылку на Stripe Checkout
    try:
        checkout_session = await create_checkout_session(
            client=stripe_client,
            config=config,
            telegram_id=callback.from_user.id,
            tariff=tariff,
        )
        redirect_onboarding_version = await _resolve_user_onboarding_version(session, callback.from_user.id)
        stripe_order = await create_payment_order(
            session=session,
            telegram_id=callback.from_user.id,
            provider=PaymentProvider.stripe,
            tariff=tariff,
            email=f"telegram-{callback.from_user.id}@local.invalid",
            external_invoice_id=checkout_session["id"],
            amount=price,
            currency="EUR",
            payment_url=checkout_session["url"],
        )
        redirect_url = _build_checkout_redirect_url(config, PaymentProvider.stripe, stripe_order.id) or checkout_session["url"]

        # Отправляем новое сообщение с другим фото
        TARIFF_SELECTED_PHOTO = "AgACAgIAAxkBAAIDbWl81m0uHZ_2zIeo4YlCYNrJBZWMAAKmEWsbN07oS7OqInpOY7e_AQADAgADeQADOAQ"
        await callback.message.answer_photo(
            photo=TARIFF_SELECTED_PHOTO,
            caption=format_text(
                PENDING_CHECKOUT,
                period=period,
                price=price,
                currency=_format_checkout_currency("EUR"),
            ),
            reply_markup=get_payment_link_keyboard(redirect_url),
            parse_mode="HTML",
        )
        await _sync_user_reporting(
            session=session,
            config=config,
            gspread_client=gspread_client,
            telegram_id=callback.from_user.id,
            event_name="tariff_selected",
            journey="payment",
            onboarding_version=redirect_onboarding_version,
            step_key=f"tariff:{tariff}",
            source="tariff_callback",
            provider=PaymentProvider.stripe,
            metadata={
                "tariff": tariff,
                "period": period,
                "price": price,
                "checkout_order_id": stripe_order.id,
            },
        )
    except Exception as e:
        # Отправляем новое сообщение вместо редактирования
        await callback.message.answer(
            PAYMENT_ERROR,
            parse_mode="Markdown",
        )


# =============================================================================
# /status — личный кабинет
# =============================================================================

@router.message(Command("status"))
async def cmd_status(
    message: Message,
    session: AsyncSession,
    config: Config,
    stripe_client: StripeClient,
) -> None:
    """
    Обработчик команды /status.
    Показывает текущий статус подписки и дату окончания.
    """
    user = message.from_user
    if not user:
        return

    db_user = await get_user_by_telegram_id(session, user.id)

    if not db_user:
        await message.answer("❌ Ты ещё не зарегистрирован. Напиши /start")
        return
    text = _build_user_status_text(db_user)
    portal_url = await _build_customer_portal_url(db_user, config, stripe_client)

    # Определяем, активна ли подписка
    has_active = db_user.status == UserStatus.active
    
    await message.answer(
        text=text,
        reply_markup=get_subscription_manage_keyboard(portal_url, has_active_subscription=has_active),
    )


@router.callback_query(F.data == "action:pay")
async def callback_action_pay(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Обработчик кнопки "Продлить подписку" из /status.
    Перенаправляет на выбор тарифа.
    """
    await callback.answer()

    if callback.from_user is None:
        return

    await open_payment_flow(
        message=callback.message,
        session=session,
        config=config,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
        source="action:pay",
        onboarding_version=await _resolve_user_onboarding_version(session, callback.from_user.id),
        gspread_client=gspread_client,
    )


@router.callback_query(F.data == "pending_reminder:question")
async def callback_pending_reminder_question(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    if callback.from_user is None or callback.message is None:
        return

    await callback.answer()
    await _dismiss_pending_reminder_keyboard(callback)
    await callback.message.answer(
        format_text(PENDING_REMINDER_QUESTION_REPLY, first_name=callback.from_user.first_name or "Друг"),
        reply_markup=get_pending_curator_keyboard(),
    )
    await _sync_user_reporting(
        session=session,
        config=config,
        gspread_client=gspread_client,
        telegram_id=callback.from_user.id,
        event_name="pending_reminder_question_clicked",
        journey="payment",
        step_key="pending_reminder:question",
        source="pending_reminder",
    )


@router.callback_query(F.data == "pending_reminder:payment")
async def callback_pending_reminder_payment(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    if callback.from_user is None or callback.message is None:
        return

    await callback.answer()
    await _dismiss_pending_reminder_keyboard(callback)
    await callback.message.answer(
        format_text(PENDING_REMINDER_PAYMENT_HELP_REPLY, first_name=callback.from_user.first_name or "Друг"),
        reply_markup=get_pending_manager_keyboard(),
    )
    await _sync_user_reporting(
        session=session,
        config=config,
        gspread_client=gspread_client,
        telegram_id=callback.from_user.id,
        event_name="pending_reminder_payment_clicked",
        journey="payment",
        step_key="pending_reminder:payment",
        source="pending_reminder",
    )


@router.callback_query(F.data == "pending_reminder:thinking")
async def callback_pending_reminder_thinking(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    if callback.from_user is None or callback.message is None:
        return

    await callback.answer()
    await _dismiss_pending_reminder_keyboard(callback)
    await snooze_pending_followup_for_day(session, callback.from_user.id)
    await mark_user_thinking_for_broadcast(session, callback.from_user.id)
    await callback.message.answer(
        format_text(PENDING_REMINDER_THINKING_REPLY, first_name=callback.from_user.first_name or "Друг"),
    )
    await _sync_user_reporting(
        session=session,
        config=config,
        gspread_client=gspread_client,
        telegram_id=callback.from_user.id,
        event_name="pending_reminder_thinking_clicked",
        journey="payment",
        step_key="pending_reminder:thinking",
        source="pending_reminder",
        metadata={"followup_delay_hours": 24},
    )


# =============================================================================
# /support — связь с админом
# =============================================================================

@router.message(Command("support"))
async def cmd_support(message: Message, config: Config) -> None:
    """
    Обработчик команды /support.
    Показывает контакт админа для связи.
    """
    await message.answer(text=SUPPORT, parse_mode="HTML")


# =============================================================================
# /schedule — расписание эфиров
# =============================================================================

@router.message(Command("schedule"))
async def cmd_schedule(message: Message, session: AsyncSession) -> None:
    """Показывает статическое расписание (legacy)."""
    text, _ = await build_smart_schedule(session, message.from_user.id)
    await message.answer(text=text, parse_mode="HTML")


@router.callback_query(F.data == "action:schedule")
async def callback_action_schedule(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """Обработчик кнопки 'Расписание'."""
    await callback.answer()
    await _sync_user_reporting(
        session=session,
        config=config,
        gspread_client=gspread_client,
        telegram_id=callback.from_user.id,
        event_name="schedule_opened",
        journey="onboarding",
        step_key="schedule",
        source="action:schedule",
    )
    text, is_subscribed = await build_smart_schedule(session, callback.from_user.id)
    await callback.message.answer(
        text=text,
        reply_markup=get_schedule_keyboard(is_subscribed),
        parse_mode="HTML",
    )


# =============================================================================
# /menu — главное инлайн-меню для пользователей
# =============================================================================

@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    """Показывает reply-клавиатуру с главным меню."""
    await message.answer(
        "📋 Меню активировано",
        reply_markup=get_main_reply_keyboard(),
        parse_mode="Markdown",
    )


# =============================================================================
# /info — умное расписание созвонов
# =============================================================================

async def build_smart_schedule(session: AsyncSession, telegram_id: int) -> tuple[str, bool]:
    """
    Формирует умное расписание с группировкой по неделям и статусом RSVP.
    Возвращает (текст, is_subscribed).
    """
    from database.requests import get_upcoming_events, get_user_rsvp_statuses, get_user_by_telegram_id
    from datetime import datetime, timedelta
    import pytz

    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz)
    
    user = await get_user_by_telegram_id(session, telegram_id)
    is_subscribed = user and user.status == UserStatus.active
    
    events = await get_upcoming_events(session, limit=10)
    
    if not events:
        text = "📅 <b>Расписание созвонов — время по Мадриду</b>\n\n"
        text += "<blockquote>Пока нет запланированных созвонов.\nСледите за обновлениями!</blockquote>"
        return text, is_subscribed
    
    broadcast_ids = [e.id for e in events]
    rsvp_statuses = await get_user_rsvp_statuses(session, telegram_id, broadcast_ids)
    
    text = "📅 <b>Расписание созвонов — время по Мадриду</b>\n\n"
    
    current_week = None
    week_names = {
        0: "Эта неделя",
        1: "Следующая неделя",
    }
    week_lines: list[str] = []
    
    for event in events:
        event_dt = madrid_tz.localize(event.rsvp_event_datetime)
        
        week_diff = (event_dt.isocalendar()[1] - now.isocalendar()[1])
        if event_dt.year > now.year:
            week_diff += 52
        
        if week_diff != current_week:
            if week_lines:
                text += "\n".join(week_lines) + "\n\n"
                week_lines = []
            current_week = week_diff
            week_label = week_names.get(week_diff, f"Через {week_diff} недель")
            text += f"<b>{escape(week_label)}</b>\n"
        
        day_name = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][event_dt.weekday()]
        date_str = event_dt.strftime(f"{day_name}, %d.%m")
        time_str = event_dt.strftime("%H:%M")
        title = escape(event.rsvp_event_title)
        
        rsvp_status = rsvp_statuses.get(event.id)
        status_line = ""
        if rsvp_status == "attending":
            status_line = "<i>✓ Вы записаны</i>"
        elif rsvp_status == "declined":
            status_line = "<i>— Вы отказались</i>"
        status_suffix = f"\n{status_line}" if status_line else ""
        
        week_lines.append(
            f"<blockquote><b>{escape(date_str)} — {escape(time_str)}</b>\n{title}"
            f"{status_suffix}</blockquote>"
        )

    if week_lines:
        text += "\n".join(week_lines) + "\n\n"
    
    if is_subscribed:
        text += "<i>✓ = вы записаны</i>"
    else:
        text += "<i>Оформите подписку, чтобы участвовать в созвонах</i>"
    
    return text, is_subscribed


async def build_event_card(
    session: AsyncSession,
    telegram_id: int,
    event_index: int,
) -> tuple[str, int, int, bool, int]:
    """
    Формирует карточку отдельного события для навигации.
    
    Returns:
        (текст_карточки, event_index, total_events, is_registered, broadcast_id)
    """
    from database.requests import get_upcoming_events, get_user_rsvp, get_user_by_telegram_id
    from datetime import datetime
    import pytz

    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz)
    
    user = await get_user_by_telegram_id(session, telegram_id)
    events = await get_upcoming_events(session, limit=10)
    
    if not events or event_index >= len(events):
        return "Нет доступных событий", 0, 0, False, 0
    
    event = events[event_index]
    total_events = len(events)
    
    # Проверяем, записан ли пользователь
    rsvp = await get_user_rsvp(session, event.id, telegram_id)
    is_registered = rsvp and rsvp.response.value == "attending"
    
    # Форматируем дату и время
    event_dt = madrid_tz.localize(event.rsvp_event_datetime)
    day_name = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][event_dt.weekday()]
    date_str = event_dt.strftime(f"{day_name}, %d.%m.%Y")
    time_str = event_dt.strftime("%H:%M")
    
    # Формируем текст карточки
    text = f"📅 **Ближайшая встреча**\n\n"
    text += f"{event.rsvp_event_title}\n\n"
    text += f"📆 {date_str}\n"
    text += f"⏰ {time_str} Madrid\n\n"
    text += "Запишитесь, чтобы получить напоминание и ссылку на созвон."
    
    return text, event_index, total_events, is_registered, event.id


@router.message(Command("info"))
async def cmd_info(message: Message, session: AsyncSession) -> None:
    """Показывает умное расписание созвонов."""
    text, is_subscribed = await build_smart_schedule(session, message.from_user.id)
    await message.answer(
        text=text,
        reply_markup=get_schedule_keyboard(is_subscribed),
        parse_mode="HTML",
    )


# =============================================================================
# Обработчики инлайн-меню (menu:*)
# =============================================================================

@router.callback_query(F.data == "menu:schedule")
async def callback_menu_schedule(callback: CallbackQuery, session: AsyncSession) -> None:
    """Обработчик кнопки 'Расписание' из меню."""
    await callback.answer()
    text, is_subscribed = await build_smart_schedule(session, callback.from_user.id)
    await callback.message.answer(
        text=text,
        reply_markup=get_schedule_keyboard(is_subscribed),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:status")
async def callback_menu_status(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    stripe_client: StripeClient,
) -> None:
    """Обработчик кнопки 'Статус' из меню — дублирует /status."""
    await callback.answer()
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    
    if not user:
        await callback.message.answer("Пользователь не найден. Напишите /start")
        return
    
    text = _build_user_status_text(user)
    portal_url = await _build_customer_portal_url(user, config, stripe_client)
    keyboard = get_subscription_manage_keyboard(
        portal_url,
        has_active_subscription=user.status == UserStatus.active,
    )
    
    await callback.message.answer(text=text, reply_markup=keyboard)


@router.callback_query(F.data == "menu:cabinet")
async def callback_menu_cabinet(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    stripe_client: StripeClient,
) -> None:
    """Обработчик кнопки 'Кабинет' из меню — дублирует /pay."""
    await callback.answer()
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    
    if user and user.status == UserStatus.active:
        portal_url = await _build_customer_portal_url(user, config, stripe_client)
        if portal_url:
            await callback.message.answer(
                "💳 **Управление подпиской**\n\n"
                "В личном кабинете Stripe вы можете:\n"
                "— Просмотреть историю платежей\n"
                "— Изменить способ оплаты\n"
                "— Отменить подписку",
                reply_markup=get_subscription_manage_keyboard(portal_url, has_active_subscription=True),
                parse_mode="Markdown",
            )
        else:
            await callback.message.answer(
                text=_build_user_status_text(user),
                reply_markup=get_subscription_manage_keyboard(None, has_active_subscription=True),
            )
        return
    
        await callback.message.answer(
            text=TARIFF_SELECT,
            reply_markup=get_tariff_keyboard(
                config.price_1_month,
                config.price_3_months,
                config.price_6_months,
            ),
            parse_mode="HTML",
    )
    asyncio.create_task(maybe_send_promo(callback.message.bot, callback.message.chat.id))


@router.callback_query(F.data == "menu:support")
async def callback_menu_support(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Поддержка' из меню — дублирует /support."""
    await callback.answer()
    await callback.message.answer(text=SUPPORT, parse_mode="Markdown")


# =============================================================================
# Обработчики Reply Keyboard кнопок (текстовые сообщения)
# =============================================================================

@router.message(F.text == "Расписание")
async def reply_schedule(message: Message, session: AsyncSession) -> None:
    """Обработчик reply-кнопки 'Расписание'."""
    text, is_subscribed = await build_smart_schedule(session, message.from_user.id)
    await message.answer(
        text=text,
        reply_markup=get_schedule_keyboard(is_subscribed),
        parse_mode="HTML",
    )


@router.message(F.text == "Кабинет")
async def reply_cabinet(
    message: Message,
    session: AsyncSession,
    config: Config,
    stripe_client: StripeClient,
) -> None:
    """Обработчик reply-кнопки 'Кабинет' — показывает статус подписки."""
    user = await get_user_by_telegram_id(session, message.from_user.id)
    
    if not user:
        await message.answer(
            "Сначала ознакомьтесь с информацией о клубе.\n\n"
            "Введите /start для начала."
        )
        return
    
    portal_url = await _build_customer_portal_url(user, config, stripe_client)
    text = _build_user_status_text(user)
    keyboard = get_subscription_manage_keyboard(
        portal_url,
        has_active_subscription=user.status == UserStatus.active,
    )
    
    await message.answer(text=text, reply_markup=keyboard)


@router.message(F.text == "Поддержка")
async def reply_support(message: Message) -> None:
    """Обработчик reply-кнопки 'Поддержка'."""
    await message.answer(text=SUPPORT, parse_mode="HTML")


@router.message(F.text == "Тарифы")
async def reply_tariffs(message: Message, config: Config) -> None:
    """Обработчик reply-кнопки 'Тарифы'."""
    if config.prices_photo_id:
        try:
            await message.answer_photo(
                photo=config.prices_photo_id,
                caption=TARIFF_SELECT,
                reply_markup=get_tariff_keyboard(
                    config.price_1_month,
                    config.price_3_months,
                    config.price_6_months,
                ),
                parse_mode="HTML",
            )
            asyncio.create_task(maybe_send_promo(message.bot, message.chat.id))
            return
        except Exception:
            pass
    
    await message.answer(
        text=TARIFF_SELECT,
        reply_markup=get_tariff_keyboard(
            config.price_1_month,
            config.price_3_months,
            config.price_6_months,
        ),
        parse_mode="HTML",
    )
    asyncio.create_task(maybe_send_promo(message.bot, message.chat.id))


@router.message(F.text == "Попробовать GregoChat")
async def reply_gregochat(message: Message) -> None:
    """Обработчик reply-кнопки 'Попробовать GregoChat'."""
    text = """GregoChat — AI-бот для практики испанского

Входит в любой тариф подписки. Используем последние модели ИИ для практики разговорной речи.

Возможности:
— Разговорная практика с оценкой речи
— Переводчик
— Справочник
— Анализ фото
— Упражнения

Для гостей доступны лимиты:
— 5 реплик в диалоге
— 20 переводов
— 5 запросов в других функциях

Попробуйте: <a href="https://t.me/GregoChat_bot">@GregoChat_bot</a>"""
    
    await message.answer(text=text, parse_mode="HTML")


# =============================================================================
# /get_id_crug — получение file_id видео-кружка (для админа)
# =============================================================================

@router.message(Command("get_id_crug"))
async def cmd_get_id_crug(message: Message, config: Config) -> None:
    """
    Команда для получения file_id видео-кружка.
    Отправь кружок в ответ на это сообщение.
    """
    if message.from_user.id not in config.admin_ids:
        return
    
    await message.answer(
        "📹 Теперь отправь видео-кружок (video note), и я покажу его file_id."
    )


@router.message(F.video_note)
async def handle_video_note(message: Message, config: Config) -> None:
    """
    Обработчик видео-кружка — показывает file_id.
    """
    if message.from_user.id not in config.admin_ids:
        return
    
    file_id = message.video_note.file_id
    await message.answer(
        f"✅ **File ID кружка:**\n\n`{file_id}`",
        parse_mode="Markdown"
    )


# =============================================================================
# RSVP — ответы на кнопки «Я буду» / «Не смогу»
# =============================================================================

def build_google_calendar_url(title: str, event_dt: "datetime", duration_hours: int = 1) -> str:
    """Формирует URL для создания события в Google Calendar."""
    from datetime import timedelta
    from urllib.parse import quote

    start = event_dt.strftime("%Y%m%dT%H%M%S")
    end = (event_dt + timedelta(hours=duration_hours)).strftime("%Y%m%dT%H%M%S")
    return (
        f"https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={quote(title)}"
        f"&dates={start}/{end}"
        f"&details={quote('Созвон в клубе')}"
    )


@router.callback_query(F.data.startswith("rsvp:attend:"))
async def callback_rsvp_attend(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """Пользователь нажал «Я буду»."""
    from database.requests import add_rsvp, get_scheduled_broadcast, count_rsvp_attending, get_upcoming_events
    from database.models import RSVPResponse

    broadcast_id = int(callback.data.split(":")[2])
    telegram_id = callback.from_user.id

    await add_rsvp(session, broadcast_id, telegram_id, RSVPResponse.attending)

    broadcast = await get_scheduled_broadcast(session, broadcast_id)
    attending_count = await count_rsvp_attending(session, broadcast_id)

    await callback.answer(f"Ты записан(а). Всего придут: {attending_count}")

    # Проверяем, вызвана ли кнопка из карточки события (по наличию кнопок навигации)
    is_event_card = callback.message.reply_markup and any(
        button.callback_data and button.callback_data.startswith("event:nav:")
        for row in callback.message.reply_markup.inline_keyboard
        for button in row
    )
    
    if is_event_card:
        # Находим индекс текущего события в списке
        events = await get_upcoming_events(session, limit=10)
        event_index = next((i for i, e in enumerate(events) if e.id == broadcast_id), 0)
        
        # Обновляем клавиатуру карточки события
        try:
            await callback.message.edit_reply_markup(
                reply_markup=get_event_navigation_keyboard(
                    event_index=event_index,
                    total_events=len(events),
                    broadcast_id=broadcast_id,
                    is_registered=True,
                )
            )
        except Exception:
            pass
    else:
        # Стандартное поведение для обычных RSVP-рассылок
        try:
            await callback.message.edit_reply_markup(
                reply_markup=get_rsvp_only_decline_keyboard(broadcast_id)
            )
        except Exception:
            pass

    if broadcast and broadcast.rsvp_event_datetime and broadcast.rsvp_event_title:
        calendar_url = build_google_calendar_url(
            title=broadcast.rsvp_event_title,
            event_dt=broadcast.rsvp_event_datetime,
        )
        await callback.message.answer(
            "Добавить событие в Google календарь?",
            reply_markup=get_calendar_keyboard(calendar_url),
            parse_mode="Markdown",
        )

    await _sync_user_reporting(
        session=session,
        config=config,
        gspread_client=gspread_client,
        telegram_id=telegram_id,
        event_name="first_rsvp_attending",
        journey="engagement",
        step_key="rsvp:attend",
        source="rsvp:attend",
        metadata={"broadcast_id": broadcast_id},
        once_per_user=True,
    )


@router.callback_query(F.data.startswith("rsvp:decline:"))
async def callback_rsvp_decline(callback: CallbackQuery, session: AsyncSession) -> None:
    """Пользователь нажал «Не смогу»."""
    from database.requests import add_rsvp, get_upcoming_events
    from database.models import RSVPResponse

    broadcast_id = int(callback.data.split(":")[2])
    telegram_id = callback.from_user.id

    await add_rsvp(session, broadcast_id, telegram_id, RSVPResponse.declined)
    await callback.answer("Жаль! Надеемся увидеть тебя в следующий раз.")

    # Проверяем, вызвана ли кнопка из карточки события
    is_event_card = callback.message.reply_markup and any(
        button.callback_data and button.callback_data.startswith("event:nav:")
        for row in callback.message.reply_markup.inline_keyboard
        for button in row
    )
    
    if is_event_card:
        # Находим индекс текущего события в списке
        events = await get_upcoming_events(session, limit=10)
        event_index = next((i for i, e in enumerate(events) if e.id == broadcast_id), 0)
        
        # Обновляем клавиатуру карточки события (пользователь больше не записан)
        try:
            await callback.message.edit_reply_markup(
                reply_markup=get_event_navigation_keyboard(
                    event_index=event_index,
                    total_events=len(events),
                    broadcast_id=broadcast_id,
                    is_registered=False,
                )
            )
        except Exception:
            pass
    else:
        # Стандартное поведение для обычных RSVP-рассылок
        try:
            await callback.message.edit_reply_markup(
                reply_markup=get_rsvp_only_attend_keyboard(broadcast_id)
            )
        except Exception:
            pass


@router.callback_query(F.data == "rsvp:dismiss_calendar")
async def callback_dismiss_calendar(callback: CallbackQuery) -> None:
    """Пользователь нажал «Нет» на предложение Google Calendar — удаляем сообщение."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass


# =============================================================================
# Навигация по событиям (schedule:signup, event:nav:N)
# =============================================================================

@router.callback_query(F.data == "schedule:signup")
async def callback_schedule_signup(callback: CallbackQuery, session: AsyncSession) -> None:
    """Пользователь нажал 'Записаться' — показываем первое событие."""
    await callback.answer()
    
    text, event_index, total_events, is_registered, broadcast_id = await build_event_card(
        session, callback.from_user.id, event_index=0
    )
    
    if total_events == 0:
        await callback.message.answer("Пока нет запланированных созвонов.")
        return
    
    await callback.message.answer(
        text=text,
        reply_markup=get_event_navigation_keyboard(
            event_index=event_index,
            total_events=total_events,
            broadcast_id=broadcast_id,
            is_registered=is_registered,
        ),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("event:nav:"))
async def callback_event_navigation(callback: CallbackQuery, session: AsyncSession) -> None:
    """Навигация между событиями (Назад/Дальше)."""
    event_index = int(callback.data.split(":")[2])
    
    text, event_index, total_events, is_registered, broadcast_id = await build_event_card(
        session, callback.from_user.id, event_index=event_index
    )
    
    await callback.answer()
    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=get_event_navigation_keyboard(
                event_index=event_index,
                total_events=total_events,
                broadcast_id=broadcast_id,
                is_registered=is_registered,
            ),
            parse_mode="Markdown",
        )
    except Exception:
        # Если не удалось отредактировать — отправляем новое сообщение
        await callback.message.answer(
            text=text,
            reply_markup=get_event_navigation_keyboard(
                event_index=event_index,
                total_events=total_events,
                broadcast_id=broadcast_id,
                is_registered=is_registered,
            ),
            parse_mode="Markdown",
        )


# =============================================================================
# Проверка входа в группу после покупки
# =============================================================================

@router.callback_query(F.data == "group_join:yes")
async def callback_group_join_yes(callback: CallbackQuery) -> None:
    """Пользователь подтвердил, что зашел в группу."""
    await callback.answer()
    try:
        await callback.message.edit_text(
            text=ACTIVE_GROUP_JOIN_YES,
            reply_markup=None,
        )
    except Exception:
        await callback.message.answer(text=ACTIVE_GROUP_JOIN_YES)


@router.callback_query(F.data == "group_join:no")
async def callback_group_join_no(callback: CallbackQuery) -> None:
    """Пользователь ответил, что не зашел в группу."""
    await callback.answer()
    try:
        await callback.message.edit_text(
            text=ACTIVE_GROUP_JOIN_NO,
            reply_markup=None,
        )
    except Exception:
        await callback.message.answer(text=ACTIVE_GROUP_JOIN_NO)
