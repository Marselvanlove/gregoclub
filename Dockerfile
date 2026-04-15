# Dockerfile для Subscription Bot
# Python 3.11 + все зависимости

FROM python:3.11-slim

# Метаданные
LABEL maintainer="your-email@example.com"
LABEL description="Telegram Subscription Bot with Stripe integration"

# Переменные окружения
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Рабочая директория
WORKDIR /app

# Системные зависимости (минимальный набор)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости отдельно для кэширования Docker layers
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY . .

# Создаём папку для данных (SQLite)
RUN mkdir -p /app/data

# Порт для FastAPI (Stripe webhooks)
EXPOSE 8000

# Healthcheck для FastAPI
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

# Запуск приложения
CMD ["python", "main.py"]
