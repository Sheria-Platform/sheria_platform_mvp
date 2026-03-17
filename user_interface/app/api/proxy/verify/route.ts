import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_URL || "http://localhost:8000";

/** Server-side proxy for POST /api/v1/verify — forwards the httpOnly JWT. */
export async function POST(req: NextRequest) {
  const token = req.cookies.get("sheria_auth")?.value;
  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  try {
    const formData = await req.formData();
    const res = await fetch(`${API_URL}/api/v1/verify`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "API unavailable" }, { status: 503 });
  }
}
