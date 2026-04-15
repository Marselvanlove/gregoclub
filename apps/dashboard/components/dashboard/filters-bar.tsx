"use client";

import { useMemo, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { RefreshCcw } from "lucide-react";

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
  blockerReason?: string | null;
};

const PRESET_LABELS = {
  all: "Все клиенты",
  new: "Новый лид",
  new_no_activation: "Новый, но не включился",
  pending: "Думает об оплате",
  checkout_no_payment: "Открыл оплату, но не купил",
  paid_no_rsvp: "Оплатил, но не записался",
  feedback_missing: "После встречи без отзыва",
  active: "Активная подписка",
  expired: "Подписка истекла",
} as const;

const STATUS_PRESETS = {
  all: {
    label: PRESET_LABELS.all,
    patch: { status: "all", blockerReason: "" },
  },
  new: {
    label: PRESET_LABELS.new,
    patch: { status: "new", blockerReason: "" },
  },
  new_no_activation: {
    label: PRESET_LABELS.new_no_activation,
    patch: { status: "new", blockerReason: "new_no_activation" },
  },
  pending: {
    label: PRESET_LABELS.pending,
    patch: { status: "pending", blockerReason: "" },
  },
  checkout_no_payment: {
    label: PRESET_LABELS.checkout_no_payment,
    patch: { status: "all", blockerReason: "checkout_no_payment" },
  },
  paid_no_rsvp: {
    label: PRESET_LABELS.paid_no_rsvp,
    patch: { status: "all", blockerReason: "paid_no_rsvp" },
  },
  feedback_missing: {
    label: PRESET_LABELS.feedback_missing,
    patch: { status: "all", blockerReason: "feedback_prompt_ignored" },
  },
  active: {
    label: PRESET_LABELS.active,
    patch: { status: "active", blockerReason: "" },
  },
  expired: {
    label: PRESET_LABELS.expired,
    patch: { status: "expired", blockerReason: "" },
  },
} as const;

type StatusPresetKey = keyof typeof STATUS_PRESETS;

function resolveInitialStatusPreset(initialValues: FilterValues, initialStatusPreset?: string | null): StatusPresetKey {
  if (initialStatusPreset && initialStatusPreset in STATUS_PRESETS) {
    return initialStatusPreset as StatusPresetKey;
  }

  return (
    (Object.entries(STATUS_PRESETS).find(([, preset]) => {
      return (
        (initialValues.status ?? "all") === preset.patch.status &&
        (initialValues.blockerReason ?? "") === preset.patch.blockerReason
      );
    })?.[0] as StatusPresetKey | undefined) ?? "all"
  );
}

export function FiltersBar({
  initialValues,
  initialStatusPreset,
  presetKeys,
}: {
  initialValues: FilterValues;
  initialStatusPreset?: string | null;
  presetKeys?: StatusPresetKey[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const currentParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const allowedPresetKeys = presetKeys ?? (Object.keys(STATUS_PRESETS) as StatusPresetKey[]);
  const initialPreset = resolveInitialStatusPreset(initialValues, initialStatusPreset);
  const resolvedStatusPreset = allowedPresetKeys.includes(initialPreset)
    ? initialPreset
    : "all";
  const allowedPresetEntries = allowedPresetKeys.map((key) => [key, STATUS_PRESETS[key]] as const);
  const [statusPreset, setStatusPreset] = useState<StatusPresetKey>(resolvedStatusPreset);
  const [filters, setFilters] = useState({
    from: initialValues.from ?? "",
    to: initialValues.to ?? "",
    status: initialValues.status ?? "all",
    provider: initialValues.provider ?? "all",
    blockerReason: initialValues.blockerReason ?? "",
  });

  const queryString = useMemo(() => {
    const params = new URLSearchParams(currentParams.toString());
    [
      "focus",
      "source",
      "state",
      "tariff",
      "journeyStage",
      "journeyStep",
      "messageKey",
      "from",
      "to",
      "status",
      "provider",
      "blockerReason",
      "statusPreset",
    ].forEach((key) => params.delete(key));

    params.set("statusPreset", statusPreset);

    Object.entries(filters).forEach(([key, rawValue]) => {
      if (key === "status" || key === "blockerReason") return;
      const value = rawValue === "all" ? "" : rawValue;
      if (!value) return;
      params.set(key, value);
    });

    return params.toString();
  }, [currentParams, filters, statusPreset]);

  const applyStatusPreset = (value: string) => {
    const preset = STATUS_PRESETS[value as StatusPresetKey];
    if (!preset) return;

    setStatusPreset(value as StatusPresetKey);
    setFilters((prev) => ({
      ...prev,
      status: preset.patch.status,
      blockerReason: preset.patch.blockerReason,
    }));
  };

  const applyFilters = () => {
    startTransition(() => {
      router.push(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
      router.refresh();
    });
  };

  const resetFilters = () => {
    setStatusPreset("all");
    setFilters({
      from: "",
      to: "",
      status: "all",
      provider: "all",
      blockerReason: "",
    });
    startTransition(() => {
      router.push(pathname, { scroll: false });
      router.refresh();
    });
  };

  return (
    <div className="rounded-[calc(var(--radius)-0.2rem)] border border-border/60 bg-white/50 p-4 shadow-[var(--shadow-soft)]">
      <div className="mb-4">
        <div className="micro-label">Фильтры</div>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Только понятные фильтры для ежедневной работы: период, статус клиента и оплата.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
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
          <span className="micro-label">Где сейчас клиент</span>
          <Select value={statusPreset} onValueChange={applyStatusPreset}>
            <SelectTrigger>
              <SelectValue placeholder="Все" />
            </SelectTrigger>
            <SelectContent>
              {allowedPresetEntries.map(([value, preset]) => (
                <SelectItem key={value} value={value}>
                  {preset.label}
                </SelectItem>
              ))}
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
          {isPending ? "Обновляю…" : "Применить"}
        </Button>
        <Button variant="outline" onClick={resetFilters} disabled={isPending}>
          <RefreshCcw className="size-4" />
          Сбросить
        </Button>
      </div>
    </div>
  );
}
