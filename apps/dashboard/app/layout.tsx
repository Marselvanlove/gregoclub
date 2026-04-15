import type { Metadata } from "next";
import { Toaster } from "sonner";

import "@/app/globals.css";

export const metadata: Metadata = {
  title: "Аналитика GregoClub",
  description: "Панель аналитики для команды GregoClub.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body>
        {children}
        <Toaster
          position="top-right"
          richColors
          toastOptions={{
            classNames: {
              toast: "!border !border-border/70 !bg-white/90 !text-foreground !shadow-[var(--shadow-floating)]",
              description: "!text-muted-foreground",
              actionButton: "!bg-primary !text-primary-foreground",
            },
          }}
        />
      </body>
    </html>
  );
}
