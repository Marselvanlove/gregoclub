# Обработчики онбординга — знакомство с Grego Club
import asyncio
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ChatAction
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states import OnboardingStates
from bot.keyboards import get_main_reply_keyboard
from utils.config import Config
from utils.promo import maybe_send_promo
from services.openai_demo import generate_demo_response, generate_voice_response, get_fallback_response, translate_to_russian
from database.requests import is_demo_completed, mark_demo_completed
from bot.texts import ONBOARDING_STEP_1, ONBOARDING_STEP_2, ONBOARDING_STEP_3

logger = logging.getLogger(__name__)

router = Router(name="onboarding")

MAX_DEMO_TURNS = 3

# Таймаут для автоотправки "Узнать больше" (в секундах)
# Тестово: 20 сек, в продакшене: 40 минут = 2400 сек
AUTO_LEARN_MORE_TIMEOUT = 20

# Таймауты для шагов онбординга (в секундах)
# Тестово: 10/20 сек, в продакшене: 15 мин = 900 сек, 30 мин = 1800 сек
ONBOARDING_STEP_1_TIMEOUT = 10  # 900 в продакшене
ONBOARDING_STEP_2_TIMEOUT = 10  # 1800 в продакшене

# Хранилище активных таймеров (chat_id -> task)
_pending_auto_sends: dict[int, asyncio.Task] = {}

# Хранилище таймеров онбординга (chat_id -> task)
_pending_onboarding_steps: dict[int, asyncio.Task] = {}

# 📸 ФОТО: отправить grego_club_main.jpg ПЕРЕД этим текстом
ONBOARDING_INTRO = """Привет, {first_name}.

Это Grego Club — закрытый разговорный клуб для практики испанского.

4 спикинга в неделю с носителями. 40–60 минут живого общения.

Без учебников. Без домашки. Только разговорная практика."""

# 📸 ФОТО: отправить grego_includes_1.jpg (спикинги + база знаний) ПЕРЕД этим текстом
ONBOARDING_WHAT_IS_CLUB = """Что входит в подписку:

**Спикинги по уровням**
4 раза в неделю. 40–60 минут с носителем. Выбираете уровень, тему и время.

**База знаний**
Готовые фразы для реальных ситуаций: полиция, банк, врач, школа. Обновляется ежемесячно."""

# Второе сообщение (отправляется через 3 секунды)
# 📸 ФОТО: отправить grego_includes_2.jpg (встречи + ИИ-ассистент) ПЕРЕД этим текстом
ONBOARDING_ECOSYSTEM = """**Закрытые встречи с профессионалами**
Полицейские, адвокаты, медики. Разбор реальных ситуаций и практика языка.

**AI-ассистент GregoChat**
Тренирует речь, помогает с формулировками, симулирует диалоги. Доступ 24/7."""

ONBOARDING_DEMO_INTRO = """Попробуйте GregoChat AI.

Бот отвечает голосом. Запишите голосовое сообщение на испанском.

Пример: «¡Hola mi amigo Grego!»"""

ONBOARDING_DEMO_END = """Демо завершено.

В полной версии: безлимитные диалоги, практика произношения, перевод фото и текстов."""

ONBOARDING_LEVEL_QUESTION = """Какой у вас уровень испанского?

Это поможет нам подобрать подходящие спикинги."""

# Первая реплика Grego для старта демо
GREGO_FIRST_LINE = "¡Hola, amigo! ¡Qué alegría verte por aquí! Llevo más de veinticinco años viviendo en Madrid con mi familia. ¿Qué tal? ¿Cómo estás?"
GREGO_FIRST_LINE_RU = "Привет, друг! Как я рад тебя видеть! Живу в Мадриде уже больше двадцати пяти лет с семьёй. Как дела? Как ты?"


def get_onboarding_intro_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎯 Узнать больше", callback_data="onb:learn_more"))
    builder.row(InlineKeyboardButton(text="💳 Сразу к тарифам", callback_data="onb:tariffs"))
    return builder.as_markup()


def get_next_step_keyboard(step: int):
    """Клавиатура с кнопкой Далее для онбординга."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Далее →", callback_data=f"onb:next:{step}"))
    return builder.as_markup()


def get_onboarding_demo_keyboard(demo_available: bool = True):
    """Keyboard with or without demo button depending on demo_available."""
    builder = InlineKeyboardBuilder()
    if demo_available:
        builder.row(InlineKeyboardButton(text="🤖 Попробовать AI", callback_data="onb:start_demo"))
    builder.row(InlineKeyboardButton(text="💳 Тарифы", callback_data="onb:tariffs"))
    return builder.as_markup()


def get_level_keyboard():
    """Клавиатура выбора уровня испанского."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🌱 A1-A2", callback_data="onb:level:A1-A2"),
        InlineKeyboardButton(text="📚 B1-B2", callback_data="onb:level:B1-B2"),
    )
    return builder.as_markup()


def get_show_text_keyboard():
    """Клавиатура под аудио: только кнопка Текст."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👁 Покажи текст", callback_data="onb:show_text"))
    return builder.as_markup()


def get_show_translation_keyboard():
    """Клавиатура под испанским текстом: кнопка Перевод."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🌐 Перевод", callback_data="onb:translate"))
    return builder.as_markup()


def get_show_spanish_keyboard():
    """Клавиатура под русским переводом: кнопка Текст."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📝 Текст", callback_data="onb:spanish"))
    return builder.as_markup()


def get_onboarding_after_demo_keyboard(gregochat_username="GregoChat_bot"):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 Расписание", callback_data="onb:schedule"))
    builder.row(InlineKeyboardButton(text="💳 Тарифы", callback_data="onb:tariffs"))
    return builder.as_markup()


def get_after_schedule_keyboard(gregochat_username="GregoChat_bot"):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🤖 GregoChat", url=f"https://t.me/{gregochat_username}"))
    builder.row(InlineKeyboardButton(text="💳 Тарифы", callback_data="onb:tariffs"))
    return builder.as_markup()


async def _send_learn_more_content(bot, chat_id: int, config, session):
    """
    Отправляет контент 'Узнать больше' (2 фото с описаниями).
    Используется как для callback, так и для автоотправки.
    """
    # Кнопка демо всегда доступна (ограничение отключено)
    demo_done = False  # await is_demo_completed(session, chat_id)
    
    # 📸 Первое фото: спикинги + база знаний
    if config.includes_photo_1_id:
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=config.includes_photo_1_id,
                caption=ONBOARDING_WHAT_IS_CLUB,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Фото 1 не отправлено: {e}")
            await bot.send_message(chat_id, ONBOARDING_WHAT_IS_CLUB, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id, ONBOARDING_WHAT_IS_CLUB, parse_mode="Markdown")
    
    await asyncio.sleep(2)
    
    # 📸 Второе фото: встречи + ИИ-ассистент
    if config.includes_photo_2_id:
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=config.includes_photo_2_id,
                caption=ONBOARDING_ECOSYSTEM,
                reply_markup=get_onboarding_demo_keyboard(demo_available=not demo_done),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Фото 2 не отправлено: {e}")
            await bot.send_message(
                chat_id,
                ONBOARDING_ECOSYSTEM,
                reply_markup=get_onboarding_demo_keyboard(demo_available=not demo_done),
                parse_mode="Markdown"
            )
    else:
        await bot.send_message(
            chat_id,
            ONBOARDING_ECOSYSTEM,
            reply_markup=get_onboarding_demo_keyboard(demo_available=not demo_done),
            parse_mode="Markdown"
        )


async def _auto_send_learn_more(bot, chat_id: int, buttons_message_id: int, config, session):
    """
    Фоновая задача: ждёт таймаут, затем удаляет кнопки и отправляет контент.
    """
    try:
        await asyncio.sleep(AUTO_LEARN_MORE_TIMEOUT)
        
        # Удаляем сообщение с кнопками
        try:
            await bot.delete_message(chat_id, buttons_message_id)
        except Exception as e:
            logger.debug(f"Не удалось удалить сообщение с кнопками: {e}")
        
        # Отправляем контент "Узнать больше"
        await _send_learn_more_content(bot, chat_id, config, session)
        logger.info(f"Автоотправка 'Узнать больше' для chat_id={chat_id}")
        
    except asyncio.CancelledError:
        # Задача отменена — пользователь нажал кнопку
        logger.debug(f"Автоотправка отменена для chat_id={chat_id}")
    finally:
        # Удаляем задачу из хранилища
        _pending_auto_sends.pop(chat_id, None)


def cancel_auto_send(chat_id: int):
    """Отменяет автоотправку для пользователя (вызывается при нажатии кнопки)."""
    task = _pending_auto_sends.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


def cancel_onboarding_step(chat_id: int):
    """Отменяет таймер шага онбординга."""
    task = _pending_onboarding_steps.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


# Фото ID для онбординга (глобальные константы)
PHOTO_STEP_1 = "AgACAgIAAxkBAAICr2l8vHrYVjNgUZsPipp7vhngwwZ4AAKFD2sbm2bhS6y7l5oqyY3sAQADAgADeQADOAQ"
PHOTO_STEP_2 = "AgACAgIAAxkBAAICsWl8vIjCXB2ekbm7ZGXolfpWL_KGAAI2EGsbN07oS98vmeM_unjsAQADAgADeQADOAQ"
PHOTO_STEP_3_1 = "AgACAgIAAxkBAAIB1Wl7iZaw6xKrPzzkHq1QDCs3yWPLAAJ2F2sbnOzZS1-jyglb1YMsAQADAgADeQADOAQ"
PHOTO_STEP_3_2 = "AgACAgIAAxkBAAIB12l7ibWye1o9pWGTQvdaOTL1fFkHAAJ4F2sbnOzZS1usE6zArKTIAQADAgADeQADOAQ"


async def send_onboarding_step_2(bot, chat_id: int):
    """Отправляет шаг 2 онбординга."""
    try:
        await bot.send_photo(
            chat_id=chat_id,
            photo=PHOTO_STEP_2,
            caption=ONBOARDING_STEP_2,
            reply_markup=get_next_step_keyboard(2),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Фото шаг 2 не отправлено: {e}")
        await bot.send_message(chat_id, ONBOARDING_STEP_2, reply_markup=get_next_step_keyboard(2), parse_mode="Markdown")
    
    # Запускаем таймер для шага 3
    task = asyncio.create_task(_auto_send_step_3(bot, chat_id))
    _pending_onboarding_steps[chat_id] = task


async def send_onboarding_step_3(bot, chat_id: int):
    """Отправляет шаг 3 онбординга (финальный)."""
    from aiogram.types import InputMediaPhoto
    media_group = [
        InputMediaPhoto(media=PHOTO_STEP_3_1),
        InputMediaPhoto(media=PHOTO_STEP_3_2),
    ]
    try:
        await bot.send_media_group(chat_id=chat_id, media=media_group)
    except Exception as e:
        logger.warning(f"Фото шаг 3 не отправлены: {e}")
    
    await bot.send_message(
        chat_id,
        ONBOARDING_STEP_3,
        reply_markup=get_onboarding_demo_keyboard(demo_available=True),
        parse_mode="Markdown"
    )


async def _auto_send_step_2(bot, chat_id: int):
    """Автоотправка шага 2 через таймаут."""
    try:
        await asyncio.sleep(ONBOARDING_STEP_1_TIMEOUT)
        await send_onboarding_step_2(bot, chat_id)
        logger.info(f"Автоотправка шага 2 для chat_id={chat_id}")
    except asyncio.CancelledError:
        logger.debug(f"Таймер шага 2 отменён для chat_id={chat_id}")
    finally:
        _pending_onboarding_steps.pop(chat_id, None)


async def _auto_send_step_3(bot, chat_id: int):
    """Автоотправка шага 3 через таймаут."""
    try:
        await asyncio.sleep(ONBOARDING_STEP_2_TIMEOUT)
        await send_onboarding_step_3(bot, chat_id)
        logger.info(f"Автоотправка шага 3 для chat_id={chat_id}")
    except asyncio.CancelledError:
        logger.debug(f"Таймер шага 3 отменён для chat_id={chat_id}")
    finally:
        _pending_onboarding_steps.pop(chat_id, None)


async def start_onboarding(message, session, config, state):
    """
    Новый онбординг: 3 шага с фото и кнопками Далее.
    """
    user = message.from_user
    if not user:
        return
    
    chat_id = message.chat.id
    
    # Отменяем предыдущие таймеры
    cancel_auto_send(chat_id)
    cancel_onboarding_step(chat_id)
    
    # Показываем reply keyboard (постоянное меню внизу)
    await message.answer("👋", reply_markup=get_main_reply_keyboard())
    
    # Шаг 1: Что такое Grego Club + кнопка Далее
    try:
        await message.answer_photo(
            photo=PHOTO_STEP_1,
            caption=ONBOARDING_STEP_1,
            reply_markup=get_next_step_keyboard(1),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Фото шаг 1 не отправлено: {e}")
        await message.answer(ONBOARDING_STEP_1, reply_markup=get_next_step_keyboard(1), parse_mode="Markdown")
    
    # Запускаем таймер автоотправки шага 2
    task = asyncio.create_task(_auto_send_step_2(message.bot, chat_id))
    _pending_onboarding_steps[chat_id] = task


@router.callback_query(F.data == "onb:learn_more")
async def callback_learn_more(callback, session, config):
    """Узнать больше — показываем 2 фото с описанием подписки."""
    await callback.answer()
    
    chat_id = callback.message.chat.id
    
    # Отменяем таймер автоотправки
    cancel_auto_send(chat_id)
    
    # Удаляем предыдущее сообщение с кнопками
    try:
        await callback.message.delete()
    except:
        pass
    
    # Отправляем контент через общую функцию
    await _send_learn_more_content(callback.bot, chat_id, config, session)


@router.callback_query(F.data.startswith("onb:next:"))
async def callback_next_step(callback):
    """Обработчик кнопки Далее для шагов онбординга."""
    await callback.answer()
    
    chat_id = callback.message.chat.id
    step = int(callback.data.split(":")[-1])
    
    # Отменяем таймер автоотправки
    cancel_onboarding_step(chat_id)
    
    if step == 1:
        # Переход к шагу 2
        await send_onboarding_step_2(callback.bot, chat_id)
    elif step == 2:
        # Переход к шагу 3 (финальный)
        await send_onboarding_step_3(callback.bot, chat_id)


@router.callback_query(F.data == "onb:start_demo")
async def callback_start_demo(callback, session, config, state):
    """Запуск демо — Grego ПЕРВЫМ отправляет аудио-приветствие."""
    await callback.answer()
    
    # Проверка на повторное демо отключена — можно пробовать сколько угодно
    # demo_done = await is_demo_completed(session, callback.from_user.id)
    # if demo_done:
    #     await callback.message.answer(
    #         "Демо уже пройдено! Для безлимитного доступа оформи подписку 👇",
    #         reply_markup=get_onboarding_after_demo_keyboard(config.gregochat_bot_username),
    #     )
    #     return
    
    chat_id = callback.message.chat.id
    
    # Удаляем предыдущее сообщение
    try:
        await callback.message.delete()
    except:
        pass
    
    # Отправляем вводный текст
    await callback.message.answer(ONBOARDING_DEMO_INTRO, parse_mode="Markdown")
    
    # Анимация "записывает аудио"
    await callback.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
    
    # Генерируем первое аудио-приветствие от Grego (ASYNC!)
    voice_audio = None
    if config.elevenlabs_api_key:
        voice_audio = await generate_voice_response(
            config.elevenlabs_api_key,
            GREGO_FIRST_LINE,
            config.grego_voice_id,
        )
    
    # Отправляем голосовое сообщение с кнопкой "Текст"
    if voice_audio:
        audio_file = BufferedInputFile(voice_audio, filename="grego.mp3")
        await callback.message.answer_voice(
            voice=audio_file,
            reply_markup=get_show_text_keyboard(),
        )
    else:
        # Fallback: текстовое сообщение
        await callback.message.answer(
            f"📝 **Текст:**\n\n{GREGO_FIRST_LINE}",
            parse_mode="Markdown",
            reply_markup=get_show_translation_keyboard(),
        )
    
    # Сохраняем состояние демо (turn=2, т.к. первая реплика уже отправлена)
    await state.update_data(
        demo_turn=2,
        last_spanish_text=GREGO_FIRST_LINE,
        last_russian_text=GREGO_FIRST_LINE_RU,
    )
    await state.set_state(OnboardingStates.demo_ai_active)
    
    logger.info(f"[onboarding] Демо запущено, первое аудио отправлено")


@router.callback_query(F.data == "onb:show_text")
async def callback_show_text(callback, state, config):
    """Показать испанский текст (новое сообщение с кнопкой Перевод)."""
    await callback.answer()
    
    # Убираем кнопку "Покажи текст" с аудио
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
    data = await state.get_data()
    spanish_text = data.get("last_spanish_text", "")
    
    if not spanish_text:
        spanish_text = "Texto no disponible"
    
    # Отправляем новое сообщение с испанским текстом
    await callback.message.answer(
        f"📝 **Текст:**\n\n{spanish_text}",
        parse_mode="Markdown",
        reply_markup=get_show_translation_keyboard(),
    )


@router.callback_query(F.data == "onb:translate")
async def callback_translate(callback, state, config):
    """Перевод — РЕДАКТИРУЕМ текущее сообщение на русский."""
    await callback.answer()
    
    data = await state.get_data()
    russian_text = data.get("last_russian_text", "")
    spanish_text = data.get("last_spanish_text", "")
    
    # Если перевода нет или он placeholder — переводим через AI
    if not russian_text or russian_text.startswith("(Перевод"):
        if config.openai_api_key and spanish_text:
            russian_text = await translate_to_russian(config.openai_api_key, spanish_text)
            # Сохраняем перевод в state
            await state.update_data(last_russian_text=russian_text)
        else:
            russian_text = "Перевод недоступен"
    
    # РЕДАКТИРУЕМ текущее сообщение (не отправляем новое!)
    await callback.message.edit_text(
        f"🌐 **Перевод:**\n\n{russian_text}",
        parse_mode="Markdown",
        reply_markup=get_show_spanish_keyboard(),
    )


@router.callback_query(F.data == "onb:spanish")
async def callback_spanish(callback, state, config):
    """Текст — РЕДАКТИРУЕМ текущее сообщение обратно на испанский."""
    await callback.answer()
    
    data = await state.get_data()
    spanish_text = data.get("last_spanish_text", "")
    
    if not spanish_text:
        spanish_text = "Texto no disponible"
    
    # РЕДАКТИРУЕМ текущее сообщение (не отправляем новое!)
    await callback.message.edit_text(
        f"📝 **Текст:**\n\n{spanish_text}",
        parse_mode="Markdown",
        reply_markup=get_show_translation_keyboard(),
    )


@router.callback_query(F.data == "onb:skip_demo")
async def callback_skip_demo(callback, config, state):
    await callback.answer()
    await state.clear()
    await callback.message.answer(ONBOARDING_DEMO_END, reply_markup=get_onboarding_after_demo_keyboard(config.gregochat_bot_username), parse_mode="Markdown")


@router.message(OnboardingStates.demo_ai_active)
async def handle_demo_message(message, session, config, state):
    """Обработка ответа пользователя в демо."""
    user_text = message.text or ""
    data = await state.get_data()
    turn = data.get("demo_turn", 1)
    chat_id = message.chat.id
    
    # Анимация "печатает"
    await message.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    
    # Генерируем текстовый ответ AI
    if config.openai_api_key:
        response = await generate_demo_response(config.openai_api_key, user_text, turn, MAX_DEMO_TURNS)
    else:
        response = get_fallback_response(turn)
    
    # Простой перевод (TODO: можно добавить AI перевод)
    russian_translation = f"(Перевод реплики {turn})"
    
    # Анимация "записывает аудио"
    await message.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
    
    # Генерируем голосовой ответ через ElevenLabs (ASYNC!)
    voice_audio = None
    if config.elevenlabs_api_key:
        voice_audio = await generate_voice_response(
            config.elevenlabs_api_key,
            response,
            config.grego_voice_id,
        )
    
    # Отправляем голосовое сообщение с кнопкой "Текст"
    if voice_audio:
        audio_file = BufferedInputFile(voice_audio, filename="grego.mp3")
        await message.answer_voice(
            voice=audio_file,
            reply_markup=get_show_text_keyboard(),
        )
    else:
        await message.answer(
            f"📝 **Текст:**\n\n{response}",
            parse_mode="Markdown",
            reply_markup=get_show_translation_keyboard(),
        )
    
    # Сохраняем тексты для кнопок
    await state.update_data(
        last_spanish_text=response,
        last_russian_text=russian_translation,
    )
    
    # Проверяем, закончено ли демо
    if turn >= MAX_DEMO_TURNS:
        # Помечаем демо как завершённое в БД (чтобы не тратить токены повторно)
        await mark_demo_completed(session, message.from_user.id)
        # НЕ очищаем state сразу - пользователь может нажать "Покажи текст"
        await state.update_data(demo_finished=True)
        await asyncio.sleep(1)
        await message.answer(ONBOARDING_DEMO_END, parse_mode="Markdown")
        await asyncio.sleep(1)
        # Спрашиваем уровень испанского
        await message.answer(ONBOARDING_LEVEL_QUESTION, reply_markup=get_level_keyboard(), parse_mode="Markdown")
    else:
        await state.update_data(demo_turn=turn + 1)


@router.callback_query(F.data == "onb:schedule")
async def callback_onb_schedule(callback, session, config):
    from bot.handlers.user import build_smart_schedule
    await callback.answer()
    schedule_text, _ = await build_smart_schedule(session, callback.from_user.id)
    await callback.message.edit_text(
        schedule_text,
        reply_markup=get_after_schedule_keyboard(config.gregochat_bot_username),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "onb:tariffs")
async def callback_onb_tariffs(callback, config):
    """Показ тарифов с фото цен."""
    from bot.keyboards import get_tariff_keyboard
    from bot.texts import TARIFF_SELECT
    await callback.answer()
    
    # Отменяем таймер автоотправки
    cancel_auto_send(callback.message.chat.id)
    
    # Удаляем предыдущее сообщение
    try:
        await callback.message.delete()
    except:
        pass
    
    # 📸 Отправляем фото с ценами
    if config.prices_photo_id:
        try:
            await callback.message.answer_photo(
                photo=config.prices_photo_id,
                caption=TARIFF_SELECT,
                reply_markup=get_tariff_keyboard(config.price_1_month, config.price_3_months, config.price_6_months),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Фото цен не отправлено: {e}")
            await callback.message.answer(
                TARIFF_SELECT,
                reply_markup=get_tariff_keyboard(config.price_1_month, config.price_3_months, config.price_6_months),
                parse_mode="HTML"
            )
    else:
        await callback.message.answer(
            TARIFF_SELECT,
            reply_markup=get_tariff_keyboard(config.price_1_month, config.price_3_months, config.price_6_months),
            parse_mode="HTML"
        )
    asyncio.create_task(maybe_send_promo(callback.message.bot, callback.message.chat.id))


@router.callback_query(F.data.startswith("onb:level:"))
async def callback_select_level(callback, session, config):
    """Обработка выбора уровня испанского."""
    from database.requests import update_user_language_level
    from bot.keyboards import get_tariff_keyboard
    from bot.texts import TARIFF_SELECT
    
    await callback.answer()
    
    level = callback.data.split(":")[2]  # A1-A2, B1-B2, C1+ или skip
    
    # Сохраняем уровень в БД (если не пропущен)
    if level != "skip":
        await update_user_language_level(session, callback.from_user.id, level)
    
    # Удаляем сообщение с выбором уровня
    try:
        await callback.message.delete()
    except:
        pass
    
    # Показываем тарифы
    if config.prices_photo_id:
        try:
            await callback.message.answer_photo(
                photo=config.prices_photo_id,
                caption=TARIFF_SELECT,
                reply_markup=get_tariff_keyboard(config.price_1_month, config.price_3_months, config.price_6_months),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Фото цен не отправлено: {e}")
            await callback.message.answer(
                TARIFF_SELECT,
                reply_markup=get_tariff_keyboard(config.price_1_month, config.price_3_months, config.price_6_months),
                parse_mode="HTML"
            )
    else:
        await callback.message.answer(
            TARIFF_SELECT,
            reply_markup=get_tariff_keyboard(config.price_1_month, config.price_3_months, config.price_6_months),
            parse_mode="HTML"
        )
    asyncio.create_task(maybe_send_promo(callback.message.bot, callback.message.chat.id))
