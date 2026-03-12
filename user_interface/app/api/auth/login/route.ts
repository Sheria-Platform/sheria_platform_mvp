import { NextRequest, NextResponse } from "next/server";
import { SignJWT } from "jose";
import { LoginRequest } from "@/types/api";

const SECRET = new TextEncoder().encode(
  process.env.JWT_SECRET || "sheria-dev-secret-change-in-prod"
);

export async function POST(req: NextRequest) {
  const body = (await req.json()) as LoginRequest;

  if (!body.username || !body.password) {
    return NextResponse.json({ error: "Missing credentials" }, { status: 400 });
  }

  // In production this should call the FastAPI auth endpoint.
  // For MVP, we create a signed JWT locally.
  const token = await new SignJWT({
    sub: body.username,
    role: body.role || "clerk",
    username: body.username,
  })
    .setProtectedHeader({ alg: "HS256" })
    .setExpirationTime("8h")
    .setIssuedAt()
    .sign(SECRET);

  const user = {
    id: body.username,
    username: body.username,
    role: body.role || "clerk",
    full_name: body.username,
    token,
  };

  const res = NextResponse.json({ user, token });
  res.cookies.set("sheria_auth", JSON.stringify(user), {
    httpOnly: false, // needs to be readable by js-cookie on client
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    maxAge: 60 * 60 * 8, // 8 hours
    path: "/",
  });

  return res;
}
