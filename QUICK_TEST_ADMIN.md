# ⚡ Быстрый живой тест для админа 614771593

## 🎯 Цель
Проверить работу Feedback System за 10 минут без изменения кода.

---

## 📋 Шаг 1: Создать тестовую встречу через SQL

```bash
# Подключиться к БД
sqlite3 data/app.db
```

```sql
-- Вставить тестовую встречу на ТЕКУЩЕЕ ВРЕМЯ + 5 минут
INSERT INTO scheduled_broadcasts (
    segment,
    content_type,
    content_text,
    scheduled_at,
    status,
    has_rsvp,
    rsvp_event_title,
    rsvp_event_datetime,
    zoom_link,
    feedback_sent,
    sent_count,
    fail_count,
    created_at
) VALUES (
    'active',
    'text',
    '🧪 Тестовая встреча для проверки Feedback System',
    datetime('now'),
    'sent',  -- сразу "отправлено"
    1,  -- has_rsvp = TRUE
    'Тест опроса после встречи',
    datetime('now', '+5 minutes'),  -- ВСТРЕЧА ЧЕРЕЗ 5 МИНУТ
    'https://zoom.us/test',
    0,  -- feedback_sent = FALSE
    1,
    0,
    datetime('now')
);

-- Проверить ID созданной встречи
SELECT id, rsvp_event_title, rsvp_event_datetime, feedback_sent 
FROM scheduled_broadcasts 
ORDER BY id DESC 
LIMIT 1;

-- Запомнить ID (например, 42)
```

---

## 📋 Шаг 2: Записаться на встречу

```sql
-- Вставить RSVP для админа 614771593
-- ЗАМЕНИТЬ 42 на реальный ID встречи из шага 1!
INSERT INTO broadcast_rsvps (
    broadcast_id,
    telegram_id,
    response,
    created_at
) VALUES (
    42,  -- ← ЗАМЕНИТЬ на ID вашей встречи!
    614771593,
    'attending',
    datetime('now')
);

-- Проверить
SELECT * FROM broadcast_rsvps WHERE telegram_id = 614771593 ORDER BY id DESC LIMIT 1;
```

---

## 📋 Шаг 3: Изменить временное окно (БЕЗ перезапуска)

**Вариант A: Временно изменить время встречи на "прошлое"**

Проще всего изменить время встречи так, чтобы 110 минут уже прошло:

```sql
-- ЗАМЕНИТЬ 42 на ID вашей встречи!
UPDATE scheduled_broadcasts 
SET rsvp_event_datetime = datetime('now', '-111 minutes')
WHERE id = 42;

-- Проверить
SELECT id, 
       rsvp_event_title,
       rsvp_event_datetime,
       datetime('now') as now,
       ROUND((julianday('now') - julianday(rsvp_event_datetime)) * 24 * 60) as minutes_passed
FROM scheduled_broadcasts 
WHERE id = 42;
-- Должно показать ~111 минут
```

**Scheduler проверяет каждую минуту**, поэтому опрос придёт в течение 1 минуты!

---

## 📋 Шаг 4: Проверить логи

```bash
# Смотреть логи бота в реальном времени
docker-compose logs -f bot

# Ожидаемое в логах:
# "Отправка опроса после встречи #42 (Тест опроса после встречи)..."
# "Опрос для #42 отправлен 1 пользователям"
```

---

## 📋 Шаг 5: Пройти опрос в Telegram

1. Откройте бота в Telegram
2. Должно прийти сообщение с текстом про встречу и кнопкой "📝 Оставить отзыв"
3. Нажмите кнопку
4. Ответьте на 3 вопроса:
   - Оценка: **5** ⭐
   - Комфорт: **✅ Да, идеально**
   - Следующая встреча: **🔥 Да**
5. Проверьте финальное сообщение

---

## 📋 Шаг 6: Проверить БД

```sql
-- Проверить, что feedback сохранён
SELECT * FROM event_feedbacks 
WHERE telegram_id = 614771593 
ORDER BY created_at DESC 
LIMIT 1;

-- Проверить, что флаг выставлен
SELECT id, feedback_sent FROM scheduled_broadcasts WHERE id = 42;
-- feedback_sent должен быть 1
```

---

## 📋 Шаг 7: Проверить Follow-up (через 6 часов)

**Для быстрой проверки:** изменить время создания feedback на "вчера":

```sql
-- Сделать вид, что feedback был вчера
UPDATE event_feedbacks 
SET created_at = datetime('now', '-25 hours')
WHERE telegram_id = 614771593
ORDER BY created_at DESC
LIMIT 1;

-- Через 6 часов (или при следующем запуске scheduler)
-- должно прийти follow-up сообщение
```

**Или запустить scheduler задачу вручную:**

```python
# В Python консоли или скрипте
import asyncio
from aiogram import Bot
from database import get_session_factory
from services.scheduler import send_feedback_followups
from utils.config import load_config

async def test_followup():
    config = load_config()
    bot = Bot(token=config.bot_token)
    session_factory = get_session_factory()
    await send_feedback_followups(session_factory, bot)
    await bot.session.close()

asyncio.run(test_followup())
```

---

## ✅ Чеклист успешного теста

- [ ] Встреча создана через SQL
- [ ] RSVP добавлен для админа 614771593
- [ ] Время встречи изменено на -111 минут
- [ ] В логах появилось "Опрос для #X отправлен"
- [ ] Опрос пришёл в Telegram
- [ ] Все 3 вопроса прошли корректно
- [ ] Финальное сообщение получено
- [ ] Запись в `event_feedbacks` создана
- [ ] `feedback_sent = 1` в `scheduled_broadcasts`
- [ ] Follow-up сообщение пришло (опционально)

---

## 🚨 Если опрос не приходит

### 1. Проверить scheduler
```bash
docker-compose logs bot | grep "send_post_event_feedback"
```

### 2. Проверить временное окно
```sql
SELECT 
    id,
    rsvp_event_title,
    rsvp_event_datetime,
    datetime('now') as now,
    ROUND((julianday('now') - julianday(rsvp_event_datetime)) * 24 * 60) as minutes_passed,
    feedback_sent
FROM scheduled_broadcasts 
WHERE has_rsvp = 1 AND feedback_sent = 0;
```

Должно показать `minutes_passed` между 109 и 111.

### 3. Проверить участников
```sql
SELECT * FROM broadcast_rsvps 
WHERE broadcast_id = 42 AND response = 'attending';
```

Должна быть запись с `telegram_id = 614771593`.

---

## 🔄 Сброс для повторного теста

```sql
-- Удалить feedback
DELETE FROM event_feedbacks WHERE telegram_id = 614771593;

-- Сбросить флаг
UPDATE scheduled_broadcasts SET feedback_sent = 0 WHERE id = 42;

-- Вернуть время на -111 минут
UPDATE scheduled_broadcasts 
SET rsvp_event_datetime = datetime('now', '-111 minutes')
WHERE id = 42;
```

---

## 📊 Альтернатива: Использовать Python скрипт

```bash
python test_feedback_quick.py
```

Выбрать опцию `3` для полной проверки.
