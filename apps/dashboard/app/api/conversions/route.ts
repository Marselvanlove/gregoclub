import { NextRequest, NextResponse } from "next/server";

import { assertDashboardApiAccess } from "@/lib/auth";
import { getConversionData } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  if (!assertDashboardApiAccess(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const data = await getConversionData({
    from: searchParams.get("from"),
    to: searchParams.get("to"),
    source: searchParams.get("source"),
    state: searchParams.get("state"),
    tariff: searchParams.get("tariff"),
    provider: searchParams.get("provider"),
    onboardingVersion: searchParams.get("onboardingVersion"),
  });
  return NextResponse.json({ data });
}
