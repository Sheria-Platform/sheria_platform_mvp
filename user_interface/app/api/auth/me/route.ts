import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_URL || "http://localhost:8000";

/**
 * Server-side profile relay.
 *
 * Reads the httpOnly `sheria_auth` cookie (inaccessible to browser JS),
 * forwards it as a Bearer token to FastAPI's /auth/me endpoint, and
 * returns the user profile to the client — without ever exposing the
 * raw JWT to JavaScript.
 */
export async function GET(req: NextRequest) {
  const token = req.cookies.get("sheria_auth")?.value;
  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  try {
    const res = await fetch(`${API_URL}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "API unavailable" }, { status: 503 });
  }
}
