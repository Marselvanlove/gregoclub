# Настройка Cloudflare Tunnel для club.hablancongrego.com

## Зачем нужен Cloudflare Tunnel?

Cloudflare Tunnel позволяет безопасно проксировать трафик с домена `club.hablancongrego.com` 
напрямую в Docker контейнер без необходимости:
- Открывать порты на сервере
- Настраивать nginx/reverse proxy
- Получать SSL сертификаты (Cloudflare делает это автоматически)

## Пошаговая настройка

### Шаг 1: Создание туннеля в Cloudflare

1. Открой [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/)
2. В меню слева выбери **Networks** → **Tunnels**
3. Нажми **Create a tunnel**
4. Выбери **Cloudflared** (рекомендуется)
5. Введи имя туннеля: `grego-club-bot`
6. Нажми **Save tunnel**

### Шаг 2: Получение credentials

После создания туннеля Cloudflare покажет команду установки. Нам нужен только **токен**.

1. На странице туннеля найди секцию **Install and run a connector**
2. Скопируй **Tunnel Token** (длинная строка после `--token`)

Или скачай JSON credentials:
1. Нажми на туннель → **Configure**
2. В разделе **Connectors** найди ID туннеля
3. Cloudflare автоматически создаст credentials при первом подключении

### Шаг 3: Настройка Public Hostname

1. На странице туннеля нажми **Public Hostname** → **Add a public hostname**
2. Заполни:
   - **Subdomain:** `club`
   - **Domain:** `hablancongrego.com`
   - **Service Type:** `HTTP`
   - **URL:** `bot:8000`
3. Нажми **Save hostname**

### Шаг 4: Настройка проекта

#### Вариант A: Через токен (проще)

1. Скопируй токен из Cloudflare Dashboard
2. Обнови `docker-compose.yml`:

```yaml
cloudflared:
  image: cloudflare/cloudflared:latest
  container_name: cloudflared-tunnel
  command: tunnel --no-autoupdate run --token YOUR_TUNNEL_TOKEN
  depends_on:
    bot:
      condition: service_healthy
  restart: unless-stopped
```

#### Вариант B: Через credentials файл (как в zaebot)

1. Создай файл `cloudflared/credentials.json`:
```json
{
  "AccountTag": "YOUR_ACCOUNT_ID",
  "TunnelSecret": "BASE64_SECRET",
  "TunnelID": "YOUR_TUNNEL_ID"
}
```

2. Обнови `cloudflared/config.yml`:
```yaml
tunnel: YOUR_TUNNEL_ID
credentials-file: /etc/cloudflared/credentials.json
no-autoupdate: true

ingress:
  - hostname: club.hablancongrego.com
    service: http://bot:8000
  - service: http_status:404
```

### Шаг 5: Запуск

```bash
docker-compose down
docker-compose up -d --build
```

### Шаг 6: Проверка

1. Открой в браузере: `https://club.hablancongrego.com/healthz`
2. Должен вернуться JSON: `{"status": "ok"}`

## Настройка Stripe Webhook

После успешной настройки туннеля:

1. Открой [Stripe Dashboard → Webhooks](https://dashboard.stripe.com/test/webhooks)
2. Нажми **Add endpoint**
3. **Endpoint URL:** `https://club.hablancongrego.com/webhook/stripe`
4. **Events:**
   - `checkout.session.completed`
   - `invoice.payment_succeeded`
   - `customer.subscription.deleted`
5. Скопируй **Signing secret** (`whsec_...`)
6. Вставь в `.env` как `STRIPE_WEBHOOK_SECRET`

## Troubleshooting

### Туннель не подключается
```bash
docker-compose logs cloudflared
```

### Webhook возвращает 400/403
- Проверь `STRIPE_WEBHOOK_SECRET` в `.env`
- Убедись что URL в Stripe Dashboard точно совпадает: `/webhook/stripe`

### Бот не отвечает
```bash
docker-compose logs bot
```
