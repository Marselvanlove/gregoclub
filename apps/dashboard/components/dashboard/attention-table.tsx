"use client";

import { useMemo, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, MoreHorizontal, PanelRightOpen } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export type AttentionUser = {
  telegramId: string;
  fullName: string | null;
  username: string | null;
  status: string | null;
  paymentProvider: string | null;
  lastEvent: string | null;
  lastEventAt: string | null;
  stuckBucket: string | null;
};

function bucketTone(bucket: string | null) {
  if (!bucket) return "neutral" as const;
  if (bucket.includes("оплат")) return "accent" as const;
  if (bucket.includes("запис") || bucket.includes("отзыв")) return "warning" as const;
  return "primary" as const;
}

export function AttentionTable({ rows }: { rows: AttentionUser[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const sortedRows = useMemo(() => rows.slice(0, 16), [rows]);

  const openSheet = (telegramId: string) => {
    startTransition(() => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("focus", telegramId);
      router.push(`${pathname}?${params.toString()}`, { scroll: false });
      router.refresh();
    });
  };

  return (
    <ScrollArea className="w-full">
      <div className="min-w-[840px]">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Клиент</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead>Оплата</TableHead>
              <TableHead>Последнее действие</TableHead>
              <TableHead>Причина</TableHead>
              <TableHead className="text-right">Открыть</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="py-10 text-center text-muted-foreground">
                  Сейчас нет клиентов, которым нужно внимание.
                </TableCell>
              </TableRow>
            ) : (
              sortedRows.map((row) => (
                <TableRow key={`${row.telegramId}-${row.stuckBucket}`}>
                  <TableCell>
                    <div className="space-y-1">
                      <div className="font-medium">{row.fullName ?? "Без имени"}</div>
                      <div className="text-xs text-muted-foreground">
                        {row.username ? `@${row.username}` : row.telegramId} · {row.status ?? "—"}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>{row.status ?? "—"}</TableCell>
                  <TableCell>{row.paymentProvider ?? "—"}</TableCell>
                  <TableCell>
                    <div className="space-y-1">
                      <div>{row.lastEvent ?? "—"}</div>
                      <div className="text-xs text-muted-foreground">{row.lastEventAt ?? "—"}</div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={bucketTone(row.stuckBucket)}>{row.stuckBucket ?? "—"}</Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <Button variant="outline" size="sm" onClick={() => openSheet(row.telegramId)} disabled={isPending}>
                        <PanelRightOpen className="size-4" />
                        Карточка
                      </Button>
                      <Popover>
                        <PopoverTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <MoreHorizontal className="size-4" />
                          </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-56">
                          <div className="micro-label">Действия</div>
                          <div className="mt-3 space-y-2">
                            <button
                              className="flex w-full items-center justify-between rounded-2xl bg-muted/80 px-3 py-2 text-sm text-foreground transition hover:bg-muted"
                              onClick={() => openSheet(row.telegramId)}
                            >
                              Открыть детали
                              <ArrowRight className="size-4" />
                            </button>
                            <div className="rounded-2xl border border-border/60 px-3 py-2 text-sm text-muted-foreground">
                              Причина: {row.stuckBucket ?? "—"}
                            </div>
                          </div>
                        </PopoverContent>
                      </Popover>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </ScrollArea>
  );
}
