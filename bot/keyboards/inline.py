# Инлайн-клавиатуры для бота
# Используем InlineKeyboardBuilder из aiogram 3.x

from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

ULTIMAGREGO_URL = "https://t.me/ultimagrego_bot"


# =============================================================================
# КЛАВИАТУРЫ ДЛЯ /start — выбор уровня языка
# =============================================================================

def get_language_level_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора уровня языка при /start.
    Callback data: level:A1-A2, level:B1-B2
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔰 A1-A2 (Начинающий)", callback_data="level:A1-A2"),
        InlineKeyboardButton(text="📚 B1-B2 (Средний)", callback_data="level:B1-B2"),
    )
    return builder.as_markup()


# =============================================================================
# КЛАВИАТУРЫ ДЛЯ /pay — выбор тарифа
# =============================================================================

def get_tariff_keyboard(
    price_1_month: float,
    price_3_months: float,
    price_6_months: float,
) -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора тарифа подписки.
    Цены передаются из конфига.
    Callback data: tariff:1month, tariff:3months, tariff:6months
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"1 месяц — {price_1_month:.0f} €",
            callback_data="tariff:1month",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=f"3 месяца — {price_3_months:.0f} € (44 €/мес)",
            callback_data="tariff:3months",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=f"6 месяцев — {price_6_months:.0f} € (39 €/мес)",
            callback_data="tariff:6months",
        ),
    )
    return builder.as_markup()


def get_payment_link_keyboard(payment_url: str) -> InlineKeyboardMarkup:
    """
    Клавиатура с кнопкой-ссылкой на оплату Stripe.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💳 Оплатить", url=payment_url),
    )
    return builder.as_markup()


def get_pending_reminder_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура первого pending-напоминания с развилкой по возражению.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Есть вопрос", callback_data="pending_reminder:question"),
    )
    builder.row(
        InlineKeyboardButton(text="Не могу оплатить", callback_data="pending_reminder:payment"),
    )
    builder.row(
        InlineKeyboardButton(text="Пока думаю", callback_data="pending_reminder:thinking"),
    )
    return builder.as_markup()


def get_pending_curator_keyboard() -> InlineKeyboardMarkup:
    """
    CTA после выбора «Есть вопрос».
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Написать куратору", url=ULTIMAGREGO_URL),
    )
    return builder.as_markup()


def get_pending_manager_keyboard() -> InlineKeyboardMarkup:
    """
    CTA после выбора «Не могу оплатить».
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Написать менеджеру", url=ULTIMAGREGO_URL),
    )
    return builder.as_markup()


def get_after_payment_keyboard(gregochat_username: str = "GregoChat_bot") -> InlineKeyboardMarkup:
    """
    Клавиатура после успешной оплаты: Расписание и GregoChat.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Расписание", callback_data="action:schedule"),
        InlineKeyboardButton(text="🤖 GregoChat", url=f"https://t.me/{gregochat_username}"),
    )
    return builder.as_markup()


def get_welcome_keyboard(gregochat_username: str = "GregoChat_bot") -> InlineKeyboardMarkup:
    """
    Клавиатура для /start: Расписание, GregoChat AI, Тарифы.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Расписание", callback_data="action:schedule"),
        InlineKeyboardButton(text="🤖 GregoChat AI", url=f"https://t.me/{gregochat_username}"),
    )
    builder.row(
        InlineKeyboardButton(text="💳 Тарифы", callback_data="action:pay"),
    )
    return builder.as_markup()


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Главное меню для пользователей — дубли команд для удобства.
    Расписание (/info), Статус (/status), Кабинет (/pay), Поддержка (/support)
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Расписание", callback_data="menu:schedule"),
        InlineKeyboardButton(text="📊 Статус", callback_data="menu:status"),
    )
    builder.row(
        InlineKeyboardButton(text="💳 Кабинет", callback_data="menu:cabinet"),
        InlineKeyboardButton(text="💬 Поддержка", callback_data="menu:support"),
    )
    return builder.as_markup()


# =============================================================================
# КЛАВИАТУРЫ ДЛЯ /status — управление подпиской
# =============================================================================

def get_subscription_manage_keyboard(
    portal_url: Optional[str] = None,
    has_active_subscription: bool = False,
) -> InlineKeyboardMarkup:
    """
    Клавиатура для управления подпиской.
    - portal_url: ссылка на Stripe Customer Portal (если есть)
    - has_active_subscription: если True, не показываем кнопку "Продлить"
    """
    builder = InlineKeyboardBuilder()
    if portal_url:
        builder.row(
            InlineKeyboardButton(text="⚙️ Управление подпиской", url=portal_url),
        )
    # Кнопку "Продлить" показываем только если подписка НЕ активна
    if not has_active_subscription:
        builder.row(
            InlineKeyboardButton(text="💰 Продлить подписку", callback_data="action:pay"),
        )
    return builder.as_markup()


# =============================================================================
# КЛАВИАТУРЫ ДЛЯ /admin — панель администратора
# =============================================================================

def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """
    Главная панель администратора.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"),
    )
    # builder.row(
    #     InlineKeyboardButton(text="📅 Расписание", callback_data="admin:schedule"),
    # )
    builder.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast_menu"),
    )
    builder.row(
        InlineKeyboardButton(text="� Неактивные участники", callback_data="admin:inactive_participants"),
    )
    builder.row(
        InlineKeyboardButton(text="� Sync CRM", callback_data="admin:sync_crm"),
    )
    builder.row(
        InlineKeyboardButton(text="➕ Добавить юзера", callback_data="admin:add_user"),
    )
    return builder.as_markup()


def get_add_user_duration_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура выбора срока подписки при ручном добавлении пользователя.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 месяц (30 дней)", callback_data="admin:duration:1month"),
    )
    builder.row(
        InlineKeyboardButton(text="3 месяца (90 дней)", callback_data="admin:duration:3months"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="admin:duration:cancel"),
    )
    return builder.as_markup()


def get_stats_detail_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура после статистики — просмотр деталей по статусам.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Активные", callback_data="stats:active"),
        InlineKeyboardButton(text="❌ Истекшие", callback_data="stats:expired"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin:back"),
    )
    return builder.as_markup()


def get_broadcast_segment_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора сегмента рассылки.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👥 Все пользователи", callback_data="broadcast:all"),
    )
    builder.row(
        InlineKeyboardButton(text="🆕 Новые (New)", callback_data="broadcast:new"),
    )
    builder.row(
        InlineKeyboardButton(text="🤔 Думают (Pending)", callback_data="broadcast:pending"),
    )
    builder.row(
        InlineKeyboardButton(text="💭 Пока думаю", callback_data="broadcast:thinking"),
    )
    builder.row(
        InlineKeyboardButton(text="✅ Активные", callback_data="broadcast:active"),
    )
    builder.row(
        InlineKeyboardButton(text="⏰ Истёкшие", callback_data="broadcast:expired"),
    )
    # Сегментация по уровням
    builder.row(
        InlineKeyboardButton(text="🌱 A1-A2", callback_data="broadcast:level:A1-A2"),
        InlineKeyboardButton(text="📚 B1-B2", callback_data="broadcast:level:B1-B2"),
    )
    builder.row(
        InlineKeyboardButton(text="💤 Неактивные (5 встреч)", callback_data="broadcast:inactive_last5_active"),
    )
    builder.row(
        InlineKeyboardButton(text="📉 Неактивные (<5 записей)", callback_data="broadcast:inactive_lt5_active"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast:cancel"),
    )
    return builder.as_markup()


def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения рассылки.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast:confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast:cancel"),
    )
    return builder.as_markup()


# =============================================================================
# КЛАВИАТУРЫ ДЛЯ ЗАПЛАНИРОВАННЫХ РАССЫЛОК
# =============================================================================

def get_broadcast_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Меню рассылки: обычная рассылка, запланированная, история.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📢 Обычная рассылка", callback_data="admin:broadcast"),
    )
    builder.row(
        InlineKeyboardButton(text="🕐 Запланировать рассылку", callback_data="admin:scheduled_broadcast"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 История", callback_data="admin:broadcast_history"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin:back"),
    )
    return builder.as_markup()


def get_scheduled_segment_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора сегмента запланированной рассылки.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👥 Все пользователи", callback_data="sched_seg:all"),
    )
    builder.row(
        InlineKeyboardButton(text="🆕 Новые (New)", callback_data="sched_seg:new"),
    )
    builder.row(
        InlineKeyboardButton(text="🤔 Думают (Pending)", callback_data="sched_seg:pending"),
    )
    builder.row(
        InlineKeyboardButton(text="💭 Пока думаю", callback_data="sched_seg:thinking"),
    )
    builder.row(
        InlineKeyboardButton(text="✅ Активные", callback_data="sched_seg:active"),
    )
    builder.row(
        InlineKeyboardButton(text="⏰ Истёкшие", callback_data="sched_seg:expired"),
    )
    builder.row(
        InlineKeyboardButton(text="🌱 A1-A2", callback_data="sched_seg:level:A1-A2"),
        InlineKeyboardButton(text="📚 B1-B2", callback_data="sched_seg:level:B1-B2"),
    )
    builder.row(
        InlineKeyboardButton(text="💤 Неактивные (5 встреч)", callback_data="sched_seg:inactive_last5_active"),
    )
    builder.row(
        InlineKeyboardButton(text="📉 Неактивные (<5 записей)", callback_data="sched_seg:inactive_lt5_active"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="sched_seg:cancel"),
    )
    return builder.as_markup()


def get_inactive_participants_keyboard(
    page: int,
    total_pages: int,
    has_items: bool,
    segment: str,
    inactivity_days: int,
    missed_events: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    def set_filter_button(text: str, days: int, missed: int) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=text,
            callback_data=f"inactive_participants:set:{max(days, 0)}:{max(missed, 0)}:1",
        )

    builder.row(
        set_filter_button("Дни -1", inactivity_days - 1, missed_events),
        set_filter_button(f"Дни: {inactivity_days}", inactivity_days, missed_events),
        set_filter_button("Дни +1", inactivity_days + 1, missed_events),
    )
    builder.row(
        set_filter_button("Встречи -1", inactivity_days, missed_events - 1),
        set_filter_button(f"Встречи: {missed_events}", inactivity_days, missed_events),
        set_filter_button("Встречи +1", inactivity_days, missed_events + 1),
    )
    builder.row(
        set_filter_button("Сброс дней", 0, missed_events),
        set_filter_button("Сброс встреч", inactivity_days, 0),
    )
    if total_pages > 1:
        nav_buttons = []
        if page > 1:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=f"inactive_participants:page:{segment}:{page - 1}",
                )
            )
        nav_buttons.append(
            InlineKeyboardButton(
                text=f"{page}/{total_pages}",
                callback_data=f"inactive_participants:refresh:{segment}:{page}",
            )
        )
        if page < total_pages:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=f"inactive_participants:page:{segment}:{page + 1}",
                )
            )
        builder.row(*nav_buttons)
    if has_items:
        builder.row(
            InlineKeyboardButton(text="📢 Рассылка", callback_data=f"inactive_participants:broadcast:{segment}"),
        )
    builder.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"inactive_participants:refresh:{segment}:{page}"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin:back"),
    )
    return builder.as_markup()


def get_rsvp_choice_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура: прикрепить RSVP-кнопки к рассылке?
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, добавить кнопки", callback_data="sched_rsvp:yes"),
        InlineKeyboardButton(text="❌ Нет", callback_data="sched_rsvp:no"),
    )
    return builder.as_markup()


def get_scheduled_confirm_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения запланированной рассылки.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Запланировать", callback_data="sched_confirm:yes"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="sched_confirm:cancel"),
    )
    return builder.as_markup()


def get_zoom_link_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура: есть ли ссылка на Zoom?
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Пропустить", callback_data="sched_zoom:skip"),
    )
    return builder.as_markup()


def get_rsvp_buttons_keyboard(broadcast_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура для RSVP в рассылке пользователям.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Я буду", callback_data=f"rsvp:attend:{broadcast_id}"),
        InlineKeyboardButton(text="Не смогу", callback_data=f"rsvp:decline:{broadcast_id}"),
    )
    return builder.as_markup()


def get_rsvp_only_decline_keyboard(broadcast_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура после выбора "Я буду" — остаётся только "Не смогу".
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Не смогу", callback_data=f"rsvp:decline:{broadcast_id}"),
    )
    return builder.as_markup()


def get_rsvp_only_attend_keyboard(broadcast_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура после выбора "Не смогу" — остаётся только "Я буду".
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Я буду", callback_data=f"rsvp:attend:{broadcast_id}"),
    )
    return builder.as_markup()


def get_calendar_keyboard(calendar_url: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для добавления события в Google Calendar.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Добавить", url=calendar_url),
        InlineKeyboardButton(text="Нет", callback_data="rsvp:dismiss_calendar"),
    )
    builder.row(
        InlineKeyboardButton(text="Скрыть", callback_data="rsvp:dismiss_calendar"),
    )
    return builder.as_markup()


def get_broadcast_history_back_keyboard() -> InlineKeyboardMarkup:
    """
    Кнопка назад из истории рассылок.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin:broadcast_menu"),
    )
    return builder.as_markup()


def get_schedule_keyboard(is_subscribed: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура под расписанием.
    Для подписчиков: кнопка "Записаться".
    Для неподписчиков: кнопка тарифов.
    """
    builder = InlineKeyboardBuilder()
    if is_subscribed:
        builder.row(
            InlineKeyboardButton(text="📝 Записаться", callback_data="schedule:signup"),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="Оформить подписку", callback_data="action:pay"),
        )
    return builder.as_markup()


def get_starts1_schedule_keyboard(is_subscribed: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура под расписанием для /starts1.
    Для неподписчиков ведёт в starts1-платёжный сценарий.
    """
    builder = InlineKeyboardBuilder()
    if is_subscribed:
        builder.row(
            InlineKeyboardButton(text="📝 Записаться", callback_data="schedule:signup"),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="Оформить подписку", callback_data="starts1:pay"),
        )
    return builder.as_markup()


# =============================================================================
# КЛАВИАТУРЫ ДЛЯ FEEDBACK — опрос после встречи
# =============================================================================

def get_feedback_start_keyboard(broadcast_id: int) -> InlineKeyboardMarkup:
    """
    Кнопка начала опроса после встречи.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📝 Оставить отзыв",
            callback_data=f"feedback:start:{broadcast_id}",
        ),
    )
    return builder.as_markup()


def get_feedback_rating_keyboard(broadcast_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура для оценки встречи (1-5 звёзд).
    Callback data: feedback:rating:{broadcast_id}:{rating}
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1", callback_data=f"feedback:rating:{broadcast_id}:1"),
        InlineKeyboardButton(text="2", callback_data=f"feedback:rating:{broadcast_id}:2"),
        InlineKeyboardButton(text="3", callback_data=f"feedback:rating:{broadcast_id}:3"),
        InlineKeyboardButton(text="4", callback_data=f"feedback:rating:{broadcast_id}:4"),
        InlineKeyboardButton(text="5", callback_data=f"feedback:rating:{broadcast_id}:5"),
    )
    return builder.as_markup()


def get_feedback_level_keyboard(broadcast_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура для вопроса о комфортности уровня.
    Callback data: feedback:level:{broadcast_id}:{answer}
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Да, идеально",
            callback_data=f"feedback:level:{broadcast_id}:perfect",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🤔 Немного сложно",
            callback_data=f"feedback:level:{broadcast_id}:hard",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🙂 Немного легко",
            callback_data=f"feedback:level:{broadcast_id}:easy",
        ),
    )
    return builder.as_markup()


def get_feedback_next_keyboard(broadcast_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура для вопроса о следующей встрече.
    Callback data: feedback:next:{broadcast_id}:{answer}
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="👌 Возможно",
            callback_data=f"feedback:next:{broadcast_id}:maybe",
        ),
        InlineKeyboardButton(
            text="❌ Нет",
            callback_data=f"feedback:next:{broadcast_id}:no",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔥 Да",
            callback_data=f"feedback:next:{broadcast_id}:yes",
        ),
    )
    return builder.as_markup()


def get_feedback_thanks_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура после завершения опроса — кнопка Расписание.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Расписание", callback_data="action:schedule"),
    )
    return builder.as_markup()


def get_followup_schedule_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для follow-up сообщений — кнопка Расписание.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Расписание", callback_data="action:schedule"),
    )
    return builder.as_markup()


def get_group_join_check_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для проверки входа в группу после покупки.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Да", callback_data="group_join:yes"),
        InlineKeyboardButton(text="Нет", callback_data="group_join:no"),
    )
    return builder.as_markup()


def get_event_navigation_keyboard(
    event_index: int,
    total_events: int,
    broadcast_id: int,
    is_registered: bool = False,
) -> InlineKeyboardMarkup:
    """
    Клавиатура для навигации по событиям с кнопкой записи.
    
    Args:
        event_index: Текущий индекс события (0-based)
        total_events: Общее количество событий
        broadcast_id: ID события для записи
        is_registered: Уже записан ли пользователь
    """
    builder = InlineKeyboardBuilder()
    
    # Первый ряд: Назад и Дальше
    nav_buttons = []
    if event_index > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"event:nav:{event_index-1}")
        )
    if event_index < total_events - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="Дальше ▶️", callback_data=f"event:nav:{event_index+1}")
        )
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    # Второй ряд: Записаться (красная кнопка) или статус
    if is_registered:
        builder.row(
            InlineKeyboardButton(text="✅ Вы записаны", callback_data=f"rsvp:decline:{broadcast_id}")
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="Записаться",
                callback_data=f"rsvp:attend:{broadcast_id}",
                style="danger"
            )
        )
    
    return builder.as_markup()


# =============================================================================
# КЛАВИАТУРЫ ДЛЯ /starts — НОВЫЙ ОНБОРДИНГ (A/B тестирование)
# =============================================================================

def get_starts_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для нового онбординга /starts.
    Красная кнопка тарифов, расписание и менеджер.
    """
    builder = InlineKeyboardBuilder()
    
    # Первая кнопка - красная (основная кнопка тарифов)
    builder.row(
        InlineKeyboardButton(
            text="Узнать тарифы и вступить",
            callback_data="action:pay",
            style="danger"
        ),
    )
    
    # Вторая кнопка - расписание
    builder.row(
        InlineKeyboardButton(
            text="Расписание встреч 🗓",
            callback_data="action:schedule"
        ),
    )
    
    # Третья кнопка - вопрос менеджеру
    builder.row(
        InlineKeyboardButton(
            text="Есть вопрос? (Задать менеджеру)",
            url=ULTIMAGREGO_URL
        ),
    )
    
    return builder.as_markup()


def get_starts1_state_keyboard() -> InlineKeyboardMarkup:
    """Компактная клавиатура выбора состояния для /starts1."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1", callback_data="starts1:state:1"),
        InlineKeyboardButton(text="2", callback_data="starts1:state:2"),
        InlineKeyboardButton(text="3", callback_data="starts1:state:3"),
    )
    return builder.as_markup()


def get_starts1_cta_keyboard() -> InlineKeyboardMarkup:
    """CTA-клавиатура для веток /starts1."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🗓 Расписание и тарифы",
            callback_data="starts1:offer",
            style="danger",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="Больше информации",
            callback_data="starts1:more_info",
        ),
    )
    return builder.as_markup()
