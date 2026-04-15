import { Sparkles } from "lucide-react";
import { AttentionTable } from "@/components/dashboard/attention-table";
import { AppShellNav } from "@/components/dashboard/app-shell";
import { AutoRefresh } from "@/components/dashboard/auto-refresh";
import { ChartShell } from "@/components/dashboard/chart-shell";
import { FiltersBar } from "@/components/dashboard/filters-bar";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { OverviewCharts } from "@/components/dashboard/overview-charts";
import { StudentsTable } from "@/components/dashboard/students-table";
import { UserDetailSheet } from "@/components/dashboard/user-detail-sheet";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  getDashboardPageData,
} from "@/lib/queries";

export const dynamic = "force-dynamic";

function formatRate(rate: number | null) {
  if (rate === null) return "—";
  return `${Math.round(rate * 100)}%`;
}

function readValue(params: Record<string, string | string[] | undefined>, key: string) {
  const value = params[key];
  return Array.isArray(value) ? value[0] : value;
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = (await searchParams) ?? {};

  const filters = {
    from: readValue(params, "from") ?? null,
    to: readValue(params, "to") ?? null,
    source: readValue(params, "source") ?? null,
    state: readValue(params, "state") ?? null,
    status: readValue(params, "status") ?? null,
    tariff: readValue(params, "tariff") ?? null,
    provider: readValue(params, "provider") ?? null,
    onboardingVersion: readValue(params, "onboardingVersion") ?? null,
  };
  const focusTelegramId = readValue(params, "focus") ?? null;

  const { overview, trend, funnel, buckets, stuckUsers, conversions, signals, studentSummary, students, journey, payments, rsvps, feedbacks } =
    await getDashboardPageData(filters, focusTelegramId);

  const spotlightBuckets = buckets.slice(0, 4);

  return (
    <>
      <AppShellNav />
      <main className="dashboard-shell pb-16">
        <AutoRefresh className="mb-6" />
        <section className="glass-panel overflow-hidden rounded-[calc(var(--radius)+0.2rem)] px-6 py-7 md:px-8 md:py-8">
          <div className="grid gap-8 xl:grid-cols-[1.25fr_0.75fr]">
            <div className="space-y-6">
              <div className="space-y-4">
                <div className="micro-label">Аналитика</div>
                <h1 className="max-w-4xl text-[clamp(2.6rem,5vw,5rem)] font-semibold leading-[0.92] tracking-[-0.07em] text-foreground">
                  Аналитика GregoClub
                </h1>
                <p className="max-w-3xl text-base leading-7 text-muted-foreground md:text-lg">
                  Живые цифры из продовой базы: регистрации, оплаты, записи на встречи и отзывы.
                </p>
              </div>
            </div>

            <div className="grid gap-4">
              <div className="rounded-[calc(var(--radius)-0.2rem)] border border-border/60 bg-white/60 p-5 shadow-[var(--shadow-soft)]">
                <div className="micro-label">Сейчас важно</div>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">
                  Смотрите, кто завис перед оплатой, кто оплатил без записи на встречу и где ещё не собран feedback.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section id="pulse" className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {overview.map((item) => (
              <KpiCard
                key={item.key}
                label={item.label}
                value={item.key === "revenue" ? `${item.count} €` : item.rate === null ? String(item.count) : `${item.count} · ${formatRate(item.rate)}`}
                helper={item.helper}
                tone={item.tone}
              />
            ))}
          </div>

          <FiltersBar initialValues={filters} />

          <OverviewCharts trend={trend} funnel={funnel} />
        </section>

        <section id="funnel" className="mt-8 grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
          <ChartShell
            label="Причины"
            title="Где нужна ручная работа"
            description="Главные причины, по которым пользователям сейчас нужно внимание."
            action={<Sparkles className="size-4 text-accent" />}
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

          <ChartShell
            label="Срезы"
            title="Разрез по платящим клиентам"
            description="Группировка по текущему статусу и провайдеру оплаты."
          >
            <ScrollArea className="w-full">
              <div className="min-w-[720px]">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border/50">
                      {["Статус", "Оплата", "Платежей", "Плательщиков", "С записью", "С отзывом"].map((item) => (
                        <th key={item} className="px-3 py-3 text-left micro-label">
                          {item}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {conversions.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">
                          Нет срезов по текущим фильтрам.
                        </td>
                      </tr>
                    ) : (
                      conversions.slice(0, 10).map((row) => (
                        <tr key={`${row.status}-${row.paymentProvider}`} className="border-b border-border/40">
                          <td className="px-3 py-3">{row.status}</td>
                          <td className="px-3 py-3">{row.paymentProvider}</td>
                          <td className="px-3 py-3 font-medium text-foreground">{row.paymentsCount}</td>
                          <td className="px-3 py-3">{row.paidUsers}</td>
                          <td className="px-3 py-3">{row.rsvpUsers}</td>
                          <td className="px-3 py-3 text-primary">{row.feedbackUsers}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </ScrollArea>
          </ChartShell>
        </section>

        <section id="attention" className="mt-8 space-y-6">
          <ChartShell
            label="Клиенты"
            title="Кому нужно внимание"
            description="Список клиентов, где стоит вмешаться вручную."
          >
            <AttentionTable rows={stuckUsers} />
          </ChartShell>
        </section>

        <section id="signals" className="mt-8 grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
          <ChartShell
            label="Последние действия"
            title="Что произошло недавно"
            description="Последние реальные события по пользователям из базы."
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
            title="Как использовать дашборд"
            description="Три простых вопроса для ежедневной работы."
          >
            <div className="space-y-4 text-sm leading-7 text-muted-foreground">
              <p>
                <strong className="text-foreground">Сколько живых регистраций и оплат прошло за окно?</strong>
              </p>
              <p>
                <strong className="text-foreground">Кто завис перед оплатой или после неё?</strong>
              </p>
              <p>
                <strong className="text-foreground">Где уже есть встречи, но ещё нет отзывов?</strong>
              </p>
            </div>
          </ChartShell>
        </section>

        <section className="mt-8 space-y-6">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <KpiCard
              label="Платят сейчас"
              value={String(studentSummary.currentPaid)}
              helper="Сколько учеников сейчас с активной оплатой."
              tone="primary"
            />
            <KpiCard
              label="Больше не платят"
              value={String(studentSummary.formerPaid)}
              helper="Сколько учеников платили раньше, но сейчас оплата не активна."
              tone="accent"
            />
            <KpiCard
              label="Выручка"
              value={`${studentSummary.revenueTotal.toFixed(0)} €`}
              helper="Сумма успешных оплат по всем ученикам."
              tone="primary"
            />
            <KpiCard
              label="Действия в боте"
              value={String(studentSummary.avgActions30d)}
              helper="Среднее число зафиксированных действий за 30 дней."
              tone="neutral"
            />
            <KpiCard
              label="Без отзывов"
              value={String(studentSummary.noFeedbackCount)}
              helper={studentSummary.avgRating == null ? "Сколько платящих учеников ещё не оставляли отзывы." : `Средняя оценка: ${studentSummary.avgRating}`}
              tone="neutral"
            />
          </div>

          <ChartShell
            label="Ученики"
            title="Платящие и бывшие ученики"
            description="Здесь собрана вся известная информация по оплатам, активности, встречам и отзывам."
          >
            <StudentsTable rows={students} />
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
