import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_URL || "http://localhost:8000";

export async function POST(req: NextRequest) {
  const body = await req.json();

  if (!body.username || !body.password) {
    return NextResponse.json({ error: "Missing credentials" }, { status: 400 });
  }

  let apiRes: Response;
  try {
    apiRes = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: body.username, password: body.password }),
    });
  } catch {
    return NextResponse.json({ error: "API unavailable" }, { status: 503 });
  }

  if (!apiRes.ok) {
    const detail = await apiRes.json().catch(() => ({ detail: "Invalid credentials" }));
    return NextResponse.json(
      { error: detail.detail || "Invalid credentials" },
      { status: apiRes.status }
    );
  }

  const data = await apiRes.json();
  const res = NextResponse.json({ user: data.user, token: data.access_token });
  res.cookies.set("sheria_auth", JSON.stringify(data.user), {
    httpOnly: false,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    maxAge: 60 * 60 * 8,
    path: "/",
  });
  return res;
}
