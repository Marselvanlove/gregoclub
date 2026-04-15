import type { Metadata } from "next";

import "@/app/globals.css";

export const metadata: Metadata = {
  title: "Grego Club Dashboard",
  description: "Admin dashboard for onboarding, CRM and analytics.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
