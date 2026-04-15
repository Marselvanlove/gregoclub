import { NextRequest, NextResponse } from "next/server";

import { getUserJourneyData } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ telegramId: string }> },
) {
  const { telegramId } = await context.params;
  const data = await getUserJourneyData(telegramId);
  return NextResponse.json(data);
}
