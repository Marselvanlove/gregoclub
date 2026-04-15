import type { NextRequest } from "next/server";

export async function requireDashboardAuth(): Promise<void> {
  return;
}

export function assertDashboardApiAccess(_request: NextRequest): boolean {
  return true;
}
