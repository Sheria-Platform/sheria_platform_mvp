import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_URL || "http://localhost:8000";

/**
 * Server-side streaming proxy for POST /api/v1/chat/stream.
 *
 * Reads the httpOnly sheria_auth cookie and forwards it as a Bearer token to
 * FastAPI, then pipes the NDJSON response stream back to the browser.
 */
export async function POST(req: NextRequest) {
  const token = req.cookies.get("sheria_auth")?.value;
  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  try {
    const body = await req.text();
    const res = await fetch(`${API_URL}/api/v1/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body,
    });

    if (!res.ok || !res.body) {
      return NextResponse.json(
        { error: `Upstream error: HTTP ${res.status}` },
        { status: res.status }
      );
    }

    // Pipe the NDJSON stream directly — do not buffer.
    return new NextResponse(res.body, {
      status: res.status,
      headers: {
        "Content-Type": "application/x-ndjson",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
      },
    });
  } catch {
    return NextResponse.json({ error: "API unavailable" }, { status: 503 });
  }
}
