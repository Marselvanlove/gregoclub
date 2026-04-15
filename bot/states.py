# FSM (Finite State Machine) — машины состояний для многошаговых диалогов
from aiogram.fsm.state import State, StatesGroup


class BroadcastStates(StatesGroup):
    """Состояния для рассылки (админ-панель)."""
    waiting_for_segment = State()   # Ожидание выбора сегмента
    waiting_for_content = State()   # Ожидание текста/фото для рассылки
    waiting_for_confirm = State()   # Ожидание подтверждения отправки


class ScheduleStates(StatesGroup):
    """Состояния для редактирования расписания (админ-панель)."""
    waiting_for_schedule = State()  # Ожидание текста расписания


class OnboardingStates(StatesGroup):
    """Состояния для онбординга нового пользователя."""
    demo_ai_active = State()  # Демо AI активен (ожидание сообщения)


class PaymentStates(StatesGroup):
    waiting_for_lava_email = State()


class FeedbackStates(StatesGroup):
    waiting_for_improvement_comment = State()


class ScheduledBroadcastStates(StatesGroup):
    """Состояния для запланированной рассылки (админ-панель)."""
    waiting_for_segment = State()      # Ожидание выбора сегмента
    waiting_for_content = State()      # Ожидание текста/фото
    waiting_for_rsvp_choice = State()  # Ожидание выбора: прикрепить RSVP-кнопки?
    waiting_for_rsvp_title = State()   # Ожидание названия созвона
    waiting_for_rsvp_date = State()    # Ожидание даты/времени созвона
    waiting_for_zoom_link = State()    # Ожидание ссылки на Zoom
    waiting_for_schedule_time = State() # Ожидание времени отправки рассылки
    waiting_for_confirm = State()      # Ожидание подтверждения


class AdminStates(StatesGroup):
    """Состояния для админ-команд."""
    waiting_for_photo = State()  # Ожидание фото для получения file_id
    waiting_for_user_id = State()  # Ожидание ID пользователя для ручного добавления
    waiting_for_duration = State()  # Ожидание выбора срока подписки (1 / 3 месяца)
