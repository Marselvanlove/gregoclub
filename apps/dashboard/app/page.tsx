import { AppShellNav } from "@/components/dashboard/app-shell";
import { AutoRefresh } from "@/components/dashboard/auto-refresh";
import { ChartShell } from "@/components/dashboard/chart-shell";
import { FiltersBar } from "@/components/dashboard/filters-bar";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { OverviewCharts } from "@/components/dashboard/overview-charts";
import { UserDetailSheet } from "@/components/dashboard/user-detail-sheet";
import { Badge } from "@/components/ui/badge";
import {
  getDashboardPageData,
} from "@/lib/queries";
import { buildDashboardFiltersFromRecord, readSearchParamValue } from "@/lib/filter-params";

export const dynamic = "force-dynamic";

const OVERVIEW_PRESET_KEYS = ["all", "new", "new_no_activation", "pending", "checkout_no_payment", "paid_no_rsvp", "feedback_missing", "active", "expired"] as const;

function getMetricValue(overview: { key: string; count: number }[], key: string) {
  return overview.find((item) => item.key === key)?.count ?? 0;
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = (await searchParams) ?? {};
  const filters = buildDashboardFiltersFromRecord(params, { allowedStatusPresets: [...OVERVIEW_PRESET_KEYS] });
  const focusTelegramId = readSearchParamValue(params, "focus") ?? null;

  const rawStatusPreset = readSearchParamValue(params, "statusPreset");
  const statusPreset = rawStatusPreset && OVERVIEW_PRESET_KEYS.includes(rawStatusPreset as (typeof OVERVIEW_PRESET_KEYS)[number]) ? rawStatusPreset : null;
  const pageData = await getDashboardPageData(filters, focusTelegramId);
  const { overview, trend, funnel, buckets, signals, journey, payments, rsvps, feedbacks } = pageData;
  const spotlightBuckets = buckets.slice(0, 4);
  const attentionTotal = buckets.reduce((sum, bucket) => sum + bucket.users, 0);
  const overviewCards = [
    {
      key: "waiting-payment",
      label: "Ждут оплату",
      value: String(getMetricValue(overview, "pending")),
      helper: "Люди, которые ещё не купили и требуют внимания команды.",
      tone: "accent" as const,
    },
    {
      key: "active-paid",
      label: "Платят сейчас",
      value: String(getMetricValue(overview, "active")),
      helper: "Активные платящие пользователи прямо сейчас.",
      tone: "primary" as const,
    },
    {
      key: "attention-total",
      label: "Нужно разобрать",
      value: String(attentionTotal),
      helper: "Суммарно по понятным зонам риска: оплата, встречи и удержание.",
      tone: "neutral" as const,
    },
    {
      key: "revenue",
      label: "Выручка",
      value: `${getMetricValue(overview, "revenue")} €`,
      helper: "Сумма успешных оплат по текущей выборке.",
      tone: "accent" as const,
    },
  ];

  return (
    <>
      <AppShellNav />
      <main className="dashboard-shell pb-16">
        <AutoRefresh className="mb-6" />
        <section className="glass-panel overflow-hidden rounded-[calc(var(--radius)+0.2rem)] px-6 py-7 md:px-8 md:py-8">
          <div className="grid gap-8 xl:grid-cols-[1.25fr_0.75fr]">
            <div className="space-y-6">
              <div className="space-y-4">
                <div className="micro-label">Обзор</div>
                <h1 className="max-w-4xl text-[clamp(2.6rem,5vw,5rem)] font-semibold leading-[0.92] tracking-[-0.07em] text-foreground">
                  Что происходит сейчас
                </h1>
                <p className="max-w-3xl text-base leading-7 text-muted-foreground md:text-lg">
                  Короткий срез по продажам, рискам и платящим: что проседает и куда команде смотреть в первую очередь.
                </p>
              </div>
            </div>

            <div className="grid gap-4">
              <div className="rounded-[calc(var(--radius)-0.2rem)] border border-border/60 bg-white/60 p-5 shadow-[var(--shadow-soft)]">
                <div className="micro-label">Сейчас важно</div>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">
                  Сначала посмотрите, где тормозится покупка. Затем проверьте, что происходит с платящими: дошли ли до встречи и оставили ли отзыв.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section id="pulse" className="mt-8 space-y-6">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {overviewCards.map((item) => (
              <KpiCard
                key={item.key}
                label={item.label}
                value={item.value}
                helper={item.helper}
                tone={item.tone}
              />
            ))}
          </div>

          <FiltersBar initialValues={filters} initialStatusPreset={statusPreset} presetKeys={[...OVERVIEW_PRESET_KEYS]} />

          <OverviewCharts trend={trend} funnel={funnel} />
        </section>

        <section id="funnel" className="mt-8">
          <ChartShell
            label="Сегодня важно"
            title="Где нужна ручная работа"
            description="Крупные причины, из-за которых пользователи сейчас застревают."
          >
            <div className="space-y-3">
              {spotlightBuckets.length === 0 ? (
                <div className="rounded-[calc(var(--radius)-0.35rem)] border border-dashed border-border/60 bg-white/50 px-4 py-8 text-sm text-muted-foreground">
                  Сейчас нет активных проблемных сегментов.
                </div>
              ) : (
                spotlightBuckets.map((bucket) => (
                  <div
                    key={bucket.bucket}
                    className="flex items-center justify-between rounded-[calc(var(--radius)-0.45rem)] border border-border/60 bg-white/58 px-4 py-3"
                  >
                    <div className="space-y-1">
                      <div className="micro-label">Причина</div>
                      <div className="font-medium text-foreground">{bucket.bucket}</div>
                    </div>
                    <div className="text-3xl font-semibold tracking-[-0.05em] text-primary">{bucket.users}</div>
                  </div>
                ))
              )}
            </div>
          </ChartShell>
        </section>

        <section id="signals" className="mt-8 grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
          <ChartShell
            label="Последние действия"
            title="Что изменилось недавно"
            description="Последние понятные события по клиентам и платящим."
          >
            <div className="space-y-3">
              {signals.length === 0 ? (
                <div className="rounded-[calc(var(--radius)-0.35rem)] border border-dashed border-border/60 bg-white/50 px-4 py-8 text-sm text-muted-foreground">
                  Лента сигналов пуста.
                </div>
              ) : (
                signals.map((signal) => (
                  <div key={`${signal.telegramId}-${signal.createdAt}-${signal.eventName}`} className="rounded-[calc(var(--radius)-0.4rem)] border border-border/60 bg-white/58 p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="primary">{signal.eventName}</Badge>
                      {signal.provider ? <Badge variant="accent">{signal.provider}</Badge> : null}
                      <span className="text-xs text-muted-foreground">{signal.createdAt}</span>
                    </div>
                    <div className="mt-3 text-sm text-foreground">
                      {signal.fullName ?? "Без имени"} {signal.username ? `· @${signal.username}` : ""}
                    </div>
                  </div>
                ))
              )}
            </div>
          </ChartShell>

          <ChartShell
            label="Коротко"
            title="Как читать обзор"
            description="Три вопроса, на которые этот экран должен отвечать за минуту."
          >
            <div className="space-y-4 text-sm leading-7 text-muted-foreground">
              <p>
                <strong className="text-foreground">Просела ли сейчас покупка и где именно?</strong>
              </p>
              <p>
                <strong className="text-foreground">Что требует ручного внимания команды сегодня?</strong>
              </p>
              <p>
                <strong className="text-foreground">Что происходит с платящими после покупки?</strong>
              </p>
            </div>
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
