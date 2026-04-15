# Парсинг конфигурации из переменных окружения
import os
from dataclasses import dataclass
from typing import Optional, List

from dotenv import load_dotenv


@dataclass
class Config:
    """Конфигурация приложения, загружаемая из переменных окружения."""
    # Telegram
    bot_token: str
    bot_username: str
    admin_ids: List[int]
    channel_id: int

    # Web server
    web_host: str
    web_port: int
    log_level: str
    webhook_public_url: str

    # Database
    database_url: str

    # Stripe
    stripe_api_key: str
    stripe_webhook_secret: str

    # LavaTop
    lavatop_api_key: str
    lavatop_webhook_incoming_key: str
    lavatop_offer_1_month: str
    lavatop_offer_3_months: str
    lavatop_offer_6_months: str
    lavatop_currency: str
    lavatop_payment_provider: str
    lavatop_payment_method: str
    lavatop_buyer_language: str

    # Тарифы (цены в EUR)
    price_1_month: float
    price_3_months: float
    price_6_months: float

    # Google Sheets
    google_creds_file: str
    google_sheet_id: str

    # Stripe Price IDs (создаются в Stripe Dashboard)
    stripe_price_1_month: str
    stripe_price_3_months: str
    stripe_price_6_months: str

    # OpenAI (для демо AI в онбординге)
    openai_api_key: str

    # ElevenLabs TTS (голос Grego)
    elevenlabs_api_key: str
    grego_voice_id: str

    # Онбординг
    welcome_video_note_id: str
    gregochat_bot_username: str

    # Фото для воронки (file_id из Telegram)
    welcome_photo_id: str  # grego_club_main.jpg - главное фото при /start
    includes_photo_1_id: str  # спикинги + база знаний
    includes_photo_2_id: str  # встречи + ИИ-ассистент
    prices_photo_id: str  # grego_prices.jpg - фото с ценами


def load_config() -> Config:
    """Загружает конфигурацию из .env файла и переменных окружения."""
    load_dotenv()

    def get_env(key: str, default: Optional[str] = None) -> str:
        value = os.getenv(key, default)
        if value is None:
            raise ValueError(f"Переменная окружения {key} не задана")
        return value

    def get_env_int(key: str, default: Optional[int] = None) -> int:
        value = os.getenv(key)
        if value is None:
            if default is None:
                raise ValueError(f"Переменная окружения {key} не задана")
            return default
        return int(value)

    def get_env_int_list(key: str) -> List[int]:
        value = os.getenv(key)
        if value is None:
            raise ValueError(f"Переменная окружения {key} не задана")
        return [int(x.strip()) for x in value.split(",")]

    def get_env_float(key: str, default: Optional[float] = None) -> float:
        value = os.getenv(key)
        if value is None:
            if default is None:
                raise ValueError(f"Переменная окружения {key} не задана")
            return default
        return float(value)

    return Config(
        bot_token=get_env("BOT_TOKEN"),
        bot_username=get_env("BOT_USERNAME", ""),
        admin_ids=get_env_int_list("ADMIN_ID"),
        channel_id=get_env_int("CHANNEL_ID"),
        web_host=get_env("WEB_HOST", "0.0.0.0"),
        web_port=get_env_int("WEB_PORT", 8000),
        log_level=get_env("LOG_LEVEL", "INFO"),
        webhook_public_url=get_env("WEBHOOK_PUBLIC_URL", ""),
        database_url=get_env("DATABASE_URL", "sqlite+aiosqlite:///./data/app.db"),
        stripe_api_key=get_env("STRIPE_SECRET_KEY"),
        stripe_webhook_secret=get_env("STRIPE_WEBHOOK_SECRET"),
        lavatop_api_key=get_env("LAVATOP_API_KEY", ""),
        lavatop_webhook_incoming_key=get_env("LAVATOP_WEBHOOK_INCOMING_KEY", ""),
        lavatop_offer_1_month=get_env("LAVATOP_OFFER_1_MONTH", ""),
        lavatop_offer_3_months=get_env("LAVATOP_OFFER_3_MONTHS", ""),
        lavatop_offer_6_months=get_env("LAVATOP_OFFER_6_MONTHS", ""),
        lavatop_currency=get_env("LAVATOP_CURRENCY", "EUR"),
        lavatop_payment_provider=get_env("LAVATOP_PAYMENT_PROVIDER", ""),
        lavatop_payment_method=get_env("LAVATOP_PAYMENT_METHOD", ""),
        lavatop_buyer_language=get_env("LAVATOP_BUYER_LANGUAGE", "RU"),
        price_1_month=get_env_float("PRICE_1_MONTH", 49.0),
        price_3_months=get_env_float("PRICE_3_MONTHS", 132.0),
        price_6_months=get_env_float("PRICE_6_MONTHS", 245.0),
        google_creds_file=get_env("GOOGLE_CREDS_FILE", "./google_sheet_creds.json"),
        google_sheet_id=get_env("GOOGLE_SHEET_ID", ""),
        stripe_price_1_month=get_env("STRIPE_PRICE_1_MONTH"),
        stripe_price_3_months=get_env("STRIPE_PRICE_3_MONTHS"),
        stripe_price_6_months=get_env("STRIPE_PRICE_6_MONTHS"),
        openai_api_key=get_env("OPENAI_API_KEY", ""),
        elevenlabs_api_key=get_env("ELEVENLABS_API_KEY", ""),
        grego_voice_id=get_env("GREGO_VOICE_ID", "RuJuetv6EsF42EMkBapY"),
        welcome_video_note_id=get_env("WELCOME_VIDEO_NOTE_ID", ""),
        gregochat_bot_username=get_env("GREGOCHAT_BOT_USERNAME", "GregoChat_bot"),
        # Фото воронки
        welcome_photo_id=get_env("WELCOME_PHOTO_ID", ""),
        includes_photo_1_id=get_env("INCLUDES_PHOTO_1_ID", ""),
        includes_photo_2_id=get_env("INCLUDES_PHOTO_2_ID", ""),
        prices_photo_id=get_env("PRICES_PHOTO_ID", ""),
    )
