import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_URL || "http://localhost:8000";

/**
 * Catch-all server-side proxy for admin auth endpoints.
 *
 * Reads the httpOnly `sheria_auth` cookie (inaccessible to browser JS),
 * forwards it as a Bearer token to FastAPI's /api/v1/auth/* endpoints,
 * and streams the response back to the client.
 *
 * URL mapping:
 *   /api/proxy/admin/pending            → /api/v1/auth/pending
 *   /api/proxy/admin/users?status=...   → /api/v1/auth/users?status=...
 *   /api/proxy/admin/approve/:id        → /api/v1/auth/approve/:id
 *   /api/proxy/admin/users/:id/status   → /api/v1/auth/users/:id/status
 */
async function handler(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const token = req.cookies.get("sheria_auth")?.value;
  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { path } = await params;
  const upstream = `${API_URL}/api/v1/auth/${path.join("/")}${req.nextUrl.search}`;

  const headers: HeadersInit = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };

  try {
    let body: string | undefined;
    if (req.method !== "GET" && req.method !== "HEAD") {
      body = await req.text();
    }

    const res = await fetch(upstream, {
      method: req.method,
      headers,
      ...(body !== undefined ? { body } : {}),
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "API unavailable" }, { status: 503 });
  }
}

export { handler as GET, handler as POST, handler as PATCH, handler as DELETE };
