import { NextRequest, NextResponse } from "next/server";

import { hasDatabaseUrl } from "@/lib/db";
import { buildDashboardFiltersFromUrlSearchParams } from "@/lib/filter-params";
import { getConversionData, getDashboardPageData } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const filters = buildDashboardFiltersFromUrlSearchParams(searchParams);
  const data = hasDatabaseUrl()
    ? await getConversionData(filters)
    : (await getDashboardPageData(filters)).conversions;
  return NextResponse.json({ data });
}
