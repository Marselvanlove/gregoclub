import { Card, CardContent, CardHeader } from "@/components/ui/card";

export function KpiCard({
  label,
  value,
  helper,
  tone = "primary",
}: {
  label: string;
  value: string;
  helper: string;
  tone?: "primary" | "accent" | "neutral";
}) {
  const toneClass =
    tone === "primary"
      ? "text-primary"
      : tone === "accent"
        ? "text-accent"
        : "text-foreground";

  return (
    <Card className="h-full bg-white/62">
      <CardHeader className="gap-4 pb-3">
        <div className="micro-label">{label}</div>
      </CardHeader>
      <CardContent>
        <div className={`text-4xl font-semibold tracking-[-0.05em] ${toneClass}`}>{value}</div>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">{helper}</p>
      </CardContent>
    </Card>
  );
}
