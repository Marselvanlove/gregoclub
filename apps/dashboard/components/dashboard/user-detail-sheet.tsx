"use client";

import { useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { CalendarDays, CircleGauge, MessagesSquare, TrendingUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";

type JourneySummary = {
  full_name: string | null;
  username: string | null;
  status: string | null;
  onboarding_version: string | null;
  entry_source: string | null;
  last_event: string | null;
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

type JourneyEvent = {
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

type PaymentRecord = {
  id: string;
  date: string;
  amount: number;
  provider: string;
  status: string;
};

type RsvpRecord = {
  id: string;
  eventTitle: string;
  eventDate: string | null;
  response: string;
  createdAt: string;
};

type FeedbackRecord = {
  id: string;
  eventTitle: string;
  eventDate: string | null;
  rating: number | null;
  comment: string | null;
  level: string | null;
  nextVisit: string | null;
  createdAt: string;
};

export function UserDetailSheet({
  summary,
  timeline,
  payments,
  rsvps,
  feedbacks,
  open,
}: {
  summary: JourneySummary | null;
  timeline: JourneyEvent[];
  payments: PaymentRecord[];
  rsvps: RsvpRecord[];
  feedbacks: FeedbackRecord[];
  open: boolean;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const onOpenChange = (nextOpen: boolean) => {
    if (nextOpen) return;
    startTransition(() => {
      const params = new URLSearchParams(searchParams.toString());
      params.delete("focus");
      router.push(params.toString() ? `${pathname}?${params.toString()}` : pathname, { scroll: false });
      router.refresh();
    });
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="p-0">
        <SheetHeader>
          <div className="micro-label">Карточка клиента</div>
          <SheetTitle>{summary?.full_name ?? "Подробности"}</SheetTitle>
          <SheetDescription>
            Короткая история действий и текущий статус.
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-10rem)]">
          <div className="space-y-6 px-6 py-6">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-[calc(var(--radius)-0.4rem)] border border-border/60 bg-white/60 p-4">
                <div className="micro-label">Основное</div>
                <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                  <div>{summary?.username ? `@${summary.username}` : "Без username"}</div>
                  <div>Статус: {summary?.status ?? "—"}</div>
                  <div>Сценарий: {summary?.onboarding_version ?? "—"}</div>
                </div>
              </div>

              <div className="rounded-[calc(var(--radius)-0.4rem)] border border-border/60 bg-white/60 p-4">
                <div className="micro-label">Причина</div>
                <div className="mt-3">
                  <Badge variant="accent">{summary?.stuck_bucket ?? "Нет активной причины"}</Badge>
                </div>
                <div className="mt-3 text-sm text-muted-foreground">
                  Последнее действие: {summary?.last_event ?? "—"} · сегмент {summary?.state_choice ?? "—"}
                </div>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              {[
                { label: "Оплаты", value: summary?.payments_count ?? "0", icon: TrendingUp },
                { label: "Записи", value: summary?.rsvp_count ?? "0", icon: CalendarDays },
                { label: "Отзывы", value: summary?.feedback_count ?? "0", icon: MessagesSquare },
              ].map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.label} className="rounded-[calc(var(--radius)-0.45rem)] border border-border/60 bg-white/60 p-4">
                    <div className="micro-label">{item.label}</div>
                    <div className="mt-3 flex items-end justify-between">
                      <div className="text-3xl font-semibold tracking-[-0.04em] text-primary">{item.value}</div>
                      <Icon className="size-5 text-muted-foreground" />
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="rounded-[calc(var(--radius)-0.35rem)] border border-border/60 bg-white/60 p-5">
              <div className="flex items-center gap-2">
                <CircleGauge className="size-4 text-primary" />
                <div className="micro-label">Этапы</div>
              </div>
              <div className="mt-4 space-y-2 text-sm text-muted-foreground">
                <div>Первая оплата: {summary?.first_paid_at ?? "—"}</div>
                <div>Последняя оплата: {summary?.last_payment_at ?? "—"}</div>
                <div>Всего оплат: {summary?.payments_count ?? "0"} · {summary?.total_paid ?? "0"} €</div>
                <div>Первая запись: {summary?.first_rsvp_at ?? "—"}</div>
                <div>Первый отзыв: {summary?.first_feedback_at ?? "—"}</div>
                <div>Способ оплаты: {summary?.payment_provider ?? "—"}</div>
                <div>Действий в боте за 7 дней: {summary?.actions_7d ?? "0"}</div>
                <div>Действий в боте за 30 дней: {summary?.actions_30d ?? "0"}</div>
              </div>
            </div>

            <div className="space-y-3">
              <div className="micro-label">Оплаты</div>
              {payments.length === 0 ? (
                <div className="rounded-[calc(var(--radius)-0.35rem)] border border-dashed border-border/60 bg-white/55 px-4 py-6 text-sm text-muted-foreground">
                  По этому клиенту пока нет оплат.
                </div>
              ) : (
                payments.map((payment) => (
                  <div key={payment.id} className="rounded-[calc(var(--radius)-0.4rem)] border border-border/60 bg-white/60 p-4 shadow-[var(--shadow-soft)]">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="primary">{payment.status}</Badge>
                      <Badge variant="accent">{payment.provider}</Badge>
                      <span className="text-xs text-muted-foreground">{payment.date}</span>
                    </div>
                    <div className="mt-3 text-sm text-foreground">{payment.amount.toFixed(0)} €</div>
                  </div>
                ))
              )}
            </div>

            <div className="space-y-3">
              <div className="micro-label">Встречи</div>
              {rsvps.length === 0 ? (
                <div className="rounded-[calc(var(--radius)-0.35rem)] border border-dashed border-border/60 bg-white/55 px-4 py-6 text-sm text-muted-foreground">
                  По этому клиенту пока нет записей на встречи.
                </div>
              ) : (
                rsvps.map((item) => (
                  <div key={item.id} className="rounded-[calc(var(--radius)-0.4rem)] border border-border/60 bg-white/60 p-4 shadow-[var(--shadow-soft)]">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="primary">{item.response}</Badge>
                      <span className="text-xs text-muted-foreground">{item.eventDate ?? item.createdAt}</span>
                    </div>
                    <div className="mt-3 text-sm text-foreground">{item.eventTitle}</div>
                  </div>
                ))
              )}
            </div>

            <div className="space-y-3">
              <div className="micro-label">Отзывы</div>
              {feedbacks.length === 0 ? (
                <div className="rounded-[calc(var(--radius)-0.35rem)] border border-dashed border-border/60 bg-white/55 px-4 py-6 text-sm text-muted-foreground">
                  Отзывов пока нет.
                </div>
              ) : (
                feedbacks.map((item) => (
                  <div key={item.id} className="rounded-[calc(var(--radius)-0.4rem)] border border-border/60 bg-white/60 p-4 shadow-[var(--shadow-soft)]">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="primary">{item.rating == null ? "Без оценки" : `${item.rating}/5`}</Badge>
                      <span className="text-xs text-muted-foreground">{item.eventDate ?? item.createdAt}</span>
                    </div>
                    <div className="mt-3 text-sm text-foreground">{item.eventTitle}</div>
                    <div className="mt-2 text-sm text-muted-foreground">
                      Уровень: {item.level ?? "—"} · Следующая встреча: {item.nextVisit ?? "—"}
                    </div>
                    {item.comment ? <div className="mt-2 text-sm text-muted-foreground">{item.comment}</div> : null}
                  </div>
                ))
              )}
            </div>

            <div className="space-y-3">
              <div className="micro-label">История</div>
              {timeline.length === 0 ? (
                <div className="rounded-[calc(var(--radius)-0.35rem)] border border-dashed border-border/60 bg-white/55 px-4 py-6 text-sm text-muted-foreground">
                  Для этого пользователя пока нет событий в аналитическом логе.
                </div>
              ) : (
                timeline.map((event) => (
                  <div
                    key={event.id}
                    className="rounded-[calc(var(--radius)-0.4rem)] border border-border/60 bg-white/60 p-4 shadow-[var(--shadow-soft)]"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="primary">{event.eventName}</Badge>
                      {event.provider ? <Badge variant="accent">{event.provider}</Badge> : null}
                      <span className="text-xs text-muted-foreground">{event.createdAt}</span>
                    </div>
                    <div className="mt-3 text-sm text-muted-foreground">
                      {event.source ?? "—"}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
