import { NextRequest, NextResponse } from "next/server";

import { hasDatabaseUrl } from "@/lib/db";
import { getDashboardPageData, getFunnelData } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const filters = {
    from: searchParams.get("from"),
    to: searchParams.get("to"),
    source: searchParams.get("source"),
    state: searchParams.get("state"),
    status: searchParams.get("status"),
    tariff: searchParams.get("tariff"),
    provider: searchParams.get("provider"),
    onboardingVersion: searchParams.get("onboardingVersion"),
  };
  const data = hasDatabaseUrl()
    ? await getFunnelData(filters)
    : (await getDashboardPageData(filters)).funnel;
  return NextResponse.json({ data });
}
