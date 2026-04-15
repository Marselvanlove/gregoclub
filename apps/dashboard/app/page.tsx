import { logoutAction } from "@/app/login/actions";
import { requireDashboardAuth } from "@/lib/auth";
import {
  getConversionData,
  getFunnelData,
  getOverviewData,
  getStuckUsersData,
  getUserJourneyData,
} from "@/lib/queries";

export const dynamic = "force-dynamic";

function formatRate(rate: number | null): string {
  if (rate === null) {
    return "—";
  }
  return `${Math.round(rate * 100)}%`;
}

function FilterField({
  label,
  name,
  defaultValue,
}: {
  label: string;
  name: string;
  defaultValue?: string | null;
}) {
  return (
    <label>
      <div className="muted">{label}</div>
      <input className="input" name={name} defaultValue={defaultValue ?? ""} />
    </label>
  );
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  await requireDashboardAuth();
  const params = (await searchParams) ?? {};
  const value = (key: string) => {
    const raw = params[key];
    return Array.isArray(raw) ? raw[0] : raw;
  };

  const filters = {
    from: value("from") ?? null,
    to: value("to") ?? null,
    source: value("source") ?? null,
    state: value("state") ?? null,
    tariff: value("tariff") ?? null,
    provider: value("provider") ?? null,
    onboardingVersion: value("onboardingVersion") ?? null,
  };

  const journeyTelegramId = value("telegramId") ?? null;

  const [overview, funnel, stuckUsers, conversions, journey] = await Promise.all([
    getOverviewData(filters),
    getFunnelData(filters),
    getStuckUsersData(filters),
    getConversionData(filters),
    journeyTelegramId ? getUserJourneyData(journeyTelegramId) : Promise.resolve(null),
  ]);

  return (
    <main>
      <div className="page-header">
        <div>
          <h1 className="page-title">Grego Club Analytics</h1>
          <p className="page-subtitle">
            Онбординг `/starts1`, оплата, CRM и activation в одном admin-only dashboard.
            Основной акцент: где пользователи застряли, что посмотрели и где теряется конверсия.
          </p>
        </div>
        <form action={logoutAction} className="logout-form">
          <button type="submit">Выйти</button>
        </form>
      </div>

      <section className="panel">
        <div className="section-header">
          <div>
            <h2>Фильтры</h2>
            <p>Фильтры применяются к overview, funnel, stuck users и conversions.</p>
          </div>
        </div>
        <form className="filter-form">
          <FilterField label="From (YYYY-MM-DD)" name="from" defaultValue={filters.from} />
          <FilterField label="To (YYYY-MM-DD)" name="to" defaultValue={filters.to} />
          <FilterField label="Source" name="source" defaultValue={filters.source} />
          <FilterField label="State" name="state" defaultValue={filters.state} />
          <FilterField label="Tariff" name="tariff" defaultValue={filters.tariff} />
          <FilterField label="Provider" name="provider" defaultValue={filters.provider} />
          <FilterField label="Onboarding Version" name="onboardingVersion" defaultValue={filters.onboardingVersion} />
          <button type="submit">Применить</button>
        </form>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h2>Overview</h2>
            <p>Ключевые показатели нового онбординга `/starts1`.</p>
          </div>
        </div>
        <div className="metrics-grid">
          {overview.map((item) => (
            <div className="metric-card" key={item.key}>
              <div className="label">{item.label}</div>
              <div className="value">{item.count}</div>
              <div className="rate">{item.rate === null ? "Без rate" : `Rate: ${formatRate(item.rate)}`}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h2>Funnel</h2>
            <p>Сравнение `/starts1` и legacy `/starts` по основным шагам.</p>
          </div>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Step</th>
              <th>/starts1</th>
              <th>Legacy</th>
            </tr>
          </thead>
          <tbody>
            {funnel.map((row) => (
              <tr key={row.step}>
                <td>{row.step}</td>
                <td>{row.starts1}</td>
                <td>{row.legacy}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="subgrid">
        <div className="panel">
          <div className="section-header">
            <div>
              <h2>Where Users Get Stuck</h2>
              <p>Snapshot по активным stuck bucket-правилам.</p>
            </div>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Status</th>
                <th>Source</th>
                <th>State</th>
                <th>Last Event</th>
                <th>Bucket</th>
              </tr>
            </thead>
            <tbody>
              {stuckUsers.length === 0 ? (
                <tr>
                  <td colSpan={6} className="muted">
                    В активных stuck bucket сейчас пусто.
                  </td>
                </tr>
              ) : (
                stuckUsers.map((row) => (
                  <tr key={`${row.telegramId}-${row.stuckBucket}`}>
                    <td>
                      <strong>{row.fullName ?? "Без имени"}</strong>
                      <div className="muted">
                        {row.username ? `@${row.username}` : row.telegramId}
                      </div>
                    </td>
                    <td>{row.status ?? "—"}</td>
                    <td>{row.entrySource ?? "—"}</td>
                    <td>{row.stateChoice ?? "—"}</td>
                    <td>
                      {row.lastEvent ?? "—"}
                      <div className="muted">{row.lastEventAt ?? "—"}</div>
                    </td>
                    <td>
                      <span className="badge">{row.stuckBucket ?? "—"}</span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <div className="section-header">
            <div>
              <h2>CRM / Ops</h2>
              <p>Быстрый user journey lookup по Telegram ID.</p>
            </div>
          </div>
          <form className="journey-form">
            <FilterField label="Telegram ID" name="telegramId" defaultValue={journeyTelegramId} />
            <button type="submit">Открыть journey</button>
          </form>
          <p className="page-subtitle">
            Используйте этот блок для follow-up: pending, paid without RSVP, attended without feedback.
          </p>
        </div>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h2>Conversions</h2>
            <p>Сводка по source / state / tariff / provider.</p>
          </div>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>State</th>
              <th>Tariff</th>
              <th>Provider</th>
              <th>Starts</th>
              <th>Checkout Clicks</th>
              <th>Paid Users</th>
            </tr>
          </thead>
          <tbody>
            {conversions.length === 0 ? (
              <tr>
                <td colSpan={7} className="muted">
                  Нет данных по выбранным фильтрам.
                </td>
              </tr>
            ) : (
              conversions.map((row) => (
                <tr key={`${row.entrySource}-${row.stateChoice}-${row.tariff}-${row.paymentProvider}`}>
                  <td>{row.entrySource}</td>
                  <td>{row.stateChoice}</td>
                  <td>{row.tariff}</td>
                  <td>{row.paymentProvider}</td>
                  <td>{row.starts}</td>
                  <td>{row.checkoutClicks}</td>
                  <td>{row.paidUsers}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      {journey ? (
        <section className="subgrid">
          <div className="panel">
            <div className="section-header">
              <div>
                <h2>User Journey</h2>
                <p>Полный таймлайн событий пользователя.</p>
              </div>
            </div>
            <div className="timeline-list">
              {journey.timeline.length === 0 ? (
                <div className="muted">Для этого Telegram ID пока нет событий.</div>
              ) : (
                journey.timeline.map((event) => (
                  <div className="timeline-item" key={event.id}>
                    <time>{event.createdAt}</time>
                    <strong>{event.eventName}</strong>
                    <div className="muted">
                      {event.journey} · {event.onboardingVersion} · {event.stepKey ?? "—"} · {event.source ?? "—"}
                    </div>
                    {event.metadata ? <code>{JSON.stringify(event.metadata)}</code> : null}
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="panel">
            <div className="section-header">
              <div>
                <h2>User Summary</h2>
                <p>Snapshot для CRM и дашборда.</p>
              </div>
            </div>
            {!journey.summary ? (
              <div className="muted">Пользователь не найден.</div>
            ) : (
              <table className="data-table">
                <tbody>
                  <tr>
                    <th>Имя</th>
                    <td>{journey.summary.full_name ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Username</th>
                    <td>{journey.summary.username ? `@${journey.summary.username}` : "—"}</td>
                  </tr>
                  <tr>
                    <th>Status</th>
                    <td>{journey.summary.status ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Onboarding</th>
                    <td>{journey.summary.onboarding_version ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Entry Source</th>
                    <td>{journey.summary.entry_source ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Last Event</th>
                    <td>{journey.summary.last_event ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>State</th>
                    <td>{journey.summary.state_choice ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Payment Provider</th>
                    <td>{journey.summary.payment_provider ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>First Paid</th>
                    <td>{journey.summary.first_paid_at ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>First RSVP</th>
                    <td>{journey.summary.first_rsvp_at ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>First Feedback</th>
                    <td>{journey.summary.first_feedback_at ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Stuck Bucket</th>
                    <td>{journey.summary.stuck_bucket ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Payments / RSVP / Feedback</th>
                    <td>
                      {journey.summary.payments_count} / {journey.summary.rsvp_count} / {journey.summary.feedback_count}
                    </td>
                  </tr>
                </tbody>
              </table>
            )}
          </div>
        </section>
      ) : null}
    </main>
  );
}
