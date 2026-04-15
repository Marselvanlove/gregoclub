import { NextRequest, NextResponse } from "next/server";

import { buildDashboardFiltersFromUrlSearchParams } from "@/lib/filter-params";
import { getDashboardPageData } from "@/lib/queries";

export const dynamic = "force-dynamic";

const OVERVIEW_PRESET_KEYS = ["all", "new", "new_no_activation", "pending", "checkout_no_payment", "paid_no_rsvp", "feedback_missing", "active", "expired"];

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const data = await getDashboardPageData(
    buildDashboardFiltersFromUrlSearchParams(searchParams, { allowedStatusPresets: OVERVIEW_PRESET_KEYS }),
    searchParams.get("focus"),
  );

  return NextResponse.json({ data });
}
