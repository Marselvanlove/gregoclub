import { NextRequest, NextResponse } from "next/server";

import { assertDashboardApiAccess } from "@/lib/auth";
import { getUserJourneyData } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ telegramId: string }> },
) {
  if (!assertDashboardApiAccess(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { telegramId } = await context.params;
  const data = await getUserJourneyData(telegramId);
  return NextResponse.json(data);
}
