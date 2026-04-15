# Subscription Bot 🤖

Telegram-бот для платного клуба с подпиской на закрытый канал.

## Возможности

- 🔐 **Подписка через Stripe** — автоматическая оплата и продление
- 📊 **Админ-панель** — статистика, рассылка, синхронизация CRM
- 📋 **Google Sheets CRM** — автоматическая выгрузка данных
- 🧭 **Analytics Events** — нормализованный event log по онбордингу, оплате, RSVP и feedback
- 🖥️ **Web Dashboard** — Next.js admin dashboard в `apps/dashboard` для Vercel
- ⏰ **Автоматизация** — ежедневная проверка подписок, kick истёкших
- 🔗 **Одноразовые ссылки** — безопасный доступ в закрытый канал

## Стек технологий

| Компонент | Технология |
|-----------|------------|
| Бот | Python 3.11, aiogram 3.x |
| API | FastAPI + Uvicorn |
| База данных | SQLAlchemy 2.x + Postgres (Neon), SQLite только для локального legacy/dev |
| Платежи | Stripe API |
| Планировщик | APScheduler |
| CRM | gspread (Google Sheets API) |
| Dashboard | Next.js App Router |
| Контейнеризация | Docker + Docker Compose |

## Быстрый старт

### 1. Клонирование

```bash
git clone <your-repo-url>
cd windsurf-project
```

### 2. Настройка окружения

```bash
# Копируем шаблон переменных
cp .env.example .env

# Редактируем .env — заполняем все переменные
nano .env
```

### 3. Настройка Stripe

1. Создай аккаунт на [stripe.com](https://stripe.com)
2. В Dashboard → Developers → API keys скопируй:
   - `STRIPE_SECRET_KEY` (Secret key)
3. Создай Products → Pricing:
   - Подписка 1 месяц → скопируй `price_xxx` в `STRIPE_PRICE_1_MONTH`
   - Подписка 3 месяца → скопируй `price_xxx` в `STRIPE_PRICE_3_MONTHS`
4. В Webhooks добавь эндпоинт:
   - URL: `https://your-domain.com/webhook/stripe`
   - Events: `checkout.session.completed`, `invoice.payment_succeeded`, `customer.subscription.deleted`
   - Скопируй Webhook Secret в `STRIPE_WEBHOOK_SECRET`

### 4. Настройка Google Sheets (опционально)

1. Создай проект в [Google Cloud Console](https://console.cloud.google.com)
2. Включи Google Sheets API и Google Drive API
3. Создай Service Account → скачай JSON ключ
4. Переименуй в `google_sheet_creds.json` и положи в корень проекта
5. Создай Google Таблицу и дай доступ Service Account (email из JSON)
6. Скопируй ID таблицы в `GOOGLE_SHEET_ID`

### 5. Запуск

#### Docker (бот и webhook backend)

```bash
# Сборка и запуск
docker-compose up -d

# Логи
docker-compose logs -f bot

# Остановка
docker-compose down
```

#### Локально (backend)

```bash
# Создаём виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate

# Устанавливаем зависимости
pip install -r requirements.txt

# Запускаем
python main.py
```

#### Dashboard локально

```bash
npm install
npm --workspace apps/dashboard run dev
```

Dashboard ожидает:

- `DATABASE_URL` на Postgres / Neon
- `DASHBOARD_ADMIN_PASSWORD`

Для деплоя на Vercel укажи Root Directory = `apps/dashboard`.

## Переменные окружения

| Переменная | Описание | Пример |
|------------|----------|--------|
| `BOT_TOKEN` | Токен Telegram бота | `123456:ABC-DEF...` |
| `ADMIN_ID` | Telegram ID администратора | `123456789` |
| `CHANNEL_ID` | ID закрытого канала | `-1001234567890` |
| `WEBHOOK_PUBLIC_URL` | Публичный URL backend для checkout redirect | `https://bot.example.com` |
| `DATABASE_URL` | Postgres для бота и dashboard | `postgresql+asyncpg://...` |
| `STRIPE_SECRET_KEY` | Секретный ключ Stripe | `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | Секрет вебхука Stripe | `whsec_...` |
| `STRIPE_PRICE_1_MONTH` | Price ID (1 месяц) | `price_...` |
| `STRIPE_PRICE_3_MONTHS` | Price ID (3 месяца) | `price_...` |
| `GOOGLE_SHEET_ID` | ID Google Таблицы | `1abc...xyz` |
| `DASHBOARD_ADMIN_PASSWORD` | Пароль доступа в dashboard | `change-me` |

## Команды бота

### Для пользователей

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие, выбор уровня языка |
| `/pay` | Выбор тарифа и оплата |
| `/status` | Личный кабинет, управление подпиской |
| `/support` | Связь с администратором |

### Для администратора

| Команда | Описание |
|---------|----------|
| `/admin` | Панель администратора |
| → Статистика | Количество пользователей по статусам |
| → Рассылка | Отправка сообщений сегментам |
| → Sync CRM | Принудительная синхронизация с Google Sheets |

## Структура проекта

```
├── main.py                 # Точка входа
├── requirements.txt        # Зависимости
├── .env.example            # Шаблон переменных
├── Dockerfile              # Docker образ
├── docker-compose.yml      # Docker Compose
├── package.json            # Workspace root для dashboard
│
├── apps/
│   └── dashboard/          # Next.js admin dashboard для Vercel
│
├── bot/
│   ├── handlers/           # Обработчики команд
│   ├── keyboards/          # Клавиатуры
│   ├── middlewares/        # Middleware (сессия БД)
│   └── states.py           # FSM состояния
│
├── database/
│   ├── models.py           # SQLAlchemy модели
│   └── requests.py         # CRUD операции
│
├── services/
│   ├── stripe_api.py       # Stripe интеграция
│   ├── analytics.py        # Event tracking + analytics snapshots
│   ├── google_sheets.py    # Google Sheets CRM
│   └── scheduler.py        # APScheduler задачи
│
├── web/
│   ├── checkout_redirect.py # Redirect tracking для checkout кликов
│   └── stripe_webhook.py    # Stripe webhook endpoint
│
└── utils/
    └── config.py           # Конфигурация
```

## Webhook для Stripe

После деплоя настрой Stripe Webhook:

```
URL: https://your-domain.com/webhook/stripe
Events:
  - checkout.session.completed
  - invoice.payment_succeeded
  - customer.subscription.deleted
```

## Фоновые задачи

| Задача | Расписание | Описание |
|--------|------------|----------|
| Проверка подписок | 09:00 Madrid | Kick истёкших из канала |
| Синхронизация CRM | Каждый час | Выгрузка в Google Sheets |

## Лицензия

MIT License
