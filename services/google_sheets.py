# Логика работы с Google Sheets (gspread): синхронизация данных пользователей
# Согласно разделу 6 ТЗ: Telegram ID, Username, Имя, Дата регистрации,
# Уровень языка, Статус, Дата окончания подписки, LTV

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Sequence

import gspread
from google.oauth2.service_account import Credentials

from database.models import User, UserStatus
from utils.config import Config

logger = logging.getLogger(__name__)

# Области доступа для Google Sheets API
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Заголовки таблицы (по ТЗ раздел 6)
HEADERS = [
    "Telegram ID",
    "Username",
    "Имя",
    "Дата регистрации",
    "Уровень языка",
    "Статус",
    "Дата окончания подписки",
    "LTV",
    "Версия онбординга",
    "Источник входа",
    "Последнее событие",
    "Время последнего события",
    "Выбранное состояние",
    "Платёжный провайдер",
    "Первая оплата",
    "Первый RSVP",
    "Первый feedback",
    "Stuck bucket",
]

# Маппинг статусов для человекочитаемого вида
STATUS_LABELS = {
    UserStatus.new: "Новый",
    UserStatus.pending: "Думает",
    UserStatus.active: "Платит",
    UserStatus.expired: "Отвалился",
}


def init_google_sheets(config: Config) -> gspread.Client:
    """
    Инициализирует клиент Google Sheets с использованием Service Account.
    
    Возвращает gspread.Client для дальнейших операций.
    """
    credentials = Credentials.from_service_account_file(
        config.google_creds_file,
        scopes=SCOPES,
    )
    client = gspread.authorize(credentials)
    logger.info("Google Sheets клиент инициализирован")
    return client


def get_or_create_worksheet(
    client: gspread.Client,
    sheet_id: str,
    worksheet_name: str = "CRM",
) -> gspread.Worksheet:
    """
    Получает или создаёт лист в таблице.
    Если листа нет — создаёт его и добавляет заголовки.
    Если лист есть, но заголовки отсутствуют — добавляет их.
    """
    spreadsheet = client.open_by_key(sheet_id)
    
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
        # Проверяем, есть ли заголовки (первая строка)
        first_row = worksheet.row_values(1)
        if not first_row or first_row != HEADERS:
            # Заголовков нет или они неправильные — добавляем/обновляем
            worksheet.update("A1", [HEADERS])
            logger.info(f"Заголовки добавлены/обновлены на листе '{worksheet_name}'")
    except gspread.WorksheetNotFound:
        # Создаём новый лист
        worksheet = spreadsheet.add_worksheet(
            title=worksheet_name,
            rows=1000,
            cols=len(HEADERS),
        )
        # Добавляем заголовки
        worksheet.update("A1", [HEADERS])
        logger.info(f"Создан новый лист '{worksheet_name}' с заголовками")
    
    return worksheet


def _format_datetime(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    return value.strftime("%d.%m.%Y %H:%M")


def _column_letter(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _build_crm_row(
    user: User,
    ltv: float = 0.0,
    analytics_profile=None,
) -> list[str]:
    reg_date = user.registration_date.strftime("%d.%m.%Y") if user.registration_date else ""
    end_date = user.subscription_end_date.strftime("%d.%m.%Y") if user.subscription_end_date else ""

    return [
        str(user.telegram_id),
        user.username or "",
        user.full_name or "",
        reg_date,
        user.language_level or "",
        STATUS_LABELS.get(user.status, str(user.status.value)),
        end_date,
        f"{ltv:.2f}" if ltv > 0 else "",
        getattr(analytics_profile, "onboarding_version", "") or "",
        getattr(analytics_profile, "entry_source", "") or "",
        getattr(analytics_profile, "last_event", "") or "",
        _format_datetime(getattr(analytics_profile, "last_event_at", None)),
        getattr(analytics_profile, "state_choice", "") or "",
        getattr(analytics_profile, "payment_provider", "") or "",
        _format_datetime(getattr(analytics_profile, "first_paid_at", None)),
        _format_datetime(getattr(analytics_profile, "first_rsvp_at", None)),
        _format_datetime(getattr(analytics_profile, "first_feedback_at", None)),
        getattr(analytics_profile, "stuck_bucket", "") or "",
    ]


def _upsert_user_in_crm_sync(
    client: gspread.Client,
    config: Config,
    user: User,
    ltv: float = 0.0,
    analytics_profile=None,
) -> None:
    worksheet = get_or_create_worksheet(client, config.google_sheet_id)
    row = _build_crm_row(user, ltv, analytics_profile=analytics_profile)
    telegram_id = str(user.telegram_id)
    telegram_ids = worksheet.col_values(1)

    row_index = None
    for index, value in enumerate(telegram_ids[1:], start=2):
        if value == telegram_id:
            row_index = index
            break

    if row_index is None:
        worksheet.append_row(row)
        logger.info("CRM append user=%s status=%s", user.telegram_id, row[5])
        return

    last_column = _column_letter(len(HEADERS))
    worksheet.update(f"A{row_index}:{last_column}{row_index}", [row])
    logger.info("CRM update user=%s status=%s row=%s", user.telegram_id, row[5], row_index)


async def upsert_user_in_crm(
    client: gspread.Client,
    config: Config,
    user: User,
    ltv: float = 0.0,
    analytics_profile=None,
) -> None:
    await asyncio.to_thread(_upsert_user_in_crm_sync, client, config, user, ltv, analytics_profile)


async def sync_users_to_sheets(
    client: gspread.Client,
    config: Config,
    users: Sequence[User],
    ltv_map: Dict[int, float],
    analytics_profile_map: Optional[Dict[int, object]] = None,
) -> int:
    """
    Синхронизирует данные пользователей в Google Sheets.
    
    Оптимизировано для большого количества пользователей (batch_update).
    
    Параметры:
    - users: список пользователей из БД
    - ltv_map: словарь {user_id: ltv_сумма}
    
    Возвращает количество записанных строк.
    """
    worksheet = get_or_create_worksheet(client, config.google_sheet_id)
    
    # Формируем данные для записи
    rows = []
    for user in users:
        # Получаем LTV
        ltv = ltv_map.get(user.id, 0.0)
        analytics_profile = analytics_profile_map.get(user.telegram_id) if analytics_profile_map else None

        row = _build_crm_row(user, ltv, analytics_profile=analytics_profile)
        rows.append(row)
    
    if not rows:
        logger.info("Нет данных для синхронизации")
        return 0
    
    # Расширяем лист если нужно (для большого кол-ва пользователей)
    current_rows = worksheet.row_count
    needed_rows = len(rows) + 10  # +10 запас
    if current_rows < needed_rows:
        worksheet.add_rows(needed_rows - current_rows)
        logger.info(f"Расширен лист до {needed_rows} строк")
    
    # Используем batch_update для оптимизации (1 API вызов вместо множества)
    # Очищаем и записываем в одном запросе
    last_column = _column_letter(len(HEADERS))
    clear_range = f"A2:{last_column}{max(current_rows, needed_rows)}"
    data_range = f"A2:{last_column}{len(rows) + 1}"
    
    worksheet.batch_update([
        {
            'range': clear_range,
            'values': [[""] * len(HEADERS)] * (max(current_rows, needed_rows) - 1),
        },
        {
            'range': data_range,
            'values': rows,
        },
    ])
    
    logger.info(f"Синхронизировано {len(rows)} пользователей в Google Sheets (batch)")
    return len(rows)


async def append_user_to_sheets(
    client: gspread.Client,
    config: Config,
    user: User,
    ltv: float = 0.0,
    analytics_profile=None,
) -> None:
    """
    Добавляет одного пользователя в конец таблицы.
    Используется для быстрого добавления нового пользователя.
    """
    worksheet = get_or_create_worksheet(client, config.google_sheet_id)
    
    row = _build_crm_row(user, ltv, analytics_profile=analytics_profile)
    
    worksheet.append_row(row)
    logger.debug(f"Добавлен пользователь {user.telegram_id} в Google Sheets")


FUNNEL_HEADERS = [
    "Дата события",
    "Telegram ID",
    "Username",
    "Имя",
    "Этап CRM",
    "Событие",
    "Детали",
]


def get_or_create_funnel_worksheet(
    client: gspread.Client,
    sheet_id: str,
    worksheet_name: str = "Воронка",
) -> gspread.Worksheet:
    spreadsheet = client.open_by_key(sheet_id)

    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
        first_row = worksheet.row_values(1)
        if not first_row or first_row != FUNNEL_HEADERS:
            worksheet.update("A1", [FUNNEL_HEADERS])
            logger.info(f"Заголовки добавлены на лист '{worksheet_name}'")
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=worksheet_name,
            rows=1000,
            cols=len(FUNNEL_HEADERS),
        )
        worksheet.update("A1", [FUNNEL_HEADERS])
        logger.info(f"Создан новый лист '{worksheet_name}' с заголовками")

    return worksheet


def _add_funnel_event_to_sheets_sync(
    client: gspread.Client,
    config: Config,
    user: User,
    event_name: str,
    details: str = "",
) -> None:
    worksheet = get_or_create_funnel_worksheet(client, config.google_sheet_id)
    row = [
        datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        str(user.telegram_id),
        user.username or "",
        user.full_name or "",
        STATUS_LABELS.get(user.status, str(user.status.value)),
        event_name,
        details,
    ]
    worksheet.append_row(row)
    logger.info("Funnel event user=%s stage=%s event=%s", user.telegram_id, row[4], event_name)


async def add_funnel_event_to_sheets(
    client: gspread.Client,
    config: Config,
    user: User,
    event_name: str,
    details: str = "",
) -> None:
    await asyncio.to_thread(_add_funnel_event_to_sheets_sync, client, config, user, event_name, details)


# =============================================================================
# Лист "Покупатели" — только оплатившие пользователи
# =============================================================================

# Заголовки для листа покупателей
BUYERS_HEADERS = [
    "Имя",
    "Username", 
    "Telegram ID",
    "Дата покупки",
    "Сумма",
]


def get_or_create_buyers_worksheet(
    client: gspread.Client,
    sheet_id: str,
    worksheet_name: str = "Покупатели",
) -> gspread.Worksheet:
    """
    Получает или создаёт лист "Покупатели" в таблице.
    """
    spreadsheet = client.open_by_key(sheet_id)
    
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
        first_row = worksheet.row_values(1)
        if not first_row or first_row != BUYERS_HEADERS:
            worksheet.update("A1", [BUYERS_HEADERS])
            logger.info(f"Заголовки добавлены на лист '{worksheet_name}'")
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=worksheet_name,
            rows=1000,
            cols=len(BUYERS_HEADERS),
        )
        worksheet.update("A1", [BUYERS_HEADERS])
        logger.info(f"Создан новый лист '{worksheet_name}' с заголовками")
    
    return worksheet


async def add_buyer_to_sheets(
    client: gspread.Client,
    config: Config,
    user: User,
    amount: float,
) -> None:
    """
    Добавляет покупателя в лист "Покупатели".
    Вызывается сразу после успешной оплаты.
    
    Записывает: Имя, Username, Telegram ID, Дата покупки, Сумма
    """
    try:
        worksheet = get_or_create_buyers_worksheet(client, config.google_sheet_id)
        
        # Форматируем дату покупки
        purchase_date = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        row = [
            user.full_name or "Без имени",
            f"@{user.username}" if user.username else "нет username",
            str(user.telegram_id),
            purchase_date,
            f"{amount:.2f} EUR",
        ]
        
        worksheet.append_row(row)
        logger.info(f"Покупатель {user.telegram_id} добавлен в лист 'Покупатели'")
    except Exception as e:
        logger.error(f"Ошибка при добавлении покупателя в Google Sheets: {e}")


# =============================================================================
# Лист "Отзывы" — отзывы после встреч
# =============================================================================

FEEDBACK_HEADERS = [
    "Дата",
    "Telegram ID",
    "Имя",
    "Встреча",
    "Оценка",
    "Комфорт уровня",
    "Придёт снова",
    "Что нужно для 5",
]

LEVEL_COMFORT_LABELS = {
    "perfect": "✅ Идеально",
    "hard": "❌ Сложно",
    "easy": "🔽 Легко",
}

WILL_ATTEND_LABELS = {
    "yes": "🔥 Да",
    "maybe": "🤔 Возможно",
    "no": "❌ Нет",
}


def get_or_create_feedback_worksheet(
    client: gspread.Client,
    sheet_id: str,
    worksheet_name: str = "Отзывы",
) -> gspread.Worksheet:
    """
    Получает или создаёт лист "Отзывы" в таблице.
    """
    spreadsheet = client.open_by_key(sheet_id)
    
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
        first_row = worksheet.row_values(1)
        if not first_row or first_row != FEEDBACK_HEADERS:
            worksheet.update("A1", [FEEDBACK_HEADERS])
            logger.info(f"Заголовки добавлены на лист '{worksheet_name}'")
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=worksheet_name,
            rows=1000,
            cols=len(FEEDBACK_HEADERS),
        )
        worksheet.update("A1", [FEEDBACK_HEADERS])
        logger.info(f"Создан новый лист '{worksheet_name}' с заголовками")
    
    return worksheet


async def add_feedback_to_sheets(
    client: gspread.Client,
    config: Config,
    telegram_id: int,
    user_name: str,
    meeting_title: str,
    rating: int,
    level_comfort: str,
    will_attend: str,
    improvement_comment: str,
) -> None:
    """
    Добавляет отзыв в лист "Отзывы".
    Вызывается после завершения опроса.
    """
    try:
        worksheet = get_or_create_feedback_worksheet(client, config.google_sheet_id)
        
        feedback_date = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        row = [
            feedback_date,
            str(telegram_id),
            user_name or "Без имени",
            meeting_title or "Встреча",
            "⭐" * rating if rating else "",
            LEVEL_COMFORT_LABELS.get(level_comfort, level_comfort or ""),
            WILL_ATTEND_LABELS.get(will_attend, will_attend or ""),
            improvement_comment or "",
        ]
        
        worksheet.append_row(row)
        logger.info(f"Отзыв от {telegram_id} добавлен в лист 'Отзывы'")
    except Exception as e:
        logger.error(f"Ошибка при добавлении отзыва в Google Sheets: {e}")
