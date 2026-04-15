"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { LayoutGrid, PanelRightOpen, Radar, Rows4 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  {
    href: "/",
    label: "Обзор",
    description: "Основные цифры и узкие места",
    icon: LayoutGrid,
  },
  {
    href: "/ops",
    label: "Очередь",
    description: "Клиенты, которым нужно внимание",
    icon: Rows4,
  },
];

function buildHref(baseHref: string, searchParams: URLSearchParams) {
  const params = new URLSearchParams(searchParams.toString());
  params.delete("focus");
  const query = params.toString();
  return query ? `${baseHref}?${query}` : baseHref;
}

export function AppShellNav() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  return (
    <div className="sticky top-4 z-30 mb-8">
      <div className="glass-panel dashboard-shell flex items-center justify-between rounded-[calc(var(--radius)+0.15rem)] px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Radar className="size-5" />
          </div>
          <div>
            <div className="micro-label">Панель</div>
            <div className="text-sm font-medium text-foreground">Grego Club / club.hablacongrego.com</div>
          </div>
        </div>

        <div className="hidden items-center gap-2 md:flex">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={buildHref(item.href, searchParams)}
                className={cn(
                  "rounded-full px-4 py-2 text-sm font-medium transition-all duration-200",
                  active
                    ? "bg-white text-foreground shadow-[var(--shadow-soft)]"
                    : "text-muted-foreground hover:bg-white/60 hover:text-foreground",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </div>

        <Sheet>
          <SheetTrigger asChild className="md:hidden">
            <Button variant="subtle" size="icon" aria-label="Open navigation">
              <PanelRightOpen className="size-4" />
            </Button>
          </SheetTrigger>
          <SheetContent className="w-[min(90vw,24rem)]">
            <SheetHeader>
              <div className="micro-label">Меню</div>
              <SheetTitle>Разделы</SheetTitle>
            </SheetHeader>
            <div className="space-y-3 px-6 py-6">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                const active = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={buildHref(item.href, searchParams)}
                    className={cn(
                      "flex items-start gap-3 rounded-[calc(var(--radius)-0.35rem)] border border-border/60 px-4 py-3 transition-all",
                      active ? "bg-primary/8 text-foreground" : "bg-white/55 text-muted-foreground",
                    )}
                  >
                    <div className="mt-0.5 flex size-9 items-center justify-center rounded-full bg-white/70 text-primary">
                      <Icon className="size-4" />
                    </div>
                    <div className="space-y-1">
                      <div className="font-medium">{item.label}</div>
                      <p className="text-sm leading-5 text-muted-foreground">{item.description}</p>
                    </div>
                  </Link>
                );
              })}
            </div>
          </SheetContent>
        </Sheet>
      </div>
    </div>
  );
}
