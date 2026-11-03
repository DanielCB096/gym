import { NextRequest, NextResponse } from "next/server";

import { GYM_API_URL, isSameOriginRequest, SESSION_COOKIE } from "@/lib/backend-proxy";

export async function POST(request: NextRequest): Promise<NextResponse> {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({ detail: "Cross-origin request rejected" }, { status: 403 });
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  try {
    const backendResponse = await fetch(`${GYM_API_URL}/auth/mfa/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const payload = await backendResponse.json().catch(() => ({}));
    if (!backendResponse.ok) {
      return NextResponse.json({ detail: payload.detail || "Código MFA inválido" }, { status: backendResponse.status });
    }
    const expiresAt = new Date(payload.expires_at);
    if (!payload.access_token || !payload.user || Number.isNaN(expiresAt.getTime()) || expiresAt <= new Date()) {
      return NextResponse.json({ detail: "Respuesta de sesión inválida" }, { status: 502 });
    }
    const response = NextResponse.json({ user: payload.user });
    response.cookies.set(SESSION_COOKIE, payload.access_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "strict",
      path: "/",
      expires: expiresAt,
    });
    return response;
  } catch {
    return NextResponse.json({ detail: "No se pudo conectar con el backend" }, { status: 502 });
  }
}
