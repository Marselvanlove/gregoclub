import { createHash } from "crypto";

import type { NextRequest } from "next/server";
import { redirect } from "next/navigation";
import { cookies } from "next/headers";

const SESSION_COOKIE = "dashboard_session";

function getDashboardPassword(): string {
  const password = process.env.DASHBOARD_ADMIN_PASSWORD;
  if (!password) {
    throw new Error("DASHBOARD_ADMIN_PASSWORD is required for the dashboard");
  }
  return password;
}

function buildSessionToken(secret: string): string {
  return createHash("sha256").update(secret).digest("hex");
}

export function getExpectedDashboardSessionToken(): string {
  return buildSessionToken(getDashboardPassword());
}

export function isDashboardPasswordValid(password: string): boolean {
  return password === getDashboardPassword();
}

export function getSessionCookieName(): string {
  return SESSION_COOKIE;
}

export async function requireDashboardAuth(): Promise<void> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (token !== getExpectedDashboardSessionToken()) {
    redirect("/login");
  }
}

export function assertDashboardApiAccess(request: NextRequest): boolean {
  const cookieToken = request.cookies.get(SESSION_COOKIE)?.value;
  if (cookieToken === getExpectedDashboardSessionToken()) {
    return true;
  }

  const headerToken = request.headers.get("x-dashboard-token");
  if (!headerToken) {
    return false;
  }

  return (
    headerToken === getDashboardPassword() ||
    headerToken === getExpectedDashboardSessionToken()
  );
}
