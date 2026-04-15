# 📊 Система обратной связи после встреч (Feedback System)

**Дата начала:** 26.02.2026  
**Статус:** В разработке

---

## 🎯 Цель

Реализовать систему автоматической обратной связи после проведения спикингов:
1. Отправка опроса через 20 минут после окончания встречи
2. Сбор оценок (1-5 звёзд), уровень комфорта, планы на следующую встречу
3. Follow-up сообщения на основе ответов

---

## 📋 Текущая архитектура (до изменений)

### Модели (database/models.py)
- `User` — пользователи с полями статуса, уровня, подписки
- `ScheduledBroadcast` — рассылки с RSVP (содержит `rsvp_event_datetime` — время встречи)
- `BroadcastRSVP` — ответы пользователей на RSVP (attending/declined)

### Scheduler (services/scheduler.py)
- `send_event_reminders()` — напоминания за 15 и 5 минут до встречи
- Использует `rsvp_event_datetime` для определения времени события

### Ключевые поля ScheduledBroadcast:
- `has_rsvp: bool` — есть ли кнопки RSVP
- `rsvp_event_datetime: datetime` — точное время начала встречи
- `rsvp_event_title: str` — название темы
- `reminder_15min_sent`, `reminder_5min_sent` — флаги отправки напоминаний

### Логика встреч:
- Встреча длится **90 минут**
- Время окончания = `rsvp_event_datetime + 90 минут`
- Опрос отправляется через **20 минут после окончания** = `rsvp_event_datetime + 110 минут`

---

## 📝 План работ

### Этап 1: Модель данных ✅

**Файл:** `database/models.py`

**Что добавляем:**
```python
class EventFeedback(Base):
    """Ответы на опрос после встречи."""
    __tablename__ = "event_feedbacks"
    
    id: int (PK)
    broadcast_id: int (FK -> scheduled_broadcasts.id)
    telegram_id: int
    rating: int (1-5 звёзд)
    level_comfort: str (perfect / hard / easy)
    will_attend_next: str (yes / maybe / no)
    created_at: datetime
```

**Новые поля в ScheduledBroadcast:**
- `feedback_sent: bool` — отправлен ли опрос после встречи

**Статус:** ✅ Завершено

---

### Этап 2: CRUD-функции ✅

**Файл:** `database/requests.py`

**Что добавляем:**
- `create_event_feedback()` — сохранение ответа
- `get_event_feedback()` — получение feedback по broadcast_id и telegram_id
- `get_broadcasts_needing_feedback()` — рассылки, после которых нужно отправить опрос
- `mark_feedback_sent()` — пометить, что опрос отправлен
- `get_feedbacks_needing_followup()` — для follow-up сообщений

**Статус:** ✅ Завершено

---

### Этап 3: Тексты сообщений ✅

**Файл:** `bot/texts.py`

**Что добавляем:**
```python
# Опрос после встречи
FEEDBACK_INTRO = "Спасибо, что были на встрече!..."
FEEDBACK_Q1_RATING = "Оцените встречу ⭐️"
FEEDBACK_Q2_LEVEL = "Комфортен ли был уровень?"
FEEDBACK_Q3_NEXT = "Придёте на следующую встречу?"
FEEDBACK_THANKS = "Спасибо за обратную связь!..."

# Follow-up сообщения
FEEDBACK_FOLLOWUP_HIGH_RATING = "Рады, что встреча вам понравилась 💚..."
FEEDBACK_FOLLOWUP_HARD_LEVEL = "Спасибо за честный ответ!..."
FEEDBACK_FOLLOWUP_NOT_COMING = "Мы давно вас не видели 😊..."
FEEDBACK_FOLLOWUP_INACTIVE = "Мы давно вас не видели 😊..."
```

**Статус:** ✅ Завершено

---

### Этап 4: Клавиатуры ✅

**Файл:** `bot/keyboards/inline.py`

**Что добавляем:**
- `get_feedback_rating_keyboard(broadcast_id)` — кнопки 1-5 звёзд
- `get_feedback_level_keyboard(broadcast_id)` — кнопки комфорта уровня
- `get_feedback_next_keyboard(broadcast_id)` — кнопки "приду / возможно / нет"
- `get_schedule_keyboard()` — кнопка "Расписание"

**Статус:** ✅ Завершено

---

### Этап 5: Handlers ✅

**Файл:** `bot/handlers/user.py` или новый `bot/handlers/feedback.py`

**Что добавляем:**
- Callback handlers для кнопок опроса:
  - `feedback_rating:{broadcast_id}:{rating}` — ответ на Q1
  - `feedback_level:{broadcast_id}:{answer}` — ответ на Q2
  - `feedback_next:{broadcast_id}:{answer}` — ответ на Q3

**Статус:** ✅ Завершено

---

### Этап 6: Scheduler — отправка опросов ✅

**Файл:** `services/scheduler.py`

**Что добавляем:**
```python
async def send_post_event_feedback():
    """
    Отправляет опрос участникам через 20 минут после окончания встречи.
    Время отправки = rsvp_event_datetime + 110 минут (90 мин встреча + 20 мин)
    """
```

**Статус:** ✅ Завершено

---

### Этап 7: Scheduler — follow-up сообщения ✅

**Файл:** `services/scheduler.py`

**Что добавляем:**
```python
async def send_feedback_followups():
    """
    Отправляет follow-up сообщения на основе ответов:
    - 4-5 звёзд + не записался → через 1-2 дня
    - "было сложно" для B1-C → предложить A1-A2
    - "не приду" → через неделю напоминание
    """
```

**Статус:** ✅ Завершено

---

### Этап 8: Миграция БД ⏳

**Файл:** Alembic миграция или ручной SQL

**Что делаем:**
- Создаём таблицу `event_feedbacks`
- Добавляем колонку `feedback_sent` в `scheduled_broadcasts`

**Статус:** ⏳ Ожидает

---

## 📊 Журнал изменений

### 26.02.2026 — Этап 1: Модель данных

**Файл:** `database/models.py`

**Что сделано:**
- Добавлены Enum-ы `LevelComfort` и `WillAttendNext` для типизации ответов
- Добавлено поле `feedback_sent: bool` в модель `ScheduledBroadcast`
- Создана модель `EventFeedback` с полями: `broadcast_id`, `telegram_id`, `rating`, `level_comfort`, `will_attend_next`, `followup_sent_at`, `created_at`

**Почему:**
- Нужно хранить ответы пользователей на опрос
- Поле `feedback_sent` предотвращает повторную отправку опроса

---

### 26.02.2026 — Этап 2: CRUD-функции

**Файл:** `database/requests.py`

**Что сделано:**
- `get_or_create_event_feedback()` — создание/получение feedback
- `update_feedback_rating()`, `update_feedback_level_comfort()`, `update_feedback_will_attend()` — обновление полей
- `get_broadcasts_needing_feedback()` — события для отправки опроса (через 110 минут после начала)
- `mark_feedback_sent()` — пометка отправки
- `get_feedbacks_for_followup()`, `get_feedbacks_not_coming_for_followup()` — для follow-up
- `get_users_inactive_for_days()` — неактивные пользователи

**Почему:**
- CRUD-слой для работы с feedback из handlers и scheduler

---

### 26.02.2026 — Этап 3: Тексты сообщений

**Файл:** `bot/texts.py`

**Что сделано:**
- `FEEDBACK_INTRO` — приветствие опроса
- `FEEDBACK_Q1_RATING`, `FEEDBACK_Q2_LEVEL`, `FEEDBACK_Q3_NEXT` — вопросы
- `FEEDBACK_THANKS` — финальное сообщение
- `FEEDBACK_FOLLOWUP_*` — follow-up сообщения

**Почему:**
- Тексты из ТЗ для опроса и follow-up логики

---

### 26.02.2026 — Этап 4: Клавиатуры

**Файл:** `bot/keyboards/inline.py`

**Что сделано:**
- `get_feedback_start_keyboard()` — кнопка "Оставить отзыв"
- `get_feedback_rating_keyboard()` — кнопки 1-5 звёзд
- `get_feedback_level_keyboard()` — комфорт уровня
- `get_feedback_next_keyboard()` — следующая встреча
- `get_feedback_thanks_keyboard()`, `get_followup_schedule_keyboard()` — кнопка расписания

**Почему:**
- Inline-клавиатуры для интерактивного опроса

---

### 26.02.2026 — Этап 5: Handlers

**Файл:** `bot/handlers/feedback.py` (НОВЫЙ)

**Что сделано:**
- `on_feedback_start()` — начало опроса
- `on_feedback_rating()` — обработка оценки
- `on_feedback_level()` — обработка комфорта уровня
- `on_feedback_next()` — обработка планов на следующую встречу

**Почему:**
- Отдельный router для обработки callback'ов опроса

---

### 26.02.2026 — Этап 6-7: Scheduler-задачи

**Файл:** `services/scheduler.py`

**Что сделано:**
- `send_post_event_feedback()` — отправка опроса через 110 минут после начала встречи
- `send_feedback_followups()` — follow-up на основе ответов (4-5 ⭐, "сложно", "не приду")
- `send_inactive_user_reminders()` — напоминания неактивным (>7 дней)
- Зарегистрированы задачи в `create_scheduler()`

**Почему:**
- Автоматизация отправки опросов и follow-up сообщений

---

### 26.02.2026 — Этап 8: Регистрация router

**Файл:** `main.py`

**Что сделано:**
- Добавлен импорт `feedback_handlers`
- Зарегистрирован `feedback_handlers.router` в диспетчере

**Почему:**
- Без регистрации callback'и не будут обрабатываться

---

## 🧪 Тесты

### Тест 1: Отправка опроса
- [ ] Создать тестовую рассылку с RSVP
- [ ] Убедиться, что опрос отправляется через 110 минут после `rsvp_event_datetime`
- [ ] Проверить, что опрос получают только участники (attending)

### Тест 2: Сохранение ответов
- [ ] Нажать кнопки опроса
- [ ] Проверить сохранение в БД
- [ ] Проверить переход между вопросами

### Тест 3: Follow-up логика
- [ ] Проверить follow-up для высокой оценки
- [ ] Проверить follow-up для "сложно"
- [ ] Проверить follow-up для "не приду"

### Тест 4: Edge cases
- [ ] Пользователь не отвечает на опрос
- [ ] Повторный ответ на тот же опрос
- [ ] Встреча без участников

---

## 📌 Заметки

- Встреча = событие с `has_rsvp=True` и `rsvp_event_datetime`
- Участники = пользователи с `BroadcastRSVP.response = attending`
- Длительность встречи = 90 минут (фиксировано)
- Задержка опроса = 20 минут после окончания

