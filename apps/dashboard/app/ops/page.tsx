import { AppShellNav } from "@/components/dashboard/app-shell";
import { AutoRefresh } from "@/components/dashboard/auto-refresh";
import { ChartShell } from "@/components/dashboard/chart-shell";
import { FiltersBar } from "@/components/dashboard/filters-bar";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { OpsBoard } from "@/components/dashboard/ops-board";
import { UserDetailSheet } from "@/components/dashboard/user-detail-sheet";
import { Badge } from "@/components/ui/badge";
import { buildDashboardFiltersFromRecord, readSearchParamValue } from "@/lib/filter-params";
import { getOpsPageData } from "@/lib/queries";

export const dynamic = "force-dynamic";

const OPS_PRESET_KEYS = ["all", "new", "new_no_activation", "pending", "checkout_no_payment"] as const;

function formatRate(rate: number | null) {
  if (rate === null) return "—";
  return `${Math.round(rate * 100)}%`;
}

export default async function OpsPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = (await searchParams) ?? {};
  const filters = buildDashboardFiltersFromRecord(params, { allowedStatusPresets: [...OPS_PRESET_KEYS] });
  const focusTelegramId = readSearchParamValue(params, "focus") ?? null;
  const rawStatusPreset = readSearchParamValue(params, "statusPreset");
  const statusPreset = rawStatusPreset && OPS_PRESET_KEYS.includes(rawStatusPreset as (typeof OPS_PRESET_KEYS)[number]) ? rawStatusPreset : null;

  const pageData = await getOpsPageData(filters, focusTelegramId);
  const { overview, funnel, buckets, lanes, signals, journey, payments, rsvps, feedbacks } = pageData;
  const prePaymentSteps = new Set([
    "Регистрация",
    "Начали диалог",
    "Получили первый шаг",
    "Выбрали ситуацию",
    "Дошли до предложения",
    "Перешли к оплате",
    "Открыли оплату",
  ]);
  const queueFunnel = funnel.filter((item) => prePaymentSteps.has(item.step));
  const funnelMax = Math.max(...queueFunnel.map((item) => item.total), 1);

  return (
    <>
      <AppShellNav />
      <main className="dashboard-shell space-y-8 pb-16">
        <AutoRefresh />

        <section className="glass-panel overflow-hidden rounded-[calc(var(--radius)+0.15rem)] px-6 py-7 md:px-8">
          <div className="grid gap-8 xl:grid-cols-[1.2fr_0.8fr]">
            <div className="space-y-5">
              <div className="micro-label">Очередь</div>
              <h1 className="max-w-4xl text-[clamp(2.4rem,5vw,4.4rem)] font-semibold leading-[0.94] tracking-[-0.07em]">
                Кто не дошёл до покупки
              </h1>
              <p className="max-w-3xl text-base leading-7 text-muted-foreground">
                Рабочий экран по тем, кто зашёл в бота, но не купил: где именно человек остановился и кого разбирать в первую очередь.
              </p>
            </div>

            <div className="rounded-[calc(var(--radius)-0.3rem)] border border-border/60 bg-white/60 p-5 shadow-[var(--shadow-soft)]">
              <div className="micro-label">Фокус команды</div>
              <div className="mt-4 space-y-3 text-sm leading-7 text-muted-foreground">
                <p>
                  <strong className="text-foreground">Сначала</strong>: те, кто уже открыл оплату, но не завершил покупку.
                </p>
                <p>
                  <strong className="text-foreground">Потом</strong>: новые, которые быстро остыли и не сделали следующий шаг.
                </p>
                <p>
                  <strong className="text-foreground">Отдельно</strong>: те, по кому уже понятна причина и нужен ручной контакт.
                </p>
              </div>
            </div>
          </div>
        </section>

        <FiltersBar initialValues={filters} initialStatusPreset={statusPreset} presetKeys={[...OPS_PRESET_KEYS]} />

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {overview.map((item) => (
            <KpiCard
              key={item.key}
              label={item.label}
              value={item.rate === null ? String(item.count) : `${item.count} · ${formatRate(item.rate)}`}
              helper={item.helper}
              tone={item.tone}
            />
          ))}
        </section>

        <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
          <ChartShell
            label="Воронка"
            title="Как идут до оплаты"
            description="Только шаги до покупки: где путь ломается раньше всего."
          >
            <div className="space-y-3">
              {queueFunnel.map((row) => (
                <div
                  key={row.step}
                  className="rounded-[calc(var(--radius)-0.4rem)] border border-border/60 bg-white/58 p-4"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="font-medium text-foreground">{row.step}</div>
                      <div className="mt-1 text-sm text-muted-foreground">За 30 дней: {row.recent}</div>
                    </div>
                    <div className="text-3xl font-semibold tracking-[-0.05em] text-primary">{row.total}</div>
                  </div>
                  <div className="mt-4 h-2 overflow-hidden rounded-full bg-muted/70">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${Math.max((row.total / funnelMax) * 100, row.total > 0 ? 10 : 0)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </ChartShell>

          <ChartShell
            label="Причины"
            title="Где именно нужна ручная работа"
            description="Крупные причины, почему человек не дошёл до покупки."
          >
            <div className="space-y-3">
              {buckets.length === 0 ? (
                <div className="rounded-[calc(var(--radius)-0.35rem)] border border-dashed border-border/60 bg-white/50 px-4 py-8 text-sm text-muted-foreground">
                  По текущим фильтрам очередь пуста.
                </div>
              ) : (
                buckets.map((bucket) => (
                  <div
                    key={bucket.bucket}
                    className="flex items-center justify-between rounded-[calc(var(--radius)-0.45rem)] border border-border/60 bg-white/58 px-4 py-3"
                  >
                    <div className="space-y-1">
                      <div className="micro-label">Сегмент</div>
                      <div className="font-medium text-foreground">{bucket.bucket}</div>
                    </div>
                    <div className="text-3xl font-semibold tracking-[-0.05em] text-accent">{bucket.users}</div>
                  </div>
                ))
              )}
            </div>
          </ChartShell>
        </section>

        <section className="space-y-6">
          <ChartShell
            label="Лейны"
            title="Кто и где остановился"
            description="Колонки для ежедневного разбора: кого нужно взять в работу прямо сейчас."
          >
            <OpsBoard initialLanes={lanes} />
          </ChartShell>
        </section>

        <section>
          <ChartShell
            label="Последние действия"
            title="Что делали недавно"
            description="Последние понятные сигналы по тем, кто ещё не купил."
          >
            <div className="space-y-3">
              {signals.length === 0 ? (
                <div className="rounded-[calc(var(--radius)-0.35rem)] border border-dashed border-border/60 bg-white/50 px-4 py-8 text-sm text-muted-foreground">
                  Лента действий пуста.
                </div>
              ) : (
                signals.map((signal) => (
                  <div
                    key={`${signal.telegramId}-${signal.createdAt}-${signal.eventName}`}
                    className="rounded-[calc(var(--radius)-0.4rem)] border border-border/60 bg-white/58 p-4"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="primary">{signal.eventName}</Badge>
                      {signal.provider ? <Badge variant="accent">{signal.provider}</Badge> : null}
                      <span className="text-xs text-muted-foreground">{signal.createdAt}</span>
                    </div>
                    <div className="mt-3 text-sm text-foreground">
                      {signal.fullName ?? "Без имени"} {signal.username ? `· @${signal.username}` : ""}
                    </div>
                    {signal.source ? <div className="mt-2 text-sm text-muted-foreground">{signal.source}</div> : null}
                  </div>
                ))
              )}
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
