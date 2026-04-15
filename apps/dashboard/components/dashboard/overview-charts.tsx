"use client";

import { useMemo } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ChartShell } from "@/components/dashboard/chart-shell";
import { ScrollArea } from "@/components/ui/scroll-area";

type TrendPoint = {
  day: string;
  registrations: number;
  payments: number;
  rsvps: number;
  feedbacks: number;
};

type FunnelPoint = {
  step: string;
  total: number;
  recent: number;
};

export function OverviewCharts({
  trend,
  funnel,
}: {
  trend: TrendPoint[];
  funnel: FunnelPoint[];
}) {
  const trendData = useMemo(() => trend, [trend]);
  const funnelData = useMemo(() => funnel, [funnel]);

  return (
    <div className="grid gap-6 xl:grid-cols-[1.35fr_1fr]">
      <ChartShell
        label="Динамика"
        title="Что происходит по дням"
        description="Реальные регистрации и оплаты по дням."
      >
        <div className="h-[320px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={trendData} margin={{ top: 12, right: 12, left: -18, bottom: 8 }}>
              <defs>
                <linearGradient id="paymentsGradient" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="var(--chart-1)" stopOpacity={0.24} />
                  <stop offset="95%" stopColor="var(--chart-1)" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="registrationsGradient" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="var(--chart-2)" stopOpacity={0.24} />
                  <stop offset="95%" stopColor="var(--chart-2)" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(66,95,90,0.08)" vertical={false} />
              <XAxis dataKey="day" tickLine={false} axisLine={false} tickMargin={12} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
              <YAxis tickLine={false} axisLine={false} tickMargin={12} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  background: "rgba(255,251,246,0.96)",
                  border: "1px solid rgba(66,95,90,0.14)",
                  borderRadius: "18px",
                  boxShadow: "var(--shadow-floating)",
                }}
              />
              <Area type="monotone" dataKey="registrations" stroke="var(--chart-2)" fill="url(#registrationsGradient)" strokeWidth={2.2} />
              <Area type="monotone" dataKey="payments" stroke="var(--chart-1)" fill="url(#paymentsGradient)" strokeWidth={2.6} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </ChartShell>

      <ChartShell
        label="Путь клиента"
        title="Всего и за 30 дней"
        description="Сколько пользователей дошли до ключевых точек по живым данным."
      >
        <ScrollArea className="w-full">
          <div className="h-[320px] min-w-[540px] pr-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={funnelData} layout="vertical" margin={{ top: 8, right: 8, left: 24, bottom: 8 }}>
                <CartesianGrid stroke="rgba(66,95,90,0.08)" horizontal={false} />
                <XAxis type="number" tickLine={false} axisLine={false} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
                <YAxis
                  type="category"
                  dataKey="step"
                  tickLine={false}
                  axisLine={false}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                  width={128}
                />
                <Tooltip
                  contentStyle={{
                    background: "rgba(255,251,246,0.96)",
                    border: "1px solid rgba(66,95,90,0.14)",
                    borderRadius: "18px",
                    boxShadow: "var(--shadow-floating)",
                  }}
                />
                <Bar dataKey="total" fill="var(--chart-1)" radius={[10, 10, 10, 10]} />
                <Bar dataKey="recent" fill="var(--chart-2)" radius={[10, 10, 10, 10]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ScrollArea>
      </ChartShell>
    </div>
  );
}
