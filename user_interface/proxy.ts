import { NextRequest, NextResponse } from "next/server";

// Routes that require a specific role (or one of several roles).
// Matching is prefix-based: "/admin" matches "/admin/users", "/admin/settings", etc.
const ROUTE_ROLE_MAP: Record<string, string[]> = {
  "/admin":   ["admin"],
  "/predict": ["judge", "magistrate", "admin"],
};

export function proxy(req: NextRequest) {
  const cookie = req.cookies.get("sheria_auth");
  const role = req.cookies.get("sheria_role")?.value;
  const { pathname } = req.nextUrl;

  const isPublic =
    pathname.startsWith("/login") ||
    pathname.startsWith("/register") ||
    pathname.startsWith("/activate") ||
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon");

  if (!cookie && !isPublic) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  // Role-based route guard using the JS-readable sheria_role cookie.
  const requiredRoles = Object.entries(ROUTE_ROLE_MAP).find(([prefix]) =>
    pathname.startsWith(prefix)
  )?.[1];

  if (requiredRoles && (!role || !requiredRoles.includes(role))) {
    const url = req.nextUrl.clone();
    url.pathname = "/";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:jpg|jpeg|png|gif|svg|webp|ico)$).*)"],
};
