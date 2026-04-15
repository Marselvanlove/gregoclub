import { cache } from "react";

import { getDatabaseKind, hasDatabaseUrl, query, readSqliteRows } from "@/lib/db";

export type DashboardFilters = {
  from?: string | null;
  to?: string | null;
  source?: string | null;
  state?: string | null;
  status?: string | null;
  tariff?: string | null;
  provider?: string | null;
  onboardingVersion?: string | null;
};

export type OverviewMetric = {
  key: string;
  label: string;
  count: number;
  rate: number | null;
  tone?: "primary" | "accent" | "neutral";
  helper: string;
};

export type FunnelRow = {
  step: string;
  total: number;
  recent: number;
};

export type TrendPoint = {
  day: string;
  registrations: number;
  payments: number;
  rsvps: number;
  feedbacks: number;
};

export type BucketSummary = {
  bucket: string;
  users: number;
};

export type StuckUserRecord = {
  telegramId: string;
  fullName: string | null;
  username: string | null;
  status: string | null;
  paymentProvider: string | null;
  lastEvent: string | null;
  lastEventAt: string | null;
  stuckBucket: string | null;
};

export type SignalFeedRecord = {
  telegramId: string;
  fullName: string | null;
  username: string | null;
  eventName: string;
  source: string | null;
  stepKey: string | null;
  provider: string | null;
  onboardingVersion: string;
  createdAt: string;
};

export type JourneySummary = {
  telegram_id: string;
  full_name: string | null;
  username: string | null;
  status: string | null;
  registration_date: string | null;
  subscription_end_date: string | null;
  onboarding_version: string | null;
  entry_source: string | null;
  last_event: string | null;
  last_event_at: string | null;
  state_choice: string | null;
  payment_provider: string | null;
  first_paid_at: string | null;
  first_rsvp_at: string | null;
  first_feedback_at: string | null;
  stuck_bucket: string | null;
  payments_count: string;
  total_paid: string;
  last_payment_at: string | null;
  rsvp_count: string;
  feedback_count: string;
  actions_7d: string;
  actions_30d: string;
  last_action_at: string | null;
};

export type JourneyEvent = {
  id: string;
  journey: string;
  onboardingVersion: string;
  eventName: string;
  stepKey: string | null;
  source: string | null;
  provider: string | null;
  metadata: Record<string, unknown> | null;
  createdAt: string;
};

export type ConversionRecord = {
  status: string;
  paymentProvider: string;
  paymentsCount: number;
  paidUsers: number;
  rsvpUsers: number;
  feedbackUsers: number;
};

export type StudentPortfolioSummary = {
  currentPaid: number;
  formerPaid: number;
  revenueTotal: number;
  avgActions30d: number;
  avgRating: number | null;
  noFeedbackCount: number;
};

export type StudentRow = {
  telegramId: string;
  fullName: string | null;
  username: string | null;
  status: string;
  entrySource: string;
  paymentProvider: string;
  paymentsCount: number;
  totalPaid: number;
  lastPaymentAt: string | null;
  actions7d: number;
  actions30d: number;
  lastActionAt: string | null;
  attendingCount: number;
  feedbackCount: number;
  avgRating: number | null;
};

export type PaymentRecord = {
  id: string;
  date: string;
  amount: number;
  provider: string;
  status: string;
};

export type RsvpRecord = {
  id: string;
  eventTitle: string;
  eventDate: string | null;
  response: string;
  createdAt: string;
};

export type FeedbackRecord = {
  id: string;
  eventTitle: string;
  eventDate: string | null;
  rating: number | null;
  comment: string | null;
  level: string | null;
  nextVisit: string | null;
  createdAt: string;
};

export type DashboardPageData = {
  overview: OverviewMetric[];
  trend: TrendPoint[];
  funnel: FunnelRow[];
  buckets: BucketSummary[];
  stuckUsers: StuckUserRecord[];
  conversions: ConversionRecord[];
  signals: SignalFeedRecord[];
  studentSummary: StudentPortfolioSummary;
  students: StudentRow[];
  journey: {
    summary: JourneySummary | null;
    timeline: JourneyEvent[];
  } | null;
  payments: PaymentRecord[];
  rsvps: RsvpRecord[];
  feedbacks: FeedbackRecord[];
};

export type OpsPageData = {
  users: StuckUserRecord[];
  buckets: BucketSummary[];
  journey: {
    summary: JourneySummary | null;
    timeline: JourneyEvent[];
  } | null;
  payments: PaymentRecord[];
  rsvps: RsvpRecord[];
  feedbacks: FeedbackRecord[];
};

type RawUser = {
  id: number;
  telegram_id: number;
  username: string | null;
  full_name: string | null;
  language_level: string | null;
  status: string;
  registration_date: string | null;
  subscription_end_date: string | null;
  last_pay_click_at: string | null;
  expired_at: string | null;
  email: string | null;
  payment_provider: string | null;
};

type RawPayment = {
  id: number;
  user_id: number;
  amount: number;
  currency: string | null;
  status: string;
  created_at: string | null;
  provider: string | null;
};

type RawRsvp = {
  id: number;
  broadcast_id: number;
  telegram_id: number;
  response: string | null;
  created_at: string | null;
};

type RawFeedback = {
  id: number;
  broadcast_id: number;
  telegram_id: number;
  rating: number | null;
  level_comfort: string | null;
  will_attend_next: string | null;
  improvement_comment: string | null;
  created_at: string | null;
};

type RawBroadcast = {
  id: number;
  content_text: string | null;
  rsvp_event_title: string | null;
  rsvp_event_datetime: string | null;
};

type RawAnalyticsEvent = {
  id: number;
  telegram_id: number;
  journey: string;
  onboarding_version: string | null;
  event_name: string;
  step_key: string | null;
  source: string | null;
  provider: string | null;
  metadata_json: Record<string, unknown> | string | null;
  created_at: string | null;
};

type RawAnalyticsProfile = {
  telegram_id: number;
  onboarding_version: string | null;
  entry_source: string | null;
  last_event: string | null;
  last_event_at: string | null;
  state_choice: string | null;
  payment_provider: string | null;
  first_paid_at: string | null;
  first_rsvp_at: string | null;
  first_feedback_at: string | null;
  stuck_bucket: string | null;
};

type RawData = {
  users: RawUser[];
  payments: RawPayment[];
  rsvps: RawRsvp[];
  feedbacks: RawFeedback[];
  broadcasts: RawBroadcast[];
  analyticsEvents: RawAnalyticsEvent[];
  analyticsProfiles: RawAnalyticsProfile[];
};

type PreparedUser = {
  user: RawUser;
  profile: RawAnalyticsProfile | null;
  timeline: JourneyEvent[];
  payments: RawPayment[];
  successPayments: RawPayment[];
  rsvps: RawRsvp[];
  attendingRsvps: RawRsvp[];
  feedbacks: RawFeedback[];
  totalPaid: number;
  avgRating: number | null;
  paymentProvider: string | null;
  firstPaidAt: string | null;
  lastPaymentAt: string | null;
  firstRsvpAt: string | null;
  lastRsvpAt: string | null;
  firstFeedbackAt: string | null;
  lastFeedbackAt: string | null;
  lastActionAt: string | null;
  lastEvent: string | null;
  lastEventAt: string | null;
  attentionBucket: string | null;
  attentionReferenceAt: string | null;
  actions7d: number;
  actions30d: number;
};

type PreparedData = {
  users: PreparedUser[];
  usersByTelegramId: Map<string, PreparedUser>;
};

const STATUS_LABELS: Record<string, string> = {
  new: "Новый",
  pending: "Ожидает оплату",
  active: "Оплатил",
  expired: "Истёк",
};

const PROVIDER_LABELS: Record<string, string> = {
  stripe: "Stripe",
  lavatop: "LavaTop",
};

const PAYMENT_STATUS_LABELS: Record<string, string> = {
  success: "Успешно",
  failed: "Ошибка",
  created: "Создано",
  paid: "Оплачено",
  cancelled: "Отменено",
};

const RSVP_LABELS: Record<string, string> = {
  attending: "Записался",
  declined: "Не пойдёт",
};

const LEVEL_LABELS: Record<string, string> = {
  perfect: "Уровень подошёл",
  hard: "Было сложно",
  easy: "Было легко",
};

const NEXT_VISIT_LABELS: Record<string, string> = {
  yes: "Придёт",
  maybe: "Возможно придёт",
  no: "Не планирует",
};

const EVENT_LABELS: Record<string, string> = {
  registration_created: "Зарегистрировался",
  checkout_opened: "Открыл оплату",
  payment_recorded: "Оплата получена",
  rsvp_attending: "Записался на встречу",
  rsvp_declined: "Отказался от встречи",
  feedback_completed: "Оставил отзыв",
  onboarding_started: "Начали диалог",
  state_picker_opened: "Открыли выбор ситуации",
  state_selected: "Выбрали ситуацию",
  branch_offer_sent: "Увидели предложение",
  more_info_opened: "Открыли подробности",
  schedule_opened: "Открыли расписание",
  payment_flow_entered: "Перешли к оплате",
  tariff_selected: "Выбрали тариф",
  checkout_redirect_opened: "Нажали оплатить",
  payment_succeeded: "Оплатили",
  first_rsvp_attending: "Записались",
  first_feedback_completed: "Оставили отзыв",
  pending_reminder_sent: "Отправлено напоминание",
  new_reminder_sent: "Напоминание новому клиенту",
};

const ATTENTION_BUCKETS = {
  checkoutNoPayment: "Нажали оплатить, но не оплатили",
  paidNoRsvp: "Оплатили, но не записались",
  attendedNoFeedback: "Были на встрече, но без отзыва",
  expired: "Подписка истекла",
} as const;

function humanizeStatus(value: string | null | undefined) {
  if (!value) return "—";
  return STATUS_LABELS[value] ?? value;
}

function humanizeProvider(value: string | null | undefined) {
  if (!value) return "—";
  return PROVIDER_LABELS[value] ?? value;
}

function humanizePaymentStatus(value: string | null | undefined) {
  if (!value) return "—";
  return PAYMENT_STATUS_LABELS[value] ?? value;
}

function humanizeRsvp(value: string | null | undefined) {
  if (!value) return "—";
  return RSVP_LABELS[value] ?? value;
}

function humanizeLevel(value: string | null | undefined) {
  if (!value) return "—";
  return LEVEL_LABELS[value] ?? value;
}

function humanizeNextVisit(value: string | null | undefined) {
  if (!value) return "—";
  return NEXT_VISIT_LABELS[value] ?? value;
}

function humanizeEventName(value: string | null | undefined) {
  if (!value) return "—";
  return EVENT_LABELS[value] ?? value;
}

function humanizeBucket(value: string | null | undefined) {
  if (!value) return "—";
  return value;
}

function sanitizeFilterValue(value?: string | null): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function normalizeFilters(filters: DashboardFilters): DashboardFilters {
  return {
    from: sanitizeFilterValue(filters.from),
    to: sanitizeFilterValue(filters.to),
    source: sanitizeFilterValue(filters.source),
    state: sanitizeFilterValue(filters.state),
    status: sanitizeFilterValue(filters.status),
    tariff: sanitizeFilterValue(filters.tariff),
    provider: sanitizeFilterValue(filters.provider),
    onboardingVersion: sanitizeFilterValue(filters.onboardingVersion),
  };
}

function toNumber(value: unknown) {
  if (typeof value === "number") return value;
  if (typeof value === "string" && value.length > 0) return Number(value);
  return 0;
}

function dateKey(value: string | null | undefined) {
  return value ? value.slice(0, 10) : null;
}

function compareDesc(left: string | null | undefined, right: string | null | undefined) {
  return (right ?? "").localeCompare(left ?? "");
}

function formatDayLabel(key: string) {
  const label = new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(`${key}T00:00:00Z`));

  return label.replace(".", "");
}

function buildDayKeys(startKey: string, endKey: string) {
  const keys: string[] = [];
  const cursor = new Date(`${startKey}T00:00:00Z`);
  const end = new Date(`${endKey}T00:00:00Z`);

  while (cursor <= end && keys.length < 31) {
    keys.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }

  return keys;
}

function buildTrendWindow(filters: DashboardFilters) {
  const today = new Date();
  const todayKey = today.toISOString().slice(0, 10);

  if (filters.from && filters.to && filters.from <= filters.to) {
    return buildDayKeys(filters.from, filters.to);
  }

  if (filters.from) {
    const end = new Date(`${filters.from}T00:00:00Z`);
    end.setUTCDate(end.getUTCDate() + 13);
    return buildDayKeys(filters.from, end.toISOString().slice(0, 10));
  }

  if (filters.to) {
    const start = new Date(`${filters.to}T00:00:00Z`);
    start.setUTCDate(start.getUTCDate() - 13);
    return buildDayKeys(start.toISOString().slice(0, 10), filters.to);
  }

  const start = new Date(`${todayKey}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - 13);
  return buildDayKeys(start.toISOString().slice(0, 10), todayKey);
}

function isWithinLastDays(value: string | null | undefined, days: number) {
  const key = dateKey(value);
  if (!key) return false;

  const current = new Date();
  const todayKey = current.toISOString().slice(0, 10);
  const start = new Date(`${todayKey}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - (days - 1));

  return key >= start.toISOString().slice(0, 10) && key <= todayKey;
}

function matchesDateRange(value: string | null | undefined, filters: DashboardFilters) {
  const key = dateKey(value);
  if (!filters.from && !filters.to) return true;
  if (!key) return false;
  if (filters.from && key < filters.from) return false;
  if (filters.to && key > filters.to) return false;
  return true;
}

function parseMetadata(value: RawAnalyticsEvent["metadata_json"]) {
  if (!value) return null;
  if (typeof value === "object") return value;
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function getRemoteDashboardOrigin() {
  const explicitOrigin = process.env.DASHBOARD_REMOTE_ORIGIN?.trim();
  if (explicitOrigin) {
    return explicitOrigin.replace(/\/$/, "");
  }

  if (process.env.VERCEL || process.env.VERCEL_URL) {
    return "https://club.hablacongrego.com";
  }

  return null;
}

async function fetchRemotePageData<T>(pathname: string, filters: DashboardFilters, focusTelegramId?: string | null): Promise<T | null> {
  const origin = getRemoteDashboardOrigin();
  if (!origin) return null;

  const params = new URLSearchParams();
  const normalized = normalizeFilters(filters);

  Object.entries(normalized).forEach(([key, value]) => {
    if (!value) return;
    params.set(key, value);
  });

  if (focusTelegramId) {
    params.set("focus", focusTelegramId);
  }

  const query = params.toString();
  const response = await fetch(`${origin}${pathname}${query ? `?${query}` : ""}`, {
    next: { revalidate: 60 },
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`Remote dashboard request failed: ${pathname} ${response.status}`);
  }

  const payload = (await response.json()) as { data: T };
  return payload.data;
}

function uniqueBy<T>(items: T[], keyOf: (item: T) => string) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = keyOf(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

const loadRawData = cache(async (): Promise<RawData | null> => {
  if (!hasDatabaseUrl()) {
    return null;
  }

  const databaseKind = getDatabaseKind();
  const statements = {
    users: `
      SELECT
        id,
        telegram_id,
        username,
        full_name,
        language_level,
        status,
        registration_date,
        subscription_end_date,
        last_pay_click_at,
        expired_at,
        email,
        payment_provider
      FROM users
    `,
    payments: `
      SELECT
        id,
        user_id,
        amount,
        currency,
        status,
        created_at,
        provider
      FROM payments
    `,
    rsvps: `
      SELECT
        id,
        broadcast_id,
        telegram_id,
        response,
        created_at
      FROM broadcast_rsvps
    `,
    feedbacks: `
      SELECT
        id,
        broadcast_id,
        telegram_id,
        rating,
        level_comfort,
        will_attend_next,
        improvement_comment,
        created_at
      FROM event_feedbacks
    `,
    broadcasts: `
      SELECT
        id,
        content_text,
        rsvp_event_title,
        rsvp_event_datetime
      FROM scheduled_broadcasts
    `,
    analyticsEvents: `
      SELECT
        id,
        telegram_id,
        journey,
        onboarding_version,
        event_name,
        step_key,
        source,
        provider,
        metadata_json,
        created_at
      FROM analytics_events
    `,
    analyticsProfiles: `
      SELECT
        telegram_id,
        onboarding_version,
        entry_source,
        last_event,
        last_event_at,
        state_choice,
        payment_provider,
        first_paid_at,
        first_rsvp_at,
        first_feedback_at,
        stuck_bucket
      FROM user_analytics_profiles
    `,
  };

  if (databaseKind === "sqlite") {
    return {
      users: readSqliteRows<RawUser>(statements.users),
      payments: readSqliteRows<RawPayment>(statements.payments),
      rsvps: readSqliteRows<RawRsvp>(statements.rsvps),
      feedbacks: readSqliteRows<RawFeedback>(statements.feedbacks),
      broadcasts: readSqliteRows<RawBroadcast>(statements.broadcasts),
      analyticsEvents: readSqliteRows<RawAnalyticsEvent>(statements.analyticsEvents),
      analyticsProfiles: readSqliteRows<RawAnalyticsProfile>(statements.analyticsProfiles),
    };
  }

  return {
    users: await query<RawUser>(statements.users),
    payments: await query<RawPayment>(statements.payments),
    rsvps: await query<RawRsvp>(statements.rsvps),
    feedbacks: await query<RawFeedback>(statements.feedbacks),
    broadcasts: await query<RawBroadcast>(statements.broadcasts),
    analyticsEvents: await query<RawAnalyticsEvent>(statements.analyticsEvents),
    analyticsProfiles: await query<RawAnalyticsProfile>(statements.analyticsProfiles),
  };
});

const loadPreparedData = cache(async (): Promise<PreparedData | null> => {
  const rawData = await loadRawData();
  if (!rawData) return null;

  const broadcastsById = new Map(rawData.broadcasts.map((broadcast) => [broadcast.id, broadcast]));
  const profilesByTelegramId = new Map(rawData.analyticsProfiles.map((profile) => [String(profile.telegram_id), profile]));

  const paymentsByUserId = new Map<number, RawPayment[]>();
  rawData.payments.forEach((payment) => {
    const bucket = paymentsByUserId.get(payment.user_id) ?? [];
    bucket.push(payment);
    paymentsByUserId.set(payment.user_id, bucket);
  });

  const rsvpsByTelegramId = new Map<string, RawRsvp[]>();
  rawData.rsvps.forEach((rsvp) => {
    const key = String(rsvp.telegram_id);
    const bucket = rsvpsByTelegramId.get(key) ?? [];
    bucket.push(rsvp);
    rsvpsByTelegramId.set(key, bucket);
  });

  const feedbacksByTelegramId = new Map<string, RawFeedback[]>();
  rawData.feedbacks.forEach((feedback) => {
    const key = String(feedback.telegram_id);
    const bucket = feedbacksByTelegramId.get(key) ?? [];
    bucket.push(feedback);
    feedbacksByTelegramId.set(key, bucket);
  });

  const eventsByTelegramId = new Map<string, RawAnalyticsEvent[]>();
  rawData.analyticsEvents.forEach((event) => {
    const key = String(event.telegram_id);
    const bucket = eventsByTelegramId.get(key) ?? [];
    bucket.push(event);
    eventsByTelegramId.set(key, bucket);
  });

  const preparedUsers = rawData.users.map<PreparedUser>((user) => {
    const telegramId = String(user.telegram_id);
    const profile = profilesByTelegramId.get(telegramId) ?? null;
    const payments = [...(paymentsByUserId.get(user.id) ?? [])].sort((left, right) => compareDesc(left.created_at, right.created_at));
    const successPayments = payments.filter((payment) => payment.status === "success");
    const rsvps = [...(rsvpsByTelegramId.get(telegramId) ?? [])].sort((left, right) => compareDesc(left.created_at, right.created_at));
    const attendingRsvps = rsvps.filter((rsvp) => rsvp.response === "attending");
    const feedbacks = [...(feedbacksByTelegramId.get(telegramId) ?? [])].sort((left, right) => compareDesc(left.created_at, right.created_at));
    const analyticsEvents = [...(eventsByTelegramId.get(telegramId) ?? [])].sort((left, right) => compareDesc(left.created_at, right.created_at));

    const timeline = uniqueBy(
      [
        user.registration_date
          ? {
              id: `registration:${telegramId}`,
              journey: "registration",
              onboardingVersion: profile?.onboarding_version ?? "—",
              eventName: humanizeEventName("registration_created"),
              stepKey: null,
              source: "Пользователь создан",
              provider: null,
              metadata: null,
              createdAt: user.registration_date,
            }
          : null,
        user.last_pay_click_at
          ? {
              id: `checkout:${telegramId}`,
              journey: "payment",
              onboardingVersion: profile?.onboarding_version ?? "—",
              eventName: humanizeEventName("checkout_opened"),
              stepKey: "checkout",
              source: "Последний клик по оплате",
              provider: user.payment_provider ? humanizeProvider(user.payment_provider) : null,
              metadata: null,
              createdAt: user.last_pay_click_at,
            }
          : null,
        ...payments
          .filter((payment) => payment.created_at)
          .map<JourneyEvent>((payment) => ({
            id: `payment:${payment.id}`,
            journey: "payment",
            onboardingVersion: profile?.onboarding_version ?? "—",
            eventName: humanizeEventName("payment_recorded"),
            stepKey: payment.status,
            source: payment.currency ? `${payment.currency} / ${humanizePaymentStatus(payment.status)}` : humanizePaymentStatus(payment.status),
            provider: payment.provider ? humanizeProvider(payment.provider) : null,
            metadata: { amount: payment.amount, status: payment.status },
            createdAt: payment.created_at!,
          })),
        ...rsvps
          .filter((rsvp) => rsvp.created_at)
          .map<JourneyEvent>((rsvp) => {
            const broadcast = broadcastsById.get(rsvp.broadcast_id);
            return {
              id: `rsvp:${rsvp.id}`,
              journey: "rsvp",
              onboardingVersion: profile?.onboarding_version ?? "—",
              eventName: humanizeEventName(rsvp.response === "attending" ? "rsvp_attending" : "rsvp_declined"),
              stepKey: rsvp.response,
              source: broadcast?.rsvp_event_title ?? broadcast?.content_text ?? "Встреча",
              provider: null,
              metadata: { broadcastId: rsvp.broadcast_id },
              createdAt: rsvp.created_at!,
            };
          }),
        ...feedbacks
          .filter((feedback) => feedback.created_at)
          .map<JourneyEvent>((feedback) => {
            const broadcast = broadcastsById.get(feedback.broadcast_id);
            return {
              id: `feedback:${feedback.id}`,
              journey: "feedback",
              onboardingVersion: profile?.onboarding_version ?? "—",
              eventName: humanizeEventName("feedback_completed"),
              stepKey: feedback.rating == null ? null : String(feedback.rating),
              source: broadcast?.rsvp_event_title ?? broadcast?.content_text ?? "Обратная связь",
              provider: null,
              metadata: {
                rating: feedback.rating,
                level: feedback.level_comfort,
                nextVisit: feedback.will_attend_next,
              },
              createdAt: feedback.created_at!,
            };
          }),
        ...analyticsEvents
          .filter((event) => event.created_at)
          .map<JourneyEvent>((event) => ({
            id: `analytics:${event.id}`,
            journey: event.journey,
            onboardingVersion: event.onboarding_version ?? "—",
            eventName: humanizeEventName(event.event_name),
            stepKey: event.step_key,
            source: event.source ?? event.step_key ?? "analytics_events",
            provider: event.provider ? humanizeProvider(event.provider) : null,
            metadata: parseMetadata(event.metadata_json),
            createdAt: event.created_at!,
          })),
      ].filter(Boolean) as JourneyEvent[],
      (item) => item.id,
    ).sort((left, right) => compareDesc(left.createdAt, right.createdAt));

    const firstPaidAt = successPayments.at(-1)?.created_at ?? profile?.first_paid_at ?? null;
    const lastPaymentAt = successPayments[0]?.created_at ?? profile?.first_paid_at ?? null;
    const firstRsvpAt = attendingRsvps.at(-1)?.created_at ?? profile?.first_rsvp_at ?? null;
    const lastRsvpAt = attendingRsvps[0]?.created_at ?? null;
    const firstFeedbackAt = feedbacks.at(-1)?.created_at ?? profile?.first_feedback_at ?? null;
    const lastFeedbackAt = feedbacks[0]?.created_at ?? null;
    const lastActionAt = timeline[0]?.createdAt ?? null;
    const lastEvent = profile?.last_event ? humanizeEventName(profile.last_event) : timeline[0]?.eventName ?? null;
    const lastEventAt = profile?.last_event_at ?? timeline[0]?.createdAt ?? null;
    const totalPaid = successPayments.reduce((sum, payment) => sum + toNumber(payment.amount), 0);
    const ratings = feedbacks.map((feedback) => feedback.rating).filter((rating): rating is number => rating != null);
    const avgRating = ratings.length > 0 ? Math.round((ratings.reduce((sum, rating) => sum + rating, 0) / ratings.length) * 10) / 10 : null;
    const paymentProvider = successPayments[0]?.provider ?? user.payment_provider ?? profile?.payment_provider ?? null;

    let attentionBucket: string | null = null;
    let attentionReferenceAt: string | null = null;

    if (successPayments.length === 0 && user.last_pay_click_at && (user.status === "pending" || user.status === "new")) {
      attentionBucket = ATTENTION_BUCKETS.checkoutNoPayment;
      attentionReferenceAt = user.last_pay_click_at;
    } else if (successPayments.length > 0 && attendingRsvps.length === 0) {
      attentionBucket = ATTENTION_BUCKETS.paidNoRsvp;
      attentionReferenceAt = lastPaymentAt;
    } else if (attendingRsvps.length > 0 && feedbacks.length === 0) {
      attentionBucket = ATTENTION_BUCKETS.attendedNoFeedback;
      attentionReferenceAt = lastRsvpAt;
    } else if (user.status === "expired") {
      attentionBucket = ATTENTION_BUCKETS.expired;
      attentionReferenceAt = user.expired_at ?? user.subscription_end_date ?? lastPaymentAt;
    }

    return {
      user,
      profile,
      timeline,
      payments,
      successPayments,
      rsvps,
      attendingRsvps,
      feedbacks,
      totalPaid,
      avgRating,
      paymentProvider,
      firstPaidAt,
      lastPaymentAt,
      firstRsvpAt,
      lastRsvpAt,
      firstFeedbackAt,
      lastFeedbackAt,
      lastActionAt,
      lastEvent,
      lastEventAt,
      attentionBucket,
      attentionReferenceAt,
      actions7d: timeline.filter((event) => isWithinLastDays(event.createdAt, 7)).length,
      actions30d: timeline.filter((event) => isWithinLastDays(event.createdAt, 30)).length,
    };
  });

  return {
    users: preparedUsers,
    usersByTelegramId: new Map(preparedUsers.map((item) => [String(item.user.telegram_id), item])),
  };
});

function matchesUserFilters(user: PreparedUser, filters: DashboardFilters) {
  const normalized = normalizeFilters(filters);

  if (normalized.status && user.user.status !== normalized.status) return false;
  if (normalized.provider && user.paymentProvider !== normalized.provider) return false;
  if (normalized.source && user.profile?.entry_source !== normalized.source) return false;
  if (normalized.onboardingVersion && user.profile?.onboarding_version !== normalized.onboardingVersion) return false;
  if (normalized.state && ![user.profile?.state_choice, user.user.language_level].includes(normalized.state)) return false;

  if (!normalized.from && !normalized.to) {
    return true;
  }

  return user.timeline.some((event) => matchesDateRange(event.createdAt, normalized));
}

async function getFilteredUsers(filters: DashboardFilters) {
  const preparedData = await loadPreparedData();
  if (!preparedData) return [];
  return preparedData.users.filter((user) => matchesUserFilters(user, filters));
}

function buildTrendPoints(users: PreparedUser[], filters: DashboardFilters) {
  const keys = buildTrendWindow(filters);
  const trendMap = new Map(
    keys.map((key) => [
      key,
      {
        day: formatDayLabel(key),
        registrations: 0,
        payments: 0,
        rsvps: 0,
        feedbacks: 0,
      },
    ]),
  );

  users.forEach((user) => {
    const registrationKey = dateKey(user.user.registration_date);
    if (registrationKey && trendMap.has(registrationKey)) {
      trendMap.get(registrationKey)!.registrations += 1;
    }

    user.successPayments.forEach((payment) => {
      const key = dateKey(payment.created_at);
      if (key && trendMap.has(key)) {
        trendMap.get(key)!.payments += 1;
      }
    });

    user.attendingRsvps.forEach((rsvp) => {
      const key = dateKey(rsvp.created_at);
      if (key && trendMap.has(key)) {
        trendMap.get(key)!.rsvps += 1;
      }
    });

    user.feedbacks.forEach((feedback) => {
      const key = dateKey(feedback.created_at);
      if (key && trendMap.has(key)) {
        trendMap.get(key)!.feedbacks += 1;
      }
    });
  });

  return keys.map((key) => trendMap.get(key)!);
}

function countUsersWith(users: PreparedUser[], predicate: (user: PreparedUser) => boolean) {
  return users.reduce((total, user) => total + (predicate(user) ? 1 : 0), 0);
}

export async function getOverviewData(filters: DashboardFilters): Promise<OverviewMetric[]> {
  const users = await getFilteredUsers(filters);
  const totalUsers = users.length;
  const pendingUsers = countUsersWith(users, (user) => user.user.status === "pending");
  const activeUsers = countUsersWith(users, (user) => user.user.status === "active");
  const expiredUsers = countUsersWith(users, (user) => user.user.status === "expired");
  const paidUsers = countUsersWith(users, (user) => user.successPayments.length > 0);
  const rsvpUsers = countUsersWith(users, (user) => user.attendingRsvps.length > 0);
  const feedbackUsers = countUsersWith(users, (user) => user.feedbacks.length > 0);
  const revenue = users.reduce((sum, user) => sum + user.totalPaid, 0);

  return [
    {
      key: "registered",
      label: "В выборке",
      count: totalUsers,
      rate: null,
      tone: "neutral",
      helper: "Пользователи, попавшие под текущие фильтры и окно активности.",
    },
    {
      key: "pending",
      label: "Ожидают оплату",
      count: pendingUsers,
      rate: totalUsers > 0 ? pendingUsers / totalUsers : null,
      tone: "accent",
      helper: "Текущий pending-статус в реальной базе.",
    },
    {
      key: "active",
      label: "Активные",
      count: activeUsers,
      rate: totalUsers > 0 ? activeUsers / totalUsers : null,
      tone: "primary",
      helper: "Пользователи с активной подпиской прямо сейчас.",
    },
    {
      key: "expired",
      label: "Истекли",
      count: expiredUsers,
      rate: totalUsers > 0 ? expiredUsers / totalUsers : null,
      tone: "neutral",
      helper: "Пользователи, у которых подписка уже закончилась.",
    },
    {
      key: "paid",
      label: "С оплатой",
      count: paidUsers,
      rate: totalUsers > 0 ? paidUsers / totalUsers : null,
      tone: "primary",
      helper: "Пользователи с хотя бы одной успешной оплатой.",
    },
    {
      key: "rsvp",
      label: "С записью на встречу",
      count: rsvpUsers,
      rate: paidUsers > 0 ? rsvpUsers / paidUsers : null,
      tone: "primary",
      helper: "Из оплативших: сколько уже записывались на встречи.",
    },
    {
      key: "feedback",
      label: "С отзывом",
      count: feedbackUsers,
      rate: rsvpUsers > 0 ? feedbackUsers / rsvpUsers : null,
      tone: "neutral",
      helper: "Из тех, кто доходил до встречи: сколько оставили отзыв.",
    },
    {
      key: "revenue",
      label: "Выручка",
      count: Math.round(revenue),
      rate: null,
      tone: "accent",
      helper: "Сумма успешных оплат по текущей выборке.",
    },
  ];
}

export async function getFunnelData(filters: DashboardFilters): Promise<FunnelRow[]> {
  const users = await getFilteredUsers(filters);

  return [
    {
      step: "Зарегистрировались",
      total: users.length,
      recent: countUsersWith(users, (user) => isWithinLastDays(user.user.registration_date, 30)),
    },
    {
      step: "Оплатили",
      total: countUsersWith(users, (user) => user.successPayments.length > 0),
      recent: countUsersWith(users, (user) => user.successPayments.some((payment) => isWithinLastDays(payment.created_at, 30))),
    },
    {
      step: "Записались",
      total: countUsersWith(users, (user) => user.attendingRsvps.length > 0),
      recent: countUsersWith(users, (user) => user.attendingRsvps.some((rsvp) => isWithinLastDays(rsvp.created_at, 30))),
    },
    {
      step: "Оставили отзыв",
      total: countUsersWith(users, (user) => user.feedbacks.length > 0),
      recent: countUsersWith(users, (user) => user.feedbacks.some((feedback) => isWithinLastDays(feedback.created_at, 30))),
    },
  ];
}

export async function getTrendData(filters: DashboardFilters): Promise<TrendPoint[]> {
  const users = await getFilteredUsers(filters);
  return buildTrendPoints(users, normalizeFilters(filters));
}

export async function getBucketSummaryData(filters: DashboardFilters): Promise<BucketSummary[]> {
  const users = await getFilteredUsers(filters);
  const counts = new Map<string, number>();

  users.forEach((user) => {
    if (!user.attentionBucket) return;
    counts.set(user.attentionBucket, (counts.get(user.attentionBucket) ?? 0) + 1);
  });

  return [...counts.entries()]
    .map(([bucket, count]) => ({ bucket, users: count }))
    .sort((left, right) => right.users - left.users || left.bucket.localeCompare(right.bucket, "ru"));
}

export async function getStuckUsersData(filters: DashboardFilters): Promise<StuckUserRecord[]> {
  const users = await getFilteredUsers(filters);

  return users
    .filter((user) => user.attentionBucket)
    .sort((left, right) => compareDesc(left.attentionReferenceAt ?? left.lastActionAt, right.attentionReferenceAt ?? right.lastActionAt))
    .slice(0, 200)
    .map((user) => ({
      telegramId: String(user.user.telegram_id),
      fullName: user.user.full_name,
      username: user.user.username,
      status: humanizeStatus(user.user.status),
      paymentProvider: humanizeProvider(user.paymentProvider),
      lastEvent: user.lastEvent,
      lastEventAt: user.lastEventAt,
      stuckBucket: humanizeBucket(user.attentionBucket),
    }));
}

export async function getSignalFeedData(filters: DashboardFilters): Promise<SignalFeedRecord[]> {
  const users = await getFilteredUsers(filters);

  return users
    .flatMap((user) =>
      user.timeline.slice(0, 6).map((event) => ({
        telegramId: String(user.user.telegram_id),
        fullName: user.user.full_name,
        username: user.user.username,
        eventName: event.eventName,
        source: event.source,
        stepKey: event.stepKey,
        provider: event.provider,
        onboardingVersion: event.onboardingVersion,
        createdAt: event.createdAt,
      })),
    )
    .sort((left, right) => compareDesc(left.createdAt, right.createdAt))
    .slice(0, 18);
}

export async function getUserJourneyData(telegramId: string): Promise<{
  summary: JourneySummary | null;
  timeline: JourneyEvent[];
}> {
  const preparedData = await loadPreparedData();
  if (!preparedData) {
    return { summary: null, timeline: [] };
  }

  const user = preparedData.usersByTelegramId.get(String(telegramId));
  if (!user) {
    return { summary: null, timeline: [] };
  }

  return {
    summary: {
      telegram_id: String(user.user.telegram_id),
      full_name: user.user.full_name,
      username: user.user.username,
      status: humanizeStatus(user.user.status),
      registration_date: user.user.registration_date,
      subscription_end_date: user.user.subscription_end_date,
      onboarding_version: user.profile?.onboarding_version ?? "—",
      entry_source: user.profile?.entry_source ?? "—",
      last_event: user.lastEvent,
      last_event_at: user.lastEventAt,
      state_choice: user.profile?.state_choice ?? user.user.language_level ?? "—",
      payment_provider: humanizeProvider(user.paymentProvider),
      first_paid_at: user.firstPaidAt,
      first_rsvp_at: user.firstRsvpAt,
      first_feedback_at: user.firstFeedbackAt,
      stuck_bucket: user.attentionBucket,
      payments_count: String(user.successPayments.length),
      total_paid: String(Math.round(user.totalPaid)),
      last_payment_at: user.lastPaymentAt,
      rsvp_count: String(user.attendingRsvps.length),
      feedback_count: String(user.feedbacks.length),
      actions_7d: String(user.actions7d),
      actions_30d: String(user.actions30d),
      last_action_at: user.lastActionAt,
    },
    timeline: user.timeline.slice(0, 200),
  };
}

export async function getConversionData(filters: DashboardFilters): Promise<ConversionRecord[]> {
  const users = await getFilteredUsers(filters);
  const groups = new Map<string, ConversionRecord>();

  users
    .filter((user) => user.successPayments.length > 0)
    .forEach((user) => {
      const status = humanizeStatus(user.user.status);
      const provider = humanizeProvider(user.paymentProvider);
      const key = `${status}:${provider}`;
      const group = groups.get(key) ?? {
        status,
        paymentProvider: provider,
        paymentsCount: 0,
        paidUsers: 0,
        rsvpUsers: 0,
        feedbackUsers: 0,
      };

      group.paymentsCount += user.successPayments.length;
      group.paidUsers += 1;
      group.rsvpUsers += user.attendingRsvps.length > 0 ? 1 : 0;
      group.feedbackUsers += user.feedbacks.length > 0 ? 1 : 0;
      groups.set(key, group);
    });

  return [...groups.values()].sort(
    (left, right) =>
      right.paymentsCount - left.paymentsCount ||
      right.paidUsers - left.paidUsers ||
      left.status.localeCompare(right.status, "ru"),
  );
}

export async function getStudentPortfolioSummary(filters: DashboardFilters): Promise<StudentPortfolioSummary> {
  const paidUsers = (await getFilteredUsers(filters)).filter((user) => user.successPayments.length > 0);

  if (paidUsers.length === 0) {
    return {
      currentPaid: 0,
      formerPaid: 0,
      revenueTotal: 0,
      avgActions30d: 0,
      avgRating: null,
      noFeedbackCount: 0,
    };
  }

  const ratings = paidUsers.map((user) => user.avgRating).filter((value): value is number => value != null);

  return {
    currentPaid: paidUsers.filter((user) => user.user.status === "active").length,
    formerPaid: paidUsers.filter((user) => user.user.status === "expired").length,
    revenueTotal: paidUsers.reduce((sum, user) => sum + user.totalPaid, 0),
    avgActions30d: Math.round((paidUsers.reduce((sum, user) => sum + user.actions30d, 0) / paidUsers.length) * 10) / 10,
    avgRating: ratings.length > 0 ? Math.round((ratings.reduce((sum, rating) => sum + rating, 0) / ratings.length) * 10) / 10 : null,
    noFeedbackCount: paidUsers.filter((user) => user.feedbacks.length === 0).length,
  };
}

export async function getStudentsData(filters: DashboardFilters): Promise<StudentRow[]> {
  const users = (await getFilteredUsers(filters)).filter((user) => user.successPayments.length > 0);

  return users
    .sort((left, right) => {
      if (left.user.status === "active" && right.user.status !== "active") return -1;
      if (left.user.status !== "active" && right.user.status === "active") return 1;
      return compareDesc(left.lastActionAt ?? left.lastPaymentAt, right.lastActionAt ?? right.lastPaymentAt);
    })
    .slice(0, 200)
    .map((user) => ({
      telegramId: String(user.user.telegram_id),
      fullName: user.user.full_name,
      username: user.user.username,
      status: humanizeStatus(user.user.status),
      entrySource: user.profile?.entry_source ?? "—",
      paymentProvider: humanizeProvider(user.paymentProvider),
      paymentsCount: user.successPayments.length,
      totalPaid: user.totalPaid,
      lastPaymentAt: user.lastPaymentAt,
      actions7d: user.actions7d,
      actions30d: user.actions30d,
      lastActionAt: user.lastActionAt,
      attendingCount: user.attendingRsvps.length,
      feedbackCount: user.feedbacks.length,
      avgRating: user.avgRating,
    }));
}

export async function getUserPaymentsData(telegramId: string): Promise<PaymentRecord[]> {
  const preparedData = await loadPreparedData();
  const user = preparedData?.usersByTelegramId.get(String(telegramId));

  if (!user) return [];

  return user.payments.slice(0, 20).map((payment) => ({
    id: String(payment.id),
    date: payment.created_at ?? "—",
    amount: toNumber(payment.amount),
    provider: humanizeProvider(payment.provider),
    status: humanizePaymentStatus(payment.status),
  }));
}

export async function getUserRsvpsData(telegramId: string): Promise<RsvpRecord[]> {
  const preparedData = await loadPreparedData();
  const user = preparedData?.usersByTelegramId.get(String(telegramId));

  if (!user) return [];

  const rawData = await loadRawData();
  const broadcastsById = new Map((rawData?.broadcasts ?? []).map((broadcast) => [broadcast.id, broadcast]));

  return user.rsvps.slice(0, 20).map((rsvp) => {
    const broadcast = broadcastsById.get(rsvp.broadcast_id);
    return {
      id: String(rsvp.id),
      eventTitle: broadcast?.rsvp_event_title ?? broadcast?.content_text ?? "Без названия",
      eventDate: broadcast?.rsvp_event_datetime ?? null,
      response: humanizeRsvp(rsvp.response),
      createdAt: rsvp.created_at ?? "—",
    };
  });
}

export async function getUserFeedbacksData(telegramId: string): Promise<FeedbackRecord[]> {
  const preparedData = await loadPreparedData();
  const user = preparedData?.usersByTelegramId.get(String(telegramId));

  if (!user) return [];

  const rawData = await loadRawData();
  const broadcastsById = new Map((rawData?.broadcasts ?? []).map((broadcast) => [broadcast.id, broadcast]));

  return user.feedbacks.slice(0, 20).map((feedback) => {
    const broadcast = broadcastsById.get(feedback.broadcast_id);
    return {
      id: String(feedback.id),
      eventTitle: broadcast?.rsvp_event_title ?? broadcast?.content_text ?? "Без названия",
      eventDate: broadcast?.rsvp_event_datetime ?? null,
      rating: feedback.rating,
      comment: feedback.improvement_comment,
      level: humanizeLevel(feedback.level_comfort),
      nextVisit: humanizeNextVisit(feedback.will_attend_next),
      createdAt: feedback.created_at ?? "—",
    };
  });
}

async function computeDashboardPageData(filters: DashboardFilters, focusTelegramId?: string | null): Promise<DashboardPageData> {
  const [overview, trend, funnel, buckets, stuckUsers, conversions, signals, studentSummary, students, journey, payments, rsvps, feedbacks] =
    await Promise.all([
      getOverviewData(filters),
      getTrendData(filters),
      getFunnelData(filters),
      getBucketSummaryData(filters),
      getStuckUsersData(filters),
      getConversionData(filters),
      getSignalFeedData(filters),
      getStudentPortfolioSummary(filters),
      getStudentsData(filters),
      focusTelegramId ? getUserJourneyData(focusTelegramId) : Promise.resolve(null),
      focusTelegramId ? getUserPaymentsData(focusTelegramId) : Promise.resolve([]),
      focusTelegramId ? getUserRsvpsData(focusTelegramId) : Promise.resolve([]),
      focusTelegramId ? getUserFeedbacksData(focusTelegramId) : Promise.resolve([]),
    ]);

  return {
    overview,
    trend,
    funnel,
    buckets,
    stuckUsers,
    conversions,
    signals,
    studentSummary,
    students,
    journey,
    payments,
    rsvps,
    feedbacks,
  };
}

async function computeOpsPageData(filters: DashboardFilters, focusTelegramId?: string | null): Promise<OpsPageData> {
  const [users, buckets, journey, payments, rsvps, feedbacks] = await Promise.all([
    getStuckUsersData(filters),
    getBucketSummaryData(filters),
    focusTelegramId ? getUserJourneyData(focusTelegramId) : Promise.resolve(null),
    focusTelegramId ? getUserPaymentsData(focusTelegramId) : Promise.resolve([]),
    focusTelegramId ? getUserRsvpsData(focusTelegramId) : Promise.resolve([]),
    focusTelegramId ? getUserFeedbacksData(focusTelegramId) : Promise.resolve([]),
  ]);

  return {
    users,
    buckets,
    journey,
    payments,
    rsvps,
    feedbacks,
  };
}

export async function getDashboardPageData(filters: DashboardFilters, focusTelegramId?: string | null): Promise<DashboardPageData> {
  if (!hasDatabaseUrl()) {
    const remoteData = await fetchRemotePageData<DashboardPageData>("/dashboard/api/page-data", filters, focusTelegramId);
    if (remoteData) return remoteData;
  }

  return computeDashboardPageData(filters, focusTelegramId);
}

export async function getOpsPageData(filters: DashboardFilters, focusTelegramId?: string | null): Promise<OpsPageData> {
  if (!hasDatabaseUrl()) {
    const remoteData = await fetchRemotePageData<OpsPageData>("/dashboard/api/ops-data", filters, focusTelegramId);
    if (remoteData) return remoteData;
  }

  return computeOpsPageData(filters, focusTelegramId);
}
