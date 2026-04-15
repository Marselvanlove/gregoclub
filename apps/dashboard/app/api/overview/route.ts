import { NextRequest, NextResponse } from "next/server";

import { hasDatabaseUrl } from "@/lib/db";
import { buildDashboardFiltersFromUrlSearchParams } from "@/lib/filter-params";
import { getDashboardPageData, getOverviewData } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const filters = buildDashboardFiltersFromUrlSearchParams(searchParams);
  const data = hasDatabaseUrl()
    ? await getOverviewData(filters)
    : (await getDashboardPageData(filters)).overview;
  return NextResponse.json({ data });
}
