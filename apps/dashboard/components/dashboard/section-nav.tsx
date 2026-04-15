"use client";

import { Menu } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const SECTION_ITEMS = [
  { value: "pulse", label: "Сводка", href: "#pulse" },
  { value: "funnel", label: "Воронка", href: "#funnel" },
  { value: "attention", label: "Риски", href: "#attention" },
  { value: "signals", label: "Действия", href: "#signals" },
];

export function SectionNav() {
  return (
    <div className="sticky top-24 z-20 mb-8">
      <div className="glass-panel rounded-[calc(var(--radius)-0.1rem)] px-3 py-3">
        <div className="hidden md:block">
          <Tabs defaultValue="pulse">
            <TabsList className="w-full justify-start bg-transparent p-0 shadow-none">
              {SECTION_ITEMS.map((item) => (
                <a key={item.value} href={item.href}>
                  <TabsTrigger value={item.value}>{item.label}</TabsTrigger>
                </a>
              ))}
            </TabsList>
          </Tabs>
        </div>

        <div className="flex items-center justify-between md:hidden">
          <div>
            <div className="micro-label">Разделы</div>
            <p className="mt-2 text-sm text-muted-foreground">Сводка, воронка, риски и действия</p>
          </div>
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="subtle" size="icon">
                <Menu className="size-4" />
              </Button>
            </SheetTrigger>
            <SheetContent className="w-[min(86vw,22rem)]">
              <SheetHeader>
                <div className="micro-label">Переход</div>
                <SheetTitle>Разделы</SheetTitle>
              </SheetHeader>
              <div className="space-y-3 px-6 py-6">
                {SECTION_ITEMS.map((item) => (
                  <a
                    key={item.value}
                    href={item.href}
                    className="block rounded-[calc(var(--radius)-0.4rem)] border border-border/60 bg-white/55 px-4 py-3 text-sm font-medium text-foreground"
                  >
                    {item.label}
                  </a>
                ))}
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </div>
  );
}
