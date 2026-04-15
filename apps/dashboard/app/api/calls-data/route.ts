import { NextRequest, NextResponse } from "next/server";

import { buildDashboardFiltersFromUrlSearchParams } from "@/lib/filter-params";
import { getCallsPageData } from "@/lib/queries";

export const dynamic = "force-dynamic";

const CALLS_PRESET_KEYS = ["all", "active", "expired", "paid_no_rsvp", "feedback_missing"];

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const data = await getCallsPageData(
    buildDashboardFiltersFromUrlSearchParams(searchParams, { allowedStatusPresets: CALLS_PRESET_KEYS }),
    searchParams.get("focus"),
  );

  return NextResponse.json({ data });
}
