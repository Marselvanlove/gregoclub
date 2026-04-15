"use client";

import { useMemo, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { PanelRightOpen } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

export function AttentionTable({ rows, limit = 16 }: { rows: AttentionUser[]; limit?: number }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const sortedRows = useMemo(() => rows.slice(0, limit), [limit, rows]);

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
      <div className="min-w-[760px]">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Клиент</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead>Где остановился</TableHead>
              <TableHead>Последнее действие</TableHead>
              <TableHead className="text-right">Открыть</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                  Сейчас нет клиентов по текущей выборке.
                </TableCell>
              </TableRow>
            ) : (
              sortedRows.map((row) => (
                <TableRow key={`${row.telegramId}-${row.stuckBucket}`}>
                  <TableCell>
                    <div className="space-y-1">
                      <div className="font-medium">{row.fullName ?? "Без имени"}</div>
                      <div className="text-xs text-muted-foreground">
                        {row.username ? `@${row.username}` : row.telegramId}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>{row.status ?? "—"}</TableCell>
                  <TableCell>
                    <Badge variant={bucketTone(row.stuckBucket)}>{row.stuckBucket ?? "—"}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="space-y-1">
                      <div>{row.lastEvent ?? "—"}</div>
                      <div className="text-xs text-muted-foreground">{row.lastEventAt ?? "—"}</div>
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="outline" size="sm" onClick={() => openSheet(row.telegramId)} disabled={isPending}>
                      <PanelRightOpen className="size-4" />
                      Карточка
                    </Button>
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
