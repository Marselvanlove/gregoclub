"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  getExpectedDashboardSessionToken,
  getSessionCookieName,
  isDashboardPasswordValid,
} from "@/lib/auth";

export async function loginAction(formData: FormData) {
  const password = String(formData.get("password") ?? "");
  if (!isDashboardPasswordValid(password)) {
    redirect("/login?error=invalid");
  }

  const cookieStore = await cookies();
  cookieStore.set({
    name: getSessionCookieName(),
    value: getExpectedDashboardSessionToken(),
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
  });

  redirect("/");
}

export async function logoutAction() {
  const cookieStore = await cookies();
  cookieStore.delete(getSessionCookieName());
  redirect("/login");
}
