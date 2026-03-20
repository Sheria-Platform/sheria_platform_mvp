import Cookies from "js-cookie";
import { AuthUser } from "@/types/chat";

const COOKIE_NAME = "sheria_auth";
const ROLE_COOKIE_NAME = "sheria_role";
const COOKIE_TTL_DAYS = 1 / 3; // 8 hours

export function setAuthUser(user: AuthUser): void {
  // Store only the non-sensitive user profile (no token) as a JS-readable cookie.
  // The JWT lives in the httpOnly sheria_auth cookie set server-side at login.
  Cookies.set(COOKIE_NAME + "_profile", JSON.stringify(user), {
    expires: COOKIE_TTL_DAYS,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
  });
}

export function getAuthUser(): AuthUser | null {
  const raw = Cookies.get(COOKIE_NAME + "_profile");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function clearAuth(): void {
  Cookies.remove(COOKIE_NAME + "_profile");
  Cookies.remove(ROLE_COOKIE_NAME);
}
