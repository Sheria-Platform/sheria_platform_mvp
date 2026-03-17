import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_URL || "http://localhost:8000";

/**
 * Catch-all server-side proxy for history endpoints.
 * Reads the httpOnly `sheria_auth` cookie and forwards it as a Bearer token.
 *
 * Covers:
 *   GET /api/proxy/history/sessions       → /api/v1/history/sessions
 *   GET /api/proxy/history/sessions/:id   → /api/v1/history/sessions/:id
 */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const token = req.cookies.get("sheria_auth")?.value;
  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { path } = await params;
  const upstream = `${API_URL}/api/v1/history/${path.join("/")}${req.nextUrl.search}`;

  try {
    const res = await fetch(upstream, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "API unavailable" }, { status: 503 });
  }
}
