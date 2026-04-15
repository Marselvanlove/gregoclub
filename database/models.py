# SQLAlchemy ORM модели: User, Payment
# Согласно разделу 2 ТЗ

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для всех моделей. Наследуемся от него."""
    pass


class UserStatus(str, enum.Enum):
    """
    Статусы пользователя (по ТЗ):
    - new: первый контакт (только /start)
    - pending: выбрал тариф, но ещё не оплатил
    - active: активный подписчик
    - expired: подписка истекла
    """
    new = "new"
    pending = "pending"
    active = "active"
    expired = "expired"


class PaymentProvider(str, enum.Enum):
    stripe = "stripe"
    lavatop = "lavatop"


class PaymentOrderStatus(str, enum.Enum):
    created = "created"
    paid = "paid"
    failed = "failed"
    cancelled = "cancelled"


class User(Base):
    """
    Таблица users — основная информация о пользователях.
    Связь один-ко-многим с таблицей payments.
    """
    __tablename__ = "users"

    # Первичный ключ (автоинкремент)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Telegram ID пользователя (уникальный, BigInt для больших ID)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)

    # @username в Telegram (может быть None, если пользователь не установил)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Полное имя (first_name + last_name из Telegram)
    full_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Email пользователя
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Уровень языка (выбирается при /start: A1-A2, B1-B2)
    language_level: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Статус пользователя (enum)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, native_enum=False),  # native_enum=False для SQLite совместимости
        default=UserStatus.new,
        nullable=False,
    )

    # Дата регистрации (первый /start)
    registration_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Дата окончания подписки (None = нет активной подписки)
    subscription_end_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ID клиента в Stripe (создаётся при первой оплате)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Провайдер платежей
    payment_provider: Mapped[Optional[PaymentProvider]] = mapped_column(
        Enum(PaymentProvider, native_enum=False),
        nullable=True,
    )

    # ID клиента в платежном провайдере
    payment_customer_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    last_pay_click_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    pending_reminder_step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    expiry_warning_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Флаг: прошёл ли пользователь демо AI (чтобы не тратить токены повторно)
    demo_completed: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="0")

    # Шаг напоминания для NEW пользователей (0 = не отправлено, 1 = через 1 час, 2 = через 24 часа)
    new_reminder_step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)

    # Дата перехода в статус expired (для winback-напоминаний)
    expired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Шаг winback-напоминания для EXPIRED (0 = не отправлено, 1 = через 3 дня, 2 = через 7 дней)
    winback_step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)

    # Дата последней покупки (для отправки проверки входа в группу через 5 минут)
    last_purchase_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Флаг: отправлена ли проверка входа в группу после покупки
    group_join_check_sent: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="0")

    # Связь с платежами (один пользователь — много платежей)
    payments: Mapped[list["Payment"]] = relationship(
        "Payment",
        back_populates="user",
        cascade="all, delete-orphan",  # Удаление пользователя удалит и его платежи
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, tg_id={self.telegram_id}, status={self.status.value})>"


class AnalyticsEvent(Base):
    """
    Таблица analytics_events — нормализованный event log для онбординга,
    оплаты и ключевых продуктовых действий.
    """
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    journey: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    onboarding_version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    step_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    source: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AnalyticsEvent(id={self.id}, tg_id={self.telegram_id}, "
            f"event={self.event_name}, version={self.onboarding_version})>"
        )


class UserAnalyticsProfile(Base):
    """
    Материализованный профиль аналитики по пользователю для CRM и дашборда.
    Обновляется при записи событий и ключевых изменениях состояния.
    """
    __tablename__ = "user_analytics_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    onboarding_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entry_source: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_event: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_event_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    state_choice: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    payment_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    first_paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    first_rsvp_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    first_feedback_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    feedback_prompt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stuck_bucket: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<UserAnalyticsProfile(tg_id={self.telegram_id}, stuck={self.stuck_bucket})>"


class PaymentOrder(Base):
    """
    Таблица payment_orders — заказы на платежи.
    """
    __tablename__ = "payment_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    provider: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider, native_enum=False),
        nullable=False,
    )

    tariff: Mapped[str] = mapped_column(String(32), nullable=False)

    email: Mapped[str] = mapped_column(String(255), nullable=False)

    external_invoice_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)

    external_parent_invoice_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    external_customer_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    currency: Mapped[str] = mapped_column(String(8), default="EUR", nullable=False, server_default="EUR")

    payment_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    status: Mapped[PaymentOrderStatus] = mapped_column(
        Enum(PaymentOrderStatus, native_enum=False),
        default=PaymentOrderStatus.created,
        nullable=False,
        server_default=PaymentOrderStatus.created.value,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<PaymentOrder(id={self.id}, provider={self.provider.value}, tg_id={self.telegram_id}, status={self.status.value})>"


class Payment(Base):
    """
    Таблица payments — история платежей.
    Каждый платёж привязан к пользователю (user_id).
    """
    __tablename__ = "payments"

    # Первичный ключ
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Внешний ключ на таблицу users
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Сумма платежа
    amount: Mapped[float] = mapped_column(Float, nullable=False)

    # Валюта (по ТЗ — EUR)
    currency: Mapped[str] = mapped_column(String(8), default="EUR", nullable=False)

    # Провайдер платежа
    provider: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider, native_enum=False),
        default=PaymentProvider.stripe,
        nullable=False,
        server_default=PaymentProvider.stripe.value,
    )

    # Внешний ID платежа
    external_payment_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)

    # ID платежа в Stripe (для сверки и дебага)
    stripe_payment_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)

    # Статус платежа: success / failed
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    # Дата создания записи
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Связь с пользователем (обратная сторона)
    user: Mapped["User"] = relationship("User", back_populates="payments")

    def __repr__(self) -> str:
        return f"<Payment(id={self.id}, user_id={self.user_id}, amount={self.amount} {self.currency})>"


class BroadcastStatus(str, enum.Enum):
    """
    Статусы запланированной рассылки:
    - pending: ожидает отправки
    - sent: отправлена
    - cancelled: отменена
    """
    pending = "pending"
    sent = "sent"
    cancelled = "cancelled"


class RSVPResponse(str, enum.Enum):
    """Ответы на RSVP."""
    attending = "attending"
    declined = "declined"


class LevelComfort(str, enum.Enum):
    """Ответы на вопрос о комфортности уровня."""
    perfect = "perfect"  # Да, идеально
    hard = "hard"        # Немного сложно
    easy = "easy"        # Немного легко


class WillAttendNext(str, enum.Enum):
    """Ответы на вопрос о следующей встрече."""
    yes = "yes"          # 🔥 Да
    maybe = "maybe"      # 👌 Возможно
    no = "no"            # ❌ Нет


class ScheduledBroadcast(Base):
    """
    Таблица scheduled_broadcasts — запланированные рассылки.
    Хранит контент, сегмент, время отправки и RSVP-настройки.
    """
    __tablename__ = "scheduled_broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    segment: Mapped[str] = mapped_column(String(64), nullable=False)

    content_type: Mapped[str] = mapped_column(String(16), nullable=False)
    content_text: Mapped[Optional[str]] = mapped_column(String(4096), nullable=True)
    content_file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[BroadcastStatus] = mapped_column(
        Enum(BroadcastStatus, native_enum=False),
        default=BroadcastStatus.pending,
        nullable=False,
    )

    has_rsvp: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="0")
    rsvp_event_title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    rsvp_event_datetime: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    zoom_link: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    reminder_24h_sent: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="0")
    reminder_15min_sent: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="0")
    reminder_5min_sent: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="0")
    feedback_sent: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="0")

    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    fail_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    rsvps: Mapped[list["BroadcastRSVP"]] = relationship(
        "BroadcastRSVP",
        back_populates="broadcast",
        cascade="all, delete-orphan",
    )

    delivery_logs: Mapped[list["BroadcastDeliveryLog"]] = relationship(
        "BroadcastDeliveryLog",
        back_populates="broadcast",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ScheduledBroadcast(id={self.id}, status={self.status.value}, scheduled_at={self.scheduled_at})>"


class BroadcastDeliveryLog(Base):
    """
    Таблица broadcast_delivery_logs — лог доставки рассылок.
    """
    __tablename__ = "broadcast_delivery_logs"
    __table_args__ = (
        UniqueConstraint("broadcast_id", "telegram_id", name="uq_broadcast_delivery_log_broadcast_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    broadcast_id: Mapped[int] = mapped_column(
        ForeignKey("scheduled_broadcasts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    broadcast: Mapped["ScheduledBroadcast"] = relationship(
        "ScheduledBroadcast",
        back_populates="delivery_logs",
    )

    def __repr__(self) -> str:
        return f"<BroadcastDeliveryLog(id={self.id}, broadcast_id={self.broadcast_id}, tg_id={self.telegram_id}, status={self.delivery_status})>"


class BroadcastRSVP(Base):
    """
    Таблица broadcast_rsvps — ответы пользователей на RSVP.
    """
    __tablename__ = "broadcast_rsvps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    broadcast_id: Mapped[int] = mapped_column(ForeignKey("scheduled_broadcasts.id"), nullable=False, index=True)

    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    response: Mapped[RSVPResponse] = mapped_column(
        Enum(RSVPResponse, native_enum=False),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    broadcast: Mapped["ScheduledBroadcast"] = relationship("ScheduledBroadcast", back_populates="rsvps")

    def __repr__(self) -> str:
        return f"<BroadcastRSVP(id={self.id}, broadcast_id={self.broadcast_id}, response={self.response.value})>"


class EventFeedback(Base):
    """
    Таблица event_feedbacks — ответы на опрос после встречи.
    Хранит оценку, комфортность уровня и планы на следующую встречу.
    """
    __tablename__ = "event_feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    broadcast_id: Mapped[int] = mapped_column(ForeignKey("scheduled_broadcasts.id"), nullable=False, index=True)

    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    level_comfort: Mapped[Optional[LevelComfort]] = mapped_column(
        Enum(LevelComfort, native_enum=False),
        nullable=True,
    )

    will_attend_next: Mapped[Optional[WillAttendNext]] = mapped_column(
        Enum(WillAttendNext, native_enum=False),
        nullable=True,
    )

    improvement_comment: Mapped[Optional[str]] = mapped_column(
        String(2000),
        nullable=True,
    )

    awaiting_improvement_comment: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        server_default="0",
    )

    followup_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    synced_to_sheets: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        server_default="0",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    broadcast: Mapped["ScheduledBroadcast"] = relationship("ScheduledBroadcast")

    def __repr__(self) -> str:
        return f"<EventFeedback(id={self.id}, broadcast_id={self.broadcast_id}, rating={self.rating})>"


class PendingEventInvitation(Base):
    """
    Таблица pending_event_invitations — отложенные персональные приглашения на события.
    Создаётся когда пользователь купил подписку, но основная рассылка на событие уже прошла.
    Планировщик отправляет эти приглашения через 1 день после покупки.
    """
    __tablename__ = "pending_event_invitations"
    __table_args__ = (
        UniqueConstraint("telegram_id", "broadcast_id", name="uq_pending_invitation_user_broadcast"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    broadcast_id: Mapped[int] = mapped_column(
        ForeignKey("scheduled_broadcasts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    sent: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="0", index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    broadcast: Mapped["ScheduledBroadcast"] = relationship("ScheduledBroadcast")

    def __repr__(self) -> str:
        return f"<PendingEventInvitation(id={self.id}, tg_id={self.telegram_id}, broadcast_id={self.broadcast_id}, sent={self.sent})>"


class Setting(Base):
    """
    Таблица settings — хранит настройки бота (ключ-значение).
    Используется для хранения расписания и других динамических данных.
    """
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(4096), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UnauthorizedMember(Base):
    """
    Таблица unauthorized_members — временное хранилище пользователей,
    которые присоединились к каналу, но отсутствуют в БД.
    Используется для автоматического удаления неавторизованных пользователей через 15 минут.
    """
    __tablename__ = "unauthorized_members"

    # Первичный ключ
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Telegram ID пользователя
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)

    # Полное имя (first_name + last_name из Telegram)
    full_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # @username в Telegram
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Время присоединения к каналу
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<UnauthorizedMember(id={self.id}, tg_id={self.telegram_id}, joined_at={self.joined_at})>"
