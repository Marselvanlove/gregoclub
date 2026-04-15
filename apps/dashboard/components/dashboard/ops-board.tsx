"use client";

import { useMemo, useState, useTransition } from "react";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  rectSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Clock3, GripVertical, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type OpsCard = {
  telegramId: string;
  fullName: string | null;
  username: string | null;
  stuckBucket: string | null;
  lastEvent: string | null;
  lastEventAt: string | null;
};

export type OpsLane = {
  id: string;
  title: string;
  description: string;
  cards: OpsCard[];
};

function SortableOpsCard({
  card,
  laneId,
  onInspect,
}: {
  card: OpsCard;
  laneId: string;
  onInspect: (telegramId: string) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: `${laneId}:${card.telegramId}`,
    data: {
      laneId,
      card,
    },
  });

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "rounded-[calc(var(--radius)-0.45rem)] border border-border/60 bg-white/85 p-4 shadow-[var(--shadow-soft)] transition-transform",
        isDragging && "rotate-[1deg] shadow-[var(--shadow-floating)]",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="font-medium text-foreground">{card.fullName ?? "Без имени"}</div>
          <div className="text-xs text-muted-foreground">{card.username ? `@${card.username}` : card.telegramId}</div>
        </div>
        <button
          className="rounded-full border border-border/60 bg-white/70 p-2 text-muted-foreground transition hover:text-foreground"
          {...attributes}
          {...listeners}
        >
          <GripVertical className="size-4" />
        </button>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Badge variant="accent">{card.stuckBucket ?? "Без причины"}</Badge>
      </div>

      <div className="mt-4 text-sm leading-6 text-muted-foreground">
        <div>{card.lastEvent ?? "—"}</div>
        <div className="mt-1 flex items-center gap-2 text-xs">
          <Clock3 className="size-3.5" />
          {card.lastEventAt ?? "—"}
        </div>
      </div>

      <div className="mt-4">
        <Button variant="outline" size="sm" onClick={() => onInspect(card.telegramId)}>
          Открыть
        </Button>
      </div>
    </div>
  );
}

function LaneDropZone({
  lane,
  children,
}: {
  lane: OpsLane;
  children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: lane.id,
    data: { laneId: lane.id },
  });

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "rounded-[calc(var(--radius)-0.1rem)] border border-border/60 bg-white/50 p-4 shadow-[var(--shadow-soft)] transition-colors",
        isOver && "bg-primary/6",
      )}
    >
      {children}
    </div>
  );
}

export function OpsBoard({
  initialLanes,
}: {
  initialLanes: OpsLane[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [lanes, setLanes] = useState(initialLanes);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  const laneMap = useMemo(
    () =>
      new Map(
        lanes.flatMap((lane) => lane.cards.map((card) => [`${lane.id}:${card.telegramId}`, { laneId: lane.id, card }])),
      ),
    [lanes],
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;

    const activeData = laneMap.get(String(active.id));
    if (!activeData) return;

    const overData = laneMap.get(String(over.id));
    const targetLaneId = overData?.laneId ?? (String(over.id).startsWith("early-friction") ||
      String(over.id).startsWith("decision-lag") ||
      String(over.id).startsWith("activation-risk") ||
      String(over.id).startsWith("reviewed")
        ? String(over.id)
        : null);

    if (!targetLaneId || activeData.laneId === targetLaneId) return;

    setLanes((previous) => {
      const next = previous.map((lane) => ({
        ...lane,
        cards: lane.cards.filter((card) => card.telegramId !== activeData.card.telegramId),
      }));

      const targetIndex = next.findIndex((lane) => lane.id === targetLaneId);
      next[targetIndex] = {
        ...next[targetIndex],
        cards: [activeData.card, ...next[targetIndex].cards],
      };
      return next;
    });

    toast.success("Карточка перемещена", {
      description: `${activeData.card.fullName ?? activeData.card.telegramId} перемещён.`,
    });
  };

  const onInspect = (telegramId: string) => {
    startTransition(() => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("focus", telegramId);
      router.push(`${pathname}?${params.toString()}`, { scroll: false });
      router.refresh();
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Sparkles className="size-4 text-accent" />
        Карточки можно быстро распределять по колонкам.
      </div>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <div className="grid gap-4 xl:grid-cols-4">
          {lanes.map((lane) => (
            <LaneDropZone key={lane.id} lane={lane}>
              <div className="mb-4 space-y-2">
                <div className="micro-label">{lane.title}</div>
                <p className="text-sm leading-6 text-muted-foreground">{lane.description}</p>
                <div className="text-2xl font-semibold tracking-[-0.04em] text-primary">{lane.cards.length}</div>
              </div>
              <SortableContext items={lane.cards.map((card) => `${lane.id}:${card.telegramId}`)} strategy={rectSortingStrategy}>
                <div className="space-y-3">
                  {lane.cards.length === 0 ? (
                    <div className="rounded-[calc(var(--radius)-0.45rem)] border border-dashed border-border/60 bg-white/55 px-4 py-6 text-sm text-muted-foreground">
                      Здесь пока пусто.
                    </div>
                  ) : (
                    lane.cards.map((card) => (
                      <SortableOpsCard key={`${lane.id}:${card.telegramId}`} card={card} laneId={lane.id} onInspect={onInspect} />
                    ))
                  )}
                </div>
              </SortableContext>
            </LaneDropZone>
          ))}
        </div>
        {isPending ? <div className="text-sm text-muted-foreground">Открываю карточку...</div> : null}
      </DndContext>
    </div>
  );
}
