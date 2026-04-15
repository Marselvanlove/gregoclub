import { NextRequest, NextResponse } from "next/server";

import { getDashboardPageData } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);

  const data = await getDashboardPageData(
    {
      from: searchParams.get("from"),
      to: searchParams.get("to"),
      source: searchParams.get("source"),
      state: searchParams.get("state"),
      status: searchParams.get("status"),
      tariff: searchParams.get("tariff"),
      provider: searchParams.get("provider"),
      onboardingVersion: searchParams.get("onboardingVersion"),
    },
    searchParams.get("focus"),
  );

  return NextResponse.json({ data });
}
