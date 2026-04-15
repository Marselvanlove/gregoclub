export type AnalyticsRolloutMode = "shadow" | "live";

export function normalizeAnalyticsRolloutMode(value?: string | null): AnalyticsRolloutMode {
  return value?.trim().toLowerCase() === "live" ? "live" : "shadow";
}

export function getAnalyticsRolloutMode(): AnalyticsRolloutMode {
  return normalizeAnalyticsRolloutMode(process.env.ANALYTICS_ROLLOUT_MODE ?? process.env.NEXT_PUBLIC_ANALYTICS_ROLLOUT_MODE);
}

export function analyticsConsumerFieldsEnabled(mode: AnalyticsRolloutMode = getAnalyticsRolloutMode()) {
  return mode === "live";
}

export function analyticsRolloutModeLabel(mode: AnalyticsRolloutMode) {
  return mode === "live" ? "Live" : "Shadow";
}
