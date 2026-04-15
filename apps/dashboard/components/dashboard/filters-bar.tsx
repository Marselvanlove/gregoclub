"use client";

import { useMemo, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { RefreshCcw, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type FilterValues = {
  from?: string | null;
  to?: string | null;
  status?: string | null;
  provider?: string | null;
};

export function FiltersBar({ initialValues }: { initialValues: FilterValues }) {
  const router = useRouter();
  const pathname = usePathname();
  const currentParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [filters, setFilters] = useState({
    from: initialValues.from ?? "",
    to: initialValues.to ?? "",
    status: initialValues.status ?? "all",
    provider: initialValues.provider ?? "all",
  });

  const queryString = useMemo(() => {
    const params = new URLSearchParams(currentParams.toString());
    params.delete("focus");

    Object.entries(filters).forEach(([key, rawValue]) => {
      const value = rawValue === "all" ? "" : rawValue;
      if (!value) {
        params.delete(key);
      } else {
        params.set(key, value);
      }
    });

    return params.toString();
  }, [currentParams, filters]);

  const applyFilters = () => {
    startTransition(() => {
      router.push(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
      router.refresh();
    });
  };

  const resetFilters = () => {
    setFilters({
      from: "",
      to: "",
      status: "all",
      provider: "all",
    });
    startTransition(() => {
      router.push(pathname, { scroll: false });
      router.refresh();
    });
  };

  return (
    <div className="rounded-[calc(var(--radius)-0.2rem)] border border-border/60 bg-white/50 p-4 shadow-[var(--shadow-soft)]">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <div className="micro-label">Фильтры</div>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Можно отфильтровать данные по периоду, текущему статусу и способу оплаты.
          </p>
        </div>
        <div className="hidden rounded-full border border-accent/20 bg-accent/10 px-3 py-2 text-sm font-medium text-accent md:flex md:items-center md:gap-2">
          <Sparkles className="size-4" />
          Сводка по ключевым данным
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <label className="space-y-2">
          <span className="micro-label">С</span>
          <Input
            type="date"
            value={filters.from}
            onChange={(event) => setFilters((prev) => ({ ...prev, from: event.target.value }))}
          />
        </label>
        <label className="space-y-2">
          <span className="micro-label">По</span>
          <Input
            type="date"
            value={filters.to}
            onChange={(event) => setFilters((prev) => ({ ...prev, to: event.target.value }))}
          />
        </label>
        <label className="space-y-2">
          <span className="micro-label">Статус</span>
          <Select value={filters.status} onValueChange={(value) => setFilters((prev) => ({ ...prev, status: value }))}>
            <SelectTrigger>
              <SelectValue placeholder="Все" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Все</SelectItem>
              <SelectItem value="new">Новые</SelectItem>
              <SelectItem value="pending">Ожидают оплату</SelectItem>
              <SelectItem value="active">Активные</SelectItem>
              <SelectItem value="expired">Истёкшие</SelectItem>
            </SelectContent>
          </Select>
        </label>
        <label className="space-y-2">
          <span className="micro-label">Оплата</span>
          <Select value={filters.provider} onValueChange={(value) => setFilters((prev) => ({ ...prev, provider: value }))}>
            <SelectTrigger>
              <SelectValue placeholder="Все" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Все</SelectItem>
              <SelectItem value="stripe">Stripe</SelectItem>
              <SelectItem value="lavatop">LavaTop</SelectItem>
            </SelectContent>
          </Select>
        </label>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button onClick={applyFilters} disabled={isPending}>
          {isPending ? "Обновляю..." : "Применить"}
        </Button>
        <Button variant="outline" onClick={resetFilters} disabled={isPending}>
          <RefreshCcw className="size-4" />
          Сбросить
        </Button>
      </div>
    </div>
  );
}
