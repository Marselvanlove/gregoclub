import { Badge } from "@/components/ui/badge";

type FeedbackHighlightRow = {
  id: string;
  fullName: string | null;
  username: string | null;
  eventTitle: string;
  eventDate: string | null;
  rating: number | null;
  comment: string | null;
  createdAt: string;
};

export function FeedbackHighlights({ rows }: { rows: FeedbackHighlightRow[] }) {
  return (
    <div className="space-y-3">
      {rows.length === 0 ? (
        <div className="rounded-[calc(var(--radius)-0.35rem)] border border-dashed border-border/60 bg-white/50 px-4 py-8 text-sm text-muted-foreground">
          По текущим фильтрам отзывов пока нет.
        </div>
      ) : (
        rows.map((row) => (
          <div key={row.id} className="rounded-[calc(var(--radius)-0.4rem)] border border-border/60 bg-white/58 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="primary">{row.rating == null ? "Без оценки" : `${row.rating}/5`}</Badge>
              <span className="text-xs text-muted-foreground">{row.eventDate ?? row.createdAt}</span>
            </div>
            <div className="mt-3 text-sm font-medium text-foreground">
              {row.fullName ?? "Без имени"} {row.username ? `· @${row.username}` : ""}
            </div>
            <div className="mt-1 text-sm text-muted-foreground">{row.eventTitle}</div>
            <div className="mt-2 text-sm text-muted-foreground">{row.comment?.trim() || "Комментарий не оставлен."}</div>
          </div>
        ))
      )}
    </div>
  );
}
