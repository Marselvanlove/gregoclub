import { query } from "@/lib/db";

export type DashboardFilters = {
  from?: string | null;
  to?: string | null;
  source?: string | null;
  state?: string | null;
  tariff?: string | null;
  provider?: string | null;
  onboardingVersion?: string | null;
};

export type OverviewMetric = {
  key: string;
  label: string;
  count: number;
  rate: number | null;
};

type CountRow = {
  starts: number;
  state_picker_opened: number;
  state_selected: number;
  branch_offer_sent: number;
  schedule_opened: number;
  payment_flow_entered: number;
  tariff_selected: number;
  checkout_redirect_opened: number;
  payment_succeeded: number;
  first_rsvp_attending: number;
  first_feedback_completed: number;
};

type FunnelSqlRow = {
  onboarding_version: string;
  event_name: string;
  users: string;
};

type StuckUserRow = {
  telegram_id: string;
  full_name: string | null;
  username: string | null;
  status: string | null;
  onboarding_version: string | null;
  entry_source: string | null;
  last_event: string | null;
  last_event_at: string | null;
  state_choice: string | null;
  stuck_bucket: string | null;
};

type JourneySummaryRow = {
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
  rsvp_count: string;
  feedback_count: string;
};

type JourneyEventRow = {
  id: string;
  journey: string;
  onboarding_version: string;
  event_name: string;
  step_key: string | null;
  source: string | null;
  provider: string | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
};

type ConversionRow = {
  entry_source: string;
  state_choice: string;
  tariff: string;
  payment_provider: string;
  starts: string;
  checkout_clicks: string;
  paid_users: string;
};

const STARTS1_VERSION = "starts1";
const LEGACY_VERSIONS = ["starts"];

const OVERVIEW_STEP_CONFIG: Array<{
  key: keyof CountRow;
  label: string;
  rateBase?: keyof CountRow;
}> = [
  { key: "starts", label: "Starts" },
  { key: "state_picker_opened", label: "State Selection Rate", rateBase: "starts" },
  { key: "branch_offer_sent", label: "Offer Rate", rateBase: "starts" },
  { key: "schedule_opened", label: "Schedule Open Rate", rateBase: "starts" },
  { key: "payment_flow_entered", label: "Payment Flow Entry Rate", rateBase: "starts" },
  { key: "checkout_redirect_opened", label: "Checkout Click Rate", rateBase: "starts" },
  { key: "payment_succeeded", label: "Paid Conversion", rateBase: "starts" },
  { key: "first_rsvp_attending", label: "First RSVP Rate", rateBase: "payment_succeeded" },
  { key: "first_feedback_completed", label: "First Feedback Completion Rate", rateBase: "first_rsvp_attending" },
];

const FUNNEL_STEPS: string[] = [
  "onboarding_started",
  "state_picker_opened",
  "state_selected",
  "branch_offer_sent",
  "more_info_opened",
  "schedule_opened",
  "payment_flow_entered",
  "tariff_selected",
  "checkout_redirect_opened",
  "payment_succeeded",
  "first_rsvp_attending",
  "first_feedback_completed",
];

function sanitizeFilterValue(value?: string | null): string | null {
  if (!value) {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function normalizeFilters(filters: DashboardFilters): DashboardFilters {
  return {
    from: sanitizeFilterValue(filters.from),
    to: sanitizeFilterValue(filters.to),
    source: sanitizeFilterValue(filters.source),
    state: sanitizeFilterValue(filters.state),
    tariff: sanitizeFilterValue(filters.tariff),
    provider: sanitizeFilterValue(filters.provider),
    onboardingVersion: sanitizeFilterValue(filters.onboardingVersion),
  };
}

function buildEventScope(
  filters: DashboardFilters,
  options?: {
    alias?: string;
    profileAlias?: string;
    includeVersion?: boolean;
    startIndex?: number;
  },
): { sql: string; params: unknown[] } {
  const normalized = normalizeFilters(filters);
  const alias = options?.alias ?? "e";
  const profileAlias = options?.profileAlias ?? "p";
  const includeVersion = options?.includeVersion ?? true;
  const startIndex = options?.startIndex ?? 0;
  const clauses: string[] = [];
  const params: unknown[] = [];

  const addParam = (value: unknown): string => {
    params.push(value);
    return `$${startIndex + params.length}`;
  };

  if (normalized.from) {
    clauses.push(`${alias}.created_at >= ${addParam(normalized.from)}::timestamptz`);
  }
  if (normalized.to) {
    clauses.push(`${alias}.created_at < (${addParam(normalized.to)}::timestamptz + interval '1 day')`);
  }
  if (includeVersion && normalized.onboardingVersion) {
    clauses.push(`${alias}.onboarding_version = ${addParam(normalized.onboardingVersion)}`);
  }
  if (normalized.source) {
    clauses.push(`COALESCE(${profileAlias}.entry_source, ${alias}.source) = ${addParam(normalized.source)}`);
  }
  if (normalized.state) {
    clauses.push(`${profileAlias}.state_choice = ${addParam(normalized.state)}`);
  }
  if (normalized.provider) {
    clauses.push(`COALESCE(${profileAlias}.payment_provider, ${alias}.provider) = ${addParam(normalized.provider)}`);
  }
  if (normalized.tariff) {
    const tariffPlaceholder = addParam(normalized.tariff);
    clauses.push(
      `EXISTS (
        SELECT 1
        FROM analytics_events te
        WHERE te.telegram_id = ${alias}.telegram_id
          AND te.event_name = 'tariff_selected'
          AND te.metadata_json ->> 'tariff' = ${tariffPlaceholder}
      )`,
    );
  }

  return {
    sql: clauses.length > 0 ? `WHERE ${clauses.join(" AND ")}` : "",
    params,
  };
}

function buildProfileScope(
  filters: DashboardFilters,
  alias = "p",
  startIndex = 0,
): { sql: string; params: unknown[] } {
  const normalized = normalizeFilters(filters);
  const clauses: string[] = [];
  const params: unknown[] = [];

  const addParam = (value: unknown): string => {
    params.push(value);
    return `$${startIndex + params.length}`;
  };

  if (normalized.source) {
    clauses.push(`${alias}.entry_source = ${addParam(normalized.source)}`);
  }
  if (normalized.state) {
    clauses.push(`${alias}.state_choice = ${addParam(normalized.state)}`);
  }
  if (normalized.provider) {
    clauses.push(`${alias}.payment_provider = ${addParam(normalized.provider)}`);
  }
  if (normalized.onboardingVersion) {
    clauses.push(`${alias}.onboarding_version = ${addParam(normalized.onboardingVersion)}`);
  }

  return {
    sql: clauses.length > 0 ? `AND ${clauses.join(" AND ")}` : "",
    params,
  };
}

export async function getOverviewData(filters: DashboardFilters): Promise<OverviewMetric[]> {
  const overviewFilters = normalizeFilters({ ...filters, onboardingVersion: filters.onboardingVersion ?? STARTS1_VERSION });
  const scope = buildEventScope(overviewFilters);
  const rows = await query<CountRow>(
    `
      SELECT
        COUNT(DISTINCT e.telegram_id) FILTER (WHERE e.event_name = 'onboarding_started')::int AS starts,
        COUNT(DISTINCT e.telegram_id) FILTER (WHERE e.event_name = 'state_picker_opened')::int AS state_picker_opened,
        COUNT(DISTINCT e.telegram_id) FILTER (WHERE e.event_name = 'state_selected')::int AS state_selected,
        COUNT(DISTINCT e.telegram_id) FILTER (WHERE e.event_name = 'branch_offer_sent')::int AS branch_offer_sent,
        COUNT(DISTINCT e.telegram_id) FILTER (WHERE e.event_name = 'schedule_opened')::int AS schedule_opened,
        COUNT(DISTINCT e.telegram_id) FILTER (WHERE e.event_name = 'payment_flow_entered')::int AS payment_flow_entered,
        COUNT(DISTINCT e.telegram_id) FILTER (WHERE e.event_name = 'tariff_selected')::int AS tariff_selected,
        COUNT(DISTINCT e.telegram_id) FILTER (WHERE e.event_name = 'checkout_redirect_opened')::int AS checkout_redirect_opened,
        COUNT(DISTINCT e.telegram_id) FILTER (WHERE e.event_name = 'payment_succeeded')::int AS payment_succeeded,
        COUNT(DISTINCT e.telegram_id) FILTER (WHERE e.event_name = 'first_rsvp_attending')::int AS first_rsvp_attending,
        COUNT(DISTINCT e.telegram_id) FILTER (WHERE e.event_name = 'first_feedback_completed')::int AS first_feedback_completed
      FROM analytics_events e
      LEFT JOIN user_analytics_profiles p ON p.telegram_id = e.telegram_id
      ${scope.sql}
    `,
    scope.params,
  );

  const row = rows[0] ?? {
    starts: 0,
    state_picker_opened: 0,
    state_selected: 0,
    branch_offer_sent: 0,
    schedule_opened: 0,
    payment_flow_entered: 0,
    tariff_selected: 0,
    checkout_redirect_opened: 0,
    payment_succeeded: 0,
    first_rsvp_attending: 0,
    first_feedback_completed: 0,
  };

  return OVERVIEW_STEP_CONFIG.map((item) => {
    const count = Number(row[item.key] ?? 0);
    const baseCount = item.rateBase ? Number(row[item.rateBase] ?? 0) : 0;
    return {
      key: item.key,
      label: item.label,
      count,
      rate: item.rateBase && baseCount > 0 ? count / baseCount : null,
    };
  });
}

export async function getFunnelData(filters: DashboardFilters) {
  const normalized = normalizeFilters(filters);
  const versions = normalized.onboardingVersion
    ? [normalized.onboardingVersion]
    : [STARTS1_VERSION, ...LEGACY_VERSIONS];

  const scope = buildEventScope({ ...normalized, onboardingVersion: null }, { includeVersion: false });
  const stepsPlaceholder = `$${scope.params.length + 1}`;
  const versionsPlaceholder = `$${scope.params.length + 2}`;
  const params = [...scope.params, FUNNEL_STEPS, versions];

  const rows = await query<FunnelSqlRow>(
    `
      SELECT
        e.onboarding_version,
        e.event_name,
        COUNT(DISTINCT e.telegram_id)::text AS users
      FROM analytics_events e
      LEFT JOIN user_analytics_profiles p ON p.telegram_id = e.telegram_id
      ${scope.sql ? `${scope.sql} AND` : "WHERE"}
      e.event_name = ANY(${stepsPlaceholder}::text[])
      AND e.onboarding_version = ANY(${versionsPlaceholder}::text[])
      GROUP BY e.onboarding_version, e.event_name
      ORDER BY e.onboarding_version, e.event_name
    `,
    params,
  );

  const versionRows = new Map<string, Record<string, number>>();
  for (const row of rows) {
    const current = versionRows.get(row.onboarding_version) ?? {};
    current[row.event_name] = Number(row.users);
    versionRows.set(row.onboarding_version, current);
  }

  return FUNNEL_STEPS.map((step) => ({
    step,
    starts1: versionRows.get(STARTS1_VERSION)?.[step] ?? 0,
    legacy: LEGACY_VERSIONS.reduce((sum, version) => sum + (versionRows.get(version)?.[step] ?? 0), 0),
  }));
}

export async function getStuckUsersData(filters: DashboardFilters) {
  const profileScope = buildProfileScope(filters);
  const params = [...profileScope.params];

  if (filters.from) {
    params.push(filters.from);
  }
  const fromPlaceholder = filters.from ? `$${params.length}` : null;

  if (filters.to) {
    params.push(filters.to);
  }
  const toPlaceholder = filters.to ? `$${params.length}` : null;

  const rows = await query<StuckUserRow>(
    `
      SELECT
        p.telegram_id::text,
        u.full_name,
        u.username,
        u.status::text AS status,
        p.onboarding_version,
        p.entry_source,
        p.last_event,
        p.last_event_at::text,
        p.state_choice,
        p.stuck_bucket
      FROM user_analytics_profiles p
      LEFT JOIN users u ON u.telegram_id = p.telegram_id
      WHERE p.stuck_bucket IS NOT NULL
      ${profileScope.sql}
      ${fromPlaceholder ? `AND p.last_event_at >= ${fromPlaceholder}::timestamptz` : ""}
      ${toPlaceholder ? `AND p.last_event_at < (${toPlaceholder}::timestamptz + interval '1 day')` : ""}
      ORDER BY p.last_event_at DESC NULLS LAST, p.telegram_id DESC
      LIMIT 200
    `,
    params,
  );

  return rows.map((row) => ({
    telegramId: row.telegram_id,
    fullName: row.full_name,
    username: row.username,
    status: row.status,
    onboardingVersion: row.onboarding_version,
    entrySource: row.entry_source,
    lastEvent: row.last_event,
    lastEventAt: row.last_event_at,
    stateChoice: row.state_choice,
    stuckBucket: row.stuck_bucket,
  }));
}

export async function getUserJourneyData(telegramId: string) {
  const summaryRows = await query<JourneySummaryRow>(
    `
      SELECT
        u.telegram_id::text,
        u.full_name,
        u.username,
        u.status::text AS status,
        u.registration_date::text,
        u.subscription_end_date::text,
        p.onboarding_version,
        p.entry_source,
        p.last_event,
        p.last_event_at::text,
        p.state_choice,
        p.payment_provider,
        p.first_paid_at::text,
        p.first_rsvp_at::text,
        p.first_feedback_at::text,
        p.stuck_bucket,
        (
          SELECT COUNT(*)::text
          FROM payments pay
          WHERE pay.user_id = u.id AND pay.status = 'success'
        ) AS payments_count,
        (
          SELECT COUNT(*)::text
          FROM broadcast_rsvps r
          WHERE r.telegram_id = u.telegram_id AND r.response = 'attending'
        ) AS rsvp_count,
        (
          SELECT COUNT(*)::text
          FROM event_feedbacks f
          WHERE f.telegram_id = u.telegram_id
        ) AS feedback_count
      FROM users u
      LEFT JOIN user_analytics_profiles p ON p.telegram_id = u.telegram_id
      WHERE u.telegram_id = $1::bigint
      LIMIT 1
    `,
    [telegramId],
  );

  const timelineRows = await query<JourneyEventRow>(
    `
      SELECT
        id::text,
        journey,
        onboarding_version,
        event_name,
        step_key,
        source,
        provider,
        metadata_json,
        created_at::text
      FROM analytics_events
      WHERE telegram_id = $1::bigint
      ORDER BY created_at DESC, id DESC
      LIMIT 200
    `,
    [telegramId],
  );

  return {
    summary: summaryRows[0] ?? null,
    timeline: timelineRows.map((row) => ({
      id: row.id,
      journey: row.journey,
      onboardingVersion: row.onboarding_version,
      eventName: row.event_name,
      stepKey: row.step_key,
      source: row.source,
      provider: row.provider,
      metadata: row.metadata_json,
      createdAt: row.created_at,
    })),
  };
}

export async function getConversionData(filters: DashboardFilters) {
  const normalized = normalizeFilters(filters);
  const scope = buildEventScope({ ...normalized, onboardingVersion: null }, { includeVersion: false });
  const profileScope = buildProfileScope(normalized, "p", scope.params.length + 2);
  const params = [...scope.params, ["onboarding_started", "checkout_redirect_opened", "payment_succeeded"], ...profileScope.params];
  const eventLimit = `$${scope.params.length + 1}`;
  const tariffPlaceholder = normalized.tariff ? `$${params.length + 1}` : null;
  if (normalized.tariff) {
    params.push(normalized.tariff);
  }

  const rows = await query<ConversionRow>(
    `
      WITH base_users AS (
        SELECT DISTINCT e.telegram_id
        FROM analytics_events e
        LEFT JOIN user_analytics_profiles p ON p.telegram_id = e.telegram_id
        ${scope.sql ? `${scope.sql} AND` : "WHERE"}
        e.event_name = ANY(${eventLimit}::text[])
      ),
      user_summary AS (
        SELECT
          b.telegram_id,
          COALESCE(p.entry_source, '—') AS entry_source,
          COALESCE(p.state_choice, '—') AS state_choice,
          COALESCE(p.payment_provider, '—') AS payment_provider,
          COALESCE((
            SELECT te.metadata_json ->> 'tariff'
            FROM analytics_events te
            WHERE te.telegram_id = b.telegram_id
              AND te.event_name = 'tariff_selected'
            ORDER BY te.created_at DESC, te.id DESC
            LIMIT 1
          ), '—') AS tariff,
          EXISTS (
            SELECT 1
            FROM analytics_events s
            WHERE s.telegram_id = b.telegram_id
              AND s.event_name = 'onboarding_started'
          ) AS started,
          EXISTS (
            SELECT 1
            FROM analytics_events c
            WHERE c.telegram_id = b.telegram_id
              AND c.event_name = 'checkout_redirect_opened'
          ) AS checkout_clicked,
          EXISTS (
            SELECT 1
            FROM analytics_events pay
            WHERE pay.telegram_id = b.telegram_id
              AND pay.event_name = 'payment_succeeded'
          ) AS paid
        FROM base_users b
        LEFT JOIN user_analytics_profiles p ON p.telegram_id = b.telegram_id
        WHERE 1=1
        ${profileScope.sql}
      )
      SELECT
        entry_source,
        state_choice,
        tariff,
        payment_provider,
        COUNT(*) FILTER (WHERE started)::text AS starts,
        COUNT(*) FILTER (WHERE checkout_clicked)::text AS checkout_clicks,
        COUNT(*) FILTER (WHERE paid)::text AS paid_users
      FROM user_summary
      ${tariffPlaceholder ? `WHERE tariff = ${tariffPlaceholder}` : ""}
      GROUP BY entry_source, state_choice, tariff, payment_provider
      HAVING COUNT(*) FILTER (WHERE started OR checkout_clicked OR paid) > 0
      ORDER BY paid_users::int DESC, starts::int DESC, checkout_clicks::int DESC
      LIMIT 100
    `,
    params,
  );

  return rows.map((row) => ({
    entrySource: row.entry_source,
    stateChoice: row.state_choice,
    tariff: row.tariff,
    paymentProvider: row.payment_provider,
    starts: Number(row.starts),
    checkoutClicks: Number(row.checkout_clicks),
    paidUsers: Number(row.paid_users),
  }));
}
