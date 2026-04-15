import { AppShellNav } from "@/components/dashboard/app-shell";
import { AutoRefresh } from "@/components/dashboard/auto-refresh";
import { CallSessionsTable } from "@/components/dashboard/call-sessions-table";
import { ChartShell } from "@/components/dashboard/chart-shell";
import { FeedbackHighlights } from "@/components/dashboard/feedback-highlights";
import { FiltersBar } from "@/components/dashboard/filters-bar";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { StudentsTable } from "@/components/dashboard/students-table";
import { UserDetailSheet } from "@/components/dashboard/user-detail-sheet";
import { buildDashboardFiltersFromRecord, readSearchParamValue } from "@/lib/filter-params";
import { getCallsPageData } from "@/lib/queries";

export const dynamic = "force-dynamic";

const CALLS_PRESET_KEYS = ["all", "active", "expired", "paid_no_rsvp", "feedback_missing"] as const;

export default async function CallsPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = (await searchParams) ?? {};
  const filters = buildDashboardFiltersFromRecord(params, { allowedStatusPresets: [...CALLS_PRESET_KEYS] });
  const focusTelegramId = readSearchParamValue(params, "focus") ?? null;
  const rawStatusPreset = readSearchParamValue(params, "statusPreset");
  const statusPreset = rawStatusPreset && CALLS_PRESET_KEYS.includes(rawStatusPreset as (typeof CALLS_PRESET_KEYS)[number]) ? rawStatusPreset : null;

  const { studentSummary, sessions, feedbackHighlights, students, journey, payments, rsvps, feedbacks } =
    await getCallsPageData(filters, focusTelegramId);

  return (
    <>
      <AppShellNav />
      <main className="dashboard-shell space-y-8 pb-16">
        <AutoRefresh />

        <section className="glass-panel overflow-hidden rounded-[calc(var(--radius)+0.15rem)] px-6 py-7 md:px-8">
          <div className="grid gap-8 xl:grid-cols-[1.2fr_0.8fr]">
            <div className="space-y-5">
              <div className="micro-label">Созвоны</div>
              <h1 className="max-w-4xl text-[clamp(2.4rem,5vw,4.4rem)] font-semibold leading-[0.94] tracking-[-0.07em]">
                Платящие и бывшие участники
              </h1>
              <p className="max-w-3xl text-base leading-7 text-muted-foreground">
                Здесь только те, кто уже платил: кто активен сейчас, кто перестал платить и что происходит с созвонами и отзывами.
              </p>
            </div>

            <div className="rounded-[calc(var(--radius)-0.3rem)] border border-border/60 bg-white/60 p-5 shadow-[var(--shadow-soft)]">
              <div className="micro-label">Что отслеживать</div>
              <div className="mt-4 space-y-3 text-sm leading-7 text-muted-foreground">
                <p>
                  <strong className="text-foreground">Подписка</strong>: сколько платят сейчас и сколько уже истекло.
                </p>
                <p>
                  <strong className="text-foreground">Встречи</strong>: кто записывается и реально доходит.
                </p>
                <p>
                  <strong className="text-foreground">Отзывы</strong>: что пишут после встречи и где отклик ещё не собран.
                </p>
              </div>
            </div>
          </div>
        </section>

        <FiltersBar initialValues={filters} initialStatusPreset={statusPreset} presetKeys={[...CALLS_PRESET_KEYS]} />

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <KpiCard
            label="Платят сейчас"
            value={String(studentSummary.currentPaid)}
            helper="Пользователи с активной оплатой прямо сейчас."
            tone="primary"
          />
          <KpiCard
            label="Истекли / ушли"
            value={String(studentSummary.formerPaid)}
            helper="Покупали раньше, но сейчас подписка не активна."
            tone="accent"
          />
          <KpiCard
            label="Были на созвоне"
            value={String(studentSummary.attendedUsers)}
            helper="Сколько оплативших уже были хотя бы на одном созвоне."
            tone="primary"
          />
          <KpiCard
            label="Оставили отзыв"
            value={String(studentSummary.feedbackUsers)}
            helper={
              studentSummary.avgRating == null
                ? "Количество пользователей с хотя бы одним отзывом."
                : `Средняя оценка по отзывам: ${studentSummary.avgRating}`
            }
            tone="neutral"
          />
          <KpiCard
            label="Без отзыва"
            value={String(studentSummary.noFeedbackCount)}
            helper="Оплатили, дошли до встреч, но отзыв ещё не собран."
            tone="accent"
          />
          <KpiCard
            label="Без записи"
            value={String(studentSummary.withoutRsvpCount)}
            helper="Оплатили, но ещё не записались ни на один созвон."
            tone="neutral"
          />
        </section>

        <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
          <ChartShell
            label="Созвоны"
            title="Что происходит по встречам"
            description="По каждой встрече: сколько записалось, сколько дошло и какая средняя оценка."
          >
            <CallSessionsTable rows={sessions} />
          </ChartShell>

          <ChartShell
            label="Отзывы"
            title="Последние комментарии"
            description="Свежие отзывы от платящих пользователей."
          >
            <FeedbackHighlights rows={feedbackHighlights} />
          </ChartShell>
        </section>

        <section>
          <ChartShell
            label="Клиенты"
            title="Активные и бывшие платящие"
            description="Только те, кто уже платил: оплаты, встречи, отзывы и текущая активность."
          >
            <StudentsTable rows={students} limit={80} />
          </ChartShell>
        </section>
      </main>

      <UserDetailSheet
        summary={journey?.summary ?? null}
        timeline={journey?.timeline ?? []}
        payments={payments}
        rsvps={rsvps}
        feedbacks={feedbacks}
        open={Boolean(focusTelegramId)}
      />
    </>
  );
}
