import { NextRequest, NextResponse } from "next/server";

import { hasDatabaseUrl } from "@/lib/db";
import { getDashboardPageData, getOverviewData } from "@/lib/queries";

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
    ? await getOverviewData(filters)
    : (await getDashboardPageData(filters)).overview;
  return NextResponse.json({ data });
}
