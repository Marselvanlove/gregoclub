import { ArrowRightCircle, Layers3, Sparkles, UsersRound } from "lucide-react";

import { AppShellNav } from "@/components/dashboard/app-shell";
import { AutoRefresh } from "@/components/dashboard/auto-refresh";
import { FiltersBar } from "@/components/dashboard/filters-bar";
import { OpsBoard, type OpsLane } from "@/components/dashboard/ops-board";
import { UserDetailSheet } from "@/components/dashboard/user-detail-sheet";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getOpsPageData, getStuckUsersData } from "@/lib/queries";

export const dynamic = "force-dynamic";

function readValue(params: Record<string, string | string[] | undefined>, key: string) {
  const value = params[key];
  return Array.isArray(value) ? value[0] : value;
}

function laneForBucket(bucket: string | null) {
  if (!bucket) return "reviewed";
  if (bucket.includes("без отзыва")) return "activation-risk";
  if (bucket.includes("не оплатили")) return "early-friction";
  if (bucket.includes("не записались") || bucket.includes("истекла")) return "decision-lag";
  return "reviewed";
}

function buildLanes(users: Awaited<ReturnType<typeof getStuckUsersData>>): OpsLane[] {
  const seed: OpsLane[] = [
    {
      id: "early-friction",
      title: "Не завершили оплату",
      description: "Есть интерес, но успешной оплаты пока нет.",
      cards: [],
    },
    {
      id: "decision-lag",
      title: "Нужен возврат",
      description: "Оплатили без записи или уже ушли в expired.",
      cards: [],
    },
    {
      id: "activation-risk",
      title: "Нет отзыва",
      description: "Были на встрече, но feedback не оставили.",
      cards: [],
    },
    {
      id: "reviewed",
      title: "Разобрано",
      description: "Карточки, которые уже посмотрели.",
      cards: [],
    },
  ];

  const laneMap = new Map(seed.map((lane) => [lane.id, lane]));
  users.forEach((user) => {
    laneMap.get(laneForBucket(user.stuckBucket))?.cards.push({
      telegramId: user.telegramId,
      fullName: user.fullName,
      username: user.username,
      stuckBucket: user.stuckBucket,
      lastEvent: user.lastEvent,
      lastEventAt: user.lastEventAt,
    });
  });

  return seed;
}

export default async function OpsPage({
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

  const { users, buckets, journey, payments, rsvps, feedbacks } = await getOpsPageData(filters, focusTelegramId);

  const lanes = buildLanes(users);

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
                Очередь внимания
              </h1>
              <p className="max-w-3xl text-base leading-7 text-muted-foreground">
                Здесь собраны реальные клиенты из продовой базы, которым нужно внимание команды.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-3 xl:grid-cols-1">
              {[
                { icon: UsersRound, label: "Клиенты", value: users.length },
                { icon: Layers3, label: "Причины", value: buckets.length },
                { icon: ArrowRightCircle, label: "Колонки", value: lanes.length },
              ].map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.label} className="rounded-[calc(var(--radius)-0.3rem)] border border-border/60 bg-white/60 p-4 shadow-[var(--shadow-soft)]">
                    <div className="micro-label">{item.label}</div>
                    <div className="mt-3 flex items-end justify-between">
                      <div className="text-3xl font-semibold tracking-[-0.05em] text-primary">{item.value}</div>
                      <Icon className="size-5 text-muted-foreground" />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <FiltersBar initialValues={filters} />

        <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
          <div className="space-y-6">
            <Card className="bg-white/60">
              <CardHeader>
                <div className="micro-label">Доска</div>
                <CardTitle>Работа с клиентами</CardTitle>
                <CardDescription>
                  Перетаскивайте карточки между колонками, чтобы быстро разобрать живую очередь.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <OpsBoard initialLanes={lanes} />
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card className="bg-white/62">
              <CardHeader>
                <div className="micro-label">Подсказка</div>
                <CardTitle>Как работать с очередью</CardTitle>
                <CardDescription>Коротко: что делать с каждой группой клиентов.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm leading-7 text-muted-foreground">
                <p>
                  <strong className="text-foreground">Не завершили оплату</strong>: помочь дойти до успешного платежа.
                </p>
                <p>
                  <strong className="text-foreground">Нужен возврат</strong>: вернуть к записи на встречу или продлению.
                </p>
                <p>
                  <strong className="text-foreground">Нет отзыва</strong>: добрать feedback после уже состоявшейся встречи.
                </p>
              </CardContent>
            </Card>

            <Card className="bg-white/62">
              <CardHeader>
                <div className="micro-label">Сводка</div>
                <CardTitle>Главные причины</CardTitle>
                <CardDescription>Где сейчас чаще всего нужна ручная работа.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {buckets.length === 0 ? (
                  <div className="rounded-[calc(var(--radius)-0.35rem)] border border-dashed border-border/60 bg-white/50 px-4 py-6 text-sm text-muted-foreground">
                    Сейчас нет активных проблемных групп.
                  </div>
                ) : (
                  buckets.slice(0, 6).map((bucket) => (
                    <div key={bucket.bucket} className="flex items-center justify-between rounded-[calc(var(--radius)-0.45rem)] border border-border/60 bg-white/55 px-4 py-3">
                      <div className="text-sm font-medium text-foreground">{bucket.bucket}</div>
                      <div className="text-xl font-semibold tracking-[-0.04em] text-accent">{bucket.users}</div>
                    </div>
                  ))
                )}
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Sparkles className="size-4 text-accent" />
                  Очередь можно быстро разобрать даже с телефона.
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
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
