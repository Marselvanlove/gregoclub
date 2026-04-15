import { NextRequest, NextResponse } from "next/server";

import { hasDatabaseUrl } from "@/lib/db";
import { buildDashboardFiltersFromUrlSearchParams } from "@/lib/filter-params";
import { getDashboardPageData, getFunnelData } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const filters = buildDashboardFiltersFromUrlSearchParams(searchParams);
  const data = hasDatabaseUrl()
    ? await getFunnelData(filters)
    : (await getDashboardPageData(filters)).funnel;
  return NextResponse.json({ data });
}
