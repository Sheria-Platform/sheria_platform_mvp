import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_URL || "http://localhost:8000";

/** Server-side proxy for GET /api/v1/verify/history — forwards the httpOnly JWT. */
export async function GET(req: NextRequest) {
  const token = req.cookies.get("sheria_auth")?.value;
  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  try {
    const res = await fetch(`${API_URL}/api/v1/verify/history`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const text = await res.text();
    let data: unknown;
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text || `HTTP ${res.status}` };
    }
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "API unavailable" }, { status: 503 });
  }
}
