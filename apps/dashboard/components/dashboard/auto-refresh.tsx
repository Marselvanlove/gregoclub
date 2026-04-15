"use client";

import { useEffect, useEffectEvent } from "react";
import { useRouter } from "next/navigation";
import { RefreshCcw } from "lucide-react";

import { cn } from "@/lib/utils";

export function AutoRefresh({
  intervalMs = 60_000,
  className,
}: {
  intervalMs?: number;
  className?: string;
}) {
  const router = useRouter();

  const refreshData = useEffectEvent(() => {
    if (document.visibilityState !== "visible") return;
    router.refresh();
  });

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      refreshData();
    }, intervalMs);

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        refreshData();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [intervalMs, refreshData]);

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-border/60 bg-white/70 px-3 py-2 text-sm text-muted-foreground shadow-[var(--shadow-soft)]",
        className,
      )}
    >
      <RefreshCcw className="size-4" />
      Автообновление каждые 60 сек
    </div>
  );
}
