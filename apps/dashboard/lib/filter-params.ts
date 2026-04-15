import type { DashboardFilters } from "@/lib/queries";

type SearchParamValue = string | string[] | undefined;
type SearchParamRecord = Record<string, SearchParamValue>;

export const STATUS_PRESET_FILTERS: Record<string, Pick<DashboardFilters, "status" | "blockerReason">> = {
  all: { status: null, blockerReason: null },
  new: { status: "new", blockerReason: null },
  new_no_activation: { status: "new", blockerReason: "new_no_activation" },
  pending: { status: "pending", blockerReason: null },
  checkout_no_payment: { status: null, blockerReason: "checkout_no_payment" },
  paid_no_rsvp: { status: null, blockerReason: "paid_no_rsvp" },
  feedback_missing: { status: null, blockerReason: "feedback_prompt_ignored" },
  active: { status: "active", blockerReason: null },
  expired: { status: "expired", blockerReason: null },
};

export function readSearchParamValue(params: SearchParamRecord, key: string) {
  const value = params[key];
  return Array.isArray(value) ? value[0] : value;
}

function pickAllowedStatusPreset(statusPreset: string | null | undefined, allowedStatusPresets?: string[]) {
  if (!statusPreset) return "all";
  if (allowedStatusPresets && !allowedStatusPresets.includes(statusPreset)) return "all";
  return statusPreset;
}

export function buildDashboardFiltersFromRecord(
  params: SearchParamRecord,
  options?: { allowedStatusPresets?: string[] },
): DashboardFilters {
  const statusPreset = pickAllowedStatusPreset(readSearchParamValue(params, "statusPreset"), options?.allowedStatusPresets);
  const statusFilters = STATUS_PRESET_FILTERS[statusPreset] ?? STATUS_PRESET_FILTERS.all;

  return {
    from: readSearchParamValue(params, "from") ?? null,
    to: readSearchParamValue(params, "to") ?? null,
    source: null,
    state: null,
    status: statusFilters.status,
    tariff: null,
    provider: readSearchParamValue(params, "provider") ?? null,
    onboardingVersion: null,
    journeyStage: null,
    journeyStep: null,
    blockerReason: statusFilters.blockerReason,
    messageKey: null,
  };
}

export function buildDashboardFiltersFromUrlSearchParams(
  searchParams: URLSearchParams,
  options?: { allowedStatusPresets?: string[] },
): DashboardFilters {
  const statusPreset = pickAllowedStatusPreset(searchParams.get("statusPreset"), options?.allowedStatusPresets);
  const statusFilters = STATUS_PRESET_FILTERS[statusPreset] ?? STATUS_PRESET_FILTERS.all;

  return {
    from: searchParams.get("from"),
    to: searchParams.get("to"),
    source: null,
    state: null,
    status: statusFilters.status,
    tariff: null,
    provider: searchParams.get("provider"),
    onboardingVersion: null,
    journeyStage: null,
    journeyStep: null,
    blockerReason: statusFilters.blockerReason,
    messageKey: null,
  };
}
