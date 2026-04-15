
# ТЕХНИЧЕСКОЕ ЗАДАНИЕ: Telegram-бот для платного клуба (Subscription Bot)

## 1. Общие сведения

**Цель:** Создать Telegram-бота для продажи и управления подпиской на закрытый канал. Бот принимает оплату через Stripe, автоматически выдает доступ (одноразовые ссылки), удаляет пользователей при неоплате и синхронизирует данные с Google Таблицей (CRM).

**Стек:**

* **Язык:** Python 3.11+
* **Бот:** aiogram 3.x (асинхронный)
* **Веб-сервер (Webhook):** FastAPI + Uvicorn 
* **База данных:** SQLite (с использованием SQLAlchemy для легкой миграции на PostgreSQL в будущем).
* **Планировщик:** APScheduler 
* **Интеграции:** Stripe API, Google Sheets API.
* **Контейнеризация:** Docker + Docker Compose.

---

## 2. Структура Базы Данных (Schema)

*Необходимо использовать ORM (SQLAlchemy).*

**Таблица users:**

* id (int, pk)
* telegram_id (bigint, unique) — ID пользователя в ТГ.
* username (string) — @username.
* full_name (string).
* language_level (string) — уровень языка (выбор при старте).
* status (enum) — new (первый контакт), pending (выбрал тариф, не платил), active (подписчик), expired (подписка кончилась).
* registration_date (datetime).
* subscription_end_date (datetime, null) — до какого числа доступ.
* stripe_customer_id (string) — ID клиента в Stripe.

**Таблица payments:**

* id (int, pk)
* user_id (fk -> users.id)
* amount (float) — сумма.
* currency (string) — валюта (EUR).
* stripe_payment_id (string).
* status (string) — success/failed.
* created_at (datetime).

---

## 3. Логика работы Бота (Aiogram)

### Роль: Пользователь

1. **Команда /start:**
* Приветствие.
* Инлайн-клавиатура: выбор уровня языка (A1-A2, B1-B2).
* Сохранение пользователя в БД со статусом new.


2. **Команда /pay (Оплата):**
* Выбор тарифа (Инлайн-кнопки: "1 месяц - X EUR", "3 месяца - Y EUR").
* Генерация ссылки на оплату Stripe (Checkout Session Mode: Subscription).
* Смена статуса в БД на pending.


3. **Команда /status (Личный кабинет):**
* Вывод: текущий статус, дата окончания подписки.
* Кнопка: "Управление подпиской" (ссылка на Stripe Portal для отмены/смены карты).


4. **Команда /support:**
* Сообщение с юзернеймом админа для связи.



### Роль: Админ (ID админа задается в .env)

1. **Команда /admin (Скрытая):**
* Открывает инлайн-панель.
* **Кнопка "Статистика":** Выводит кол-во юзеров по статусам (New, Active, Expired).
* **Кнопка "Рассылка":**
* Выбор сегмента: "Все", "Думают (Pending)", "Активные".
* Ввод текста/фото.
* Подтверждение отправки.


* **Кнопка "Sync CRM":** Принудительная выгрузка базы в Google Sheets.



---

## 4. Логика Вебхука (FastAPI)

Приложение FastAPI должно слушать POST запросы на /webhook/stripe.

**Обработка событий Stripe:**

1. checkout.session.completed:
* Первичная оплата успешна.
* Найти пользователя в БД по client_reference_id (передаем tg_id при создании ссылки).
* Обновить статус на active.
* Установить subscription_end_date (+30 дней).
* **Действие:** Бот отправляет пользователю сообщение: "Оплата прошла! Вот твоя ссылка" + генерирует одноразовую ссылку на вступление (createChatInviteLink с member_limit=1).


2. invoice.payment_succeeded (Рекуррентный платеж):
* Продление подписки.
* Найти юзера по stripe_customer_id.
* Продлить subscription_end_date.
* Бот молчит или шлет уведомление "Подписка продлена".


3. customer.subscription.deleted:
* Подписка отменена или не оплачена после всех попыток.
* Обновить статус на expired.
* Запустить процедуру исключения из канала (Kick).



---

## 5. Фоновые задачи (APScheduler)

1. **Ежедневная проверка (09:00 Madrid Time):**
* Выбрать всех пользователей, у которых subscription_end_date < today.
* Проверить статус подписки в Stripe (на случай рассинхрона).
* Если не активна -> bot.ban_chat_member (Kick) -> bot.unban_chat_member (чтобы могли вернуться).
* Отправить сообщение: "Твоя подписка истекла. Ждем тебя снова!".


2. **Синхронизация с Google Sheets (раз в 1 час):**
* Очистить лист (или обновить строки).
* Выгрузить актуальные данные из таблицы users: ID, Username, Status, Language Level, Subscription End.



---

## 6. Требования к Google Таблице (CRM)

Бот должен писать в таблицу со следующими колонками:

1. Telegram ID 
2. Username 
3. Имя 
4. Дата регистрации 
5. Уровень языка 
6. Статус (Платит / Думает / Отвалился)
7. Дата окончания подписки 
8. LTV (Сумма всех платежей - опционально).

---

## 7. Файловая структура (Рекомендация)

```text
bot_project/
├── .env                    # Токены (TG, Stripe, Google JSON path)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── main.py                 # Точка входа (запуск бота + FastAPI)
├── google_sheet_creds.json # Ключ от гугла
├── bot/
│   ├── __init__.py
│   ├── handlers/           # Обработчики команд (user.py, admin.py)
│   ├── keyboards/          # Кнопки
│   ├── middlewares/        # Мидлвари (например, для проверки админа)
│   └── states.py           # FSM машины состояний
├── database/
│   ├── __init__.py
│   ├── models.py           # SQLAlchemy модели
│   └── requests.py         # Функции работы с БД (add_user, get_user)
├── services/
│   ├── stripe_api.py       # Логика работы со Stripe
│   ├── google_sheets.py    # Логика работы с таблицами
│   └── scheduler.py        # Задачи по расписанию
└── utils/
    └── config.py           # Парсинг конфига

```

---

### Как использовать это ТЗ:

1. Создай папку проекта.
2. Создай файл SPECIFICATION.md и вставь туда этот текст.
3. Открой Cursor, нажми Cmd+L (Chat) или Cmd+I (Composer).
