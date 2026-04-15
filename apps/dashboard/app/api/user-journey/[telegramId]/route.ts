import { NextRequest, NextResponse } from "next/server";

import { hasDatabaseUrl } from "@/lib/db";
import { getDashboardPageData, getUserJourneyData } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ telegramId: string }> },
) {
  const { telegramId } = await context.params;
  const data = hasDatabaseUrl()
    ? await getUserJourneyData(telegramId)
    : (await getDashboardPageData({}, telegramId)).journey;
  return NextResponse.json(data);
}
