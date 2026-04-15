import asyncio
import logging
import signal
from contextlib import suppress

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from fastapi import FastAPI

# Импорты из нашего проекта
from utils.config import load_config, Config
from bot.handlers import user as user_handlers
from bot.handlers import admin as admin_handlers
from bot.handlers import onboarding as onboarding_handlers
from bot.handlers import feedback as feedback_handlers
from bot.handlers import test_commands as test_handlers
from bot.handlers import chat_member as chat_member_handlers
from bot.handlers import starts_onboarding as starts_handlers
from bot.middlewares import DbSessionMiddleware
from bot.middlewares.gspread_middleware import GspreadMiddleware
from database import init_db, close_db, get_session_factory
from services.stripe_api import init_stripe
from services.google_sheets import init_google_sheets
from services.scheduler import create_scheduler
from web.lavatop_webhook import create_lavatop_webhook_endpoint
from web.salebot_webhook import create_salebot_webhook_endpoint
from web.checkout_redirect import create_checkout_redirect_endpoint
from web.dashboard_proxy import create_dashboard_proxy_endpoint
from web.stripe_webhook import create_stripe_webhook_endpoint


# FastAPI приложение для вебхуков Stripe
app = FastAPI(title="Subscription Bot Webhooks")


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


def _setup_logging(log_level: str) -> None:
    """Настройка логирования для всего приложения."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def run_bot_polling(dp: Dispatcher, bot: Bot) -> None:
    # Важно: handle_signals=False, потому что мы будем управлять остановкой
    # самостоятельно (иначе разные сервисы начнут конфликтовать за SIGINT/SIGTERM).
    await dp.start_polling(bot, handle_signals=False)


async def run_web_server(server: uvicorn.Server) -> None:
    # Uvicorn умеет работать в asyncio как coroutine через server.serve().
    await server.serve()


async def main() -> None:
    # Загружаем конфигурацию из .env через наш модуль config.py
    config: Config = load_config()
    _setup_logging(config.log_level)

    # Инициализация бота и диспетчера
    bot = Bot(token=config.bot_token)
    dp = Dispatcher()

    # Нормализуем username (на случай если в .env указали "@name")
    config.bot_username = config.bot_username.lstrip("@")

    # Пытаемся автоматически определить username бота для корректных deep links (Stripe)
    if not config.bot_username:
        try:
            me = await bot.get_me()
            if me.username:
                config.bot_username = me.username
                logging.info(f"Username бота определён автоматически: @{me.username}")
            else:
                logging.warning("Не удалось определить username бота: поле username пустое")
        except Exception as e:
            logging.warning(f"Не удалось получить username бота через get_me(): {e}")

    # Подключаем роутеры (обработчики команд)
    dp.include_router(user_handlers.router)
    dp.include_router(admin_handlers.router)
    dp.include_router(onboarding_handlers.router)
    dp.include_router(feedback_handlers.router)
    dp.include_router(test_handlers.router)
    dp.include_router(chat_member_handlers.router)
    dp.include_router(starts_handlers.router)

    # Устанавливаем команды бота в меню
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать"),
        BotCommand(command="info", description="Расписание"),
        BotCommand(command="pay", description="Оформить подписку"),
        BotCommand(command="pay_lava", description="Оплатить через LavaTop"),
        BotCommand(command="status", description="Статус подписки"),
        BotCommand(command="support", description="Поддержка"),
    ])
    logging.info("Команды бота установлены.")

    # Передаём конфиг в workflow_data, чтобы он был доступен в хендлерах
    dp.workflow_data["config"] = config

    # Инициализируем базу данных (создаём таблицы, если их нет)
    logging.info("Инициализация базы данных...")
    await init_db(config.database_url)
    # Подключаем middleware для автоматической инъекции сессии БД в хендлеры
    session_factory = get_session_factory()
    dp.update.middleware(DbSessionMiddleware(session_factory))
    logging.info("База данных инициализирована.")

    # Инициализируем Stripe клиент и передаём в workflow_data
    stripe_client = init_stripe(config)
    dp.workflow_data["stripe_client"] = stripe_client
    logging.info("Stripe клиент инициализирован.")

    # Инициализируем Google Sheets клиент (опционально — если есть креды)
    # ВАЖНО: инициализируем ДО webhook роутера, чтобы передать в него gspread_client
    gspread_client = None
    if config.google_sheet_id:
        try:
            gspread_client = init_google_sheets(config)
            dp.workflow_data["gspread_client"] = gspread_client
            logging.info("Google Sheets клиент инициализирован.")
        except Exception as e:
            logging.warning(f"Google Sheets не инициализирован: {e}")
    else:
        logging.info("Google Sheets отключён: GOOGLE_SHEET_ID не задан")

    # Подключаем middleware для передачи gspread_client в хендлеры
    dp.update.middleware(GspreadMiddleware(gspread_client))
    logging.info("GspreadMiddleware подключен.")

    # Подключаем FastAPI роутер для Stripe вебхуков (с gspread_client для записи покупателей)
    stripe_webhook_router = create_stripe_webhook_endpoint(
        session_factory, bot, config, gspread_client
    )
    app.include_router(stripe_webhook_router)
    lavatop_webhook_router = create_lavatop_webhook_endpoint(
        session_factory, bot, config, gspread_client
    )
    app.include_router(lavatop_webhook_router)
    checkout_redirect_router = create_checkout_redirect_endpoint(
        session_factory, bot, config, gspread_client
    )
    app.include_router(checkout_redirect_router)
    salebot_webhook_router = create_salebot_webhook_endpoint(
        session_factory, bot, config, gspread_client
    )
    app.include_router(salebot_webhook_router)
    dashboard_proxy_router = create_dashboard_proxy_endpoint()
    app.include_router(dashboard_proxy_router)

    # Создаём и запускаем планировщик задач (APScheduler)
    scheduler = create_scheduler(
        session_factory=session_factory,
        bot=bot,
        config=config,
        gspread_client=gspread_client,
    )
    scheduler.start()
    logging.info("Планировщик задач запущен.")

    uvicorn_config = uvicorn.Config(
        app=app,
        host=config.web_host,
        port=config.web_port,
        log_level=config.log_level.lower(),
        loop="asyncio",
    )
    server = uvicorn.Server(config=uvicorn_config)

    # Один общий сигнал остановки для обоих сервисов.
    stop_event = asyncio.Event()

    def _request_shutdown() -> None:
        # Вызывается из signal handler: мы не делаем тут await,
        # а только выставляем флаг остановки.
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, _request_shutdown)

    bot_task = asyncio.create_task(run_bot_polling(dp, bot), name="bot_polling")
    web_task = asyncio.create_task(run_web_server(server), name="web_server")
    stop_task = asyncio.create_task(stop_event.wait(), name="stop_signal")

    # Ждём: либо пришёл сигнал остановки, либо один из сервисов завершился/упал.
    done, pending = await asyncio.wait(
        {bot_task, web_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Важно: если завершился ЛЮБОЙ из сервисов (или пришёл сигнал) —
    # мы корректно останавливаем второй. Иначе можно зависнуть на ожидании.
    if stop_task in done or bot_task in done or web_task in done:
        server.should_exit = True
        await dp.stop_polling()

    # Если кто-то упал с исключением — пробрасываем ошибку дальше,
    # но перед этим корректно гасим второй сервис.
    for task in (bot_task, web_task):
        exc = task.exception() if task in done and not task.cancelled() else None
        if exc is not None:
            server.should_exit = True
            await dp.stop_polling()
            raise exc

    # На случай, если стоп-задача осталась ожидать сигнал (например, если завершился
    # bot/web task) — отменяем её, чтобы не оставлять "висящих" задач.
    if not stop_task.done():
        stop_task.cancel()
        with suppress(asyncio.CancelledError):
            await stop_task

    # Дожидаемся завершения фоновых задач.
    await asyncio.gather(bot_task, web_task, return_exceptions=True)

    # Останавливаем планировщик
    scheduler.shutdown(wait=False)
    logging.info("Планировщик остановлен.")

    # Закрываем соединение с БД
    await close_db()
    logging.info("Соединение с БД закрыто.")

    # На всякий случай закрываем HTTP-сессию бота.
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
