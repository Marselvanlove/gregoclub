"use client";

import { useMemo, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { PanelRightOpen } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type StudentRow = {
  telegramId: string;
  fullName: string | null;
  username: string | null;
  status: string;
  entrySource: string;
  paymentProvider: string;
  paymentsCount: number;
  totalPaid: number;
  lastPaymentAt: string | null;
  actions7d: number;
  actions30d: number;
  lastActionAt: string | null;
  attendingCount: number;
  feedbackCount: number;
  avgRating: number | null;
};

function statusTone(status: string) {
  if (status === "Оплатил") return "success" as const;
  if (status === "Истёк") return "warning" as const;
  return "neutral" as const;
}

export function StudentsTable({ rows, limit = 20 }: { rows: StudentRow[]; limit?: number }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const visibleRows = useMemo(() => rows.slice(0, limit), [limit, rows]);

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
      <div className="min-w-[1080px]">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Клиент</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead>Оплаты</TableHead>
              <TableHead>Встречи</TableHead>
              <TableHead>Активность 30 дней</TableHead>
              <TableHead>Отзывы</TableHead>
              <TableHead>Последняя активность</TableHead>
              <TableHead className="text-right">Карточка</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="py-10 text-center text-muted-foreground">
                  По текущим фильтрам нет активных или бывших платящих пользователей.
                </TableCell>
              </TableRow>
            ) : (
              visibleRows.map((row) => (
                <TableRow key={row.telegramId}>
                  <TableCell>
                    <div className="space-y-1">
                      <div className="font-medium">{row.fullName ?? "Без имени"}</div>
                      <div className="text-xs text-muted-foreground">{row.username ? `@${row.username}` : row.telegramId}</div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={statusTone(row.status)}>{row.status}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="space-y-1">
                      <div>{row.paymentsCount} · {row.totalPaid.toFixed(0)} €</div>
                      <div className="text-xs text-muted-foreground">{row.paymentProvider}</div>
                    </div>
                  </TableCell>
                  <TableCell>{row.attendingCount}</TableCell>
                  <TableCell>{row.actions30d}</TableCell>
                  <TableCell>
                    <div className="space-y-1">
                      <div>{row.feedbackCount}</div>
                      <div className="text-xs text-muted-foreground">{row.avgRating == null ? "—" : `Средняя: ${row.avgRating}`}</div>
                    </div>
                  </TableCell>
                  <TableCell>{row.lastActionAt ?? row.lastPaymentAt ?? "—"}</TableCell>
                  <TableCell className="text-right">
                    <Button variant="outline" size="sm" onClick={() => openSheet(row.telegramId)} disabled={isPending}>
                      <PanelRightOpen className="size-4" />
                      Открыть
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
