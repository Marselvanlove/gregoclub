import { type ReactNode } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function ChartShell({
  label,
  title,
  description,
  action,
  children,
  className,
}: {
  label: string;
  title: string;
  description: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("bg-white/65", className)}>
      <CardHeader className="flex-row items-start justify-between gap-5">
        <div className="space-y-3">
          <div className="micro-label">{label}</div>
          <div className="space-y-1.5">
            <CardTitle>{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
        </div>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}
