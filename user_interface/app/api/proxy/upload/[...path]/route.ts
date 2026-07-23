import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_URL || "http://localhost:8000";

/**
 * Catch-all server-side proxy for upload endpoints.
 * Reads the httpOnly `sheria_auth` cookie and forwards it as a Bearer token.
 *
 * Covers:
 *   POST /api/proxy/upload/generate-presigned-url → /api/v1/upload/generate-presigned-url
 *   POST /api/proxy/upload/ingest                 → /api/v1/upload/ingest
 *   GET  /api/proxy/upload/jobs                   → /api/v1/upload/jobs
 *   GET  /api/proxy/upload/jobs/:id               → /api/v1/upload/jobs/:id
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
  const upstream = `${API_URL}/api/v1/upload/${path.join("/")}${req.nextUrl.search}`;

  const headers: HeadersInit = { Authorization: `Bearer ${token}` };

  try {
    let body: string | undefined;
    if (req.method !== "GET" && req.method !== "HEAD") {
      body = await req.text();
      headers["Content-Type"] = "application/json";
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

export { handler as GET, handler as POST };
