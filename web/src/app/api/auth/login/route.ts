import { NextRequest, NextResponse } from "next/server";

import { GYM_API_URL, isSameOriginRequest, SESSION_COOKIE } from "@/lib/backend-proxy";

type BackendLoginResponse = {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: {
    id: string;
    email: string;
    employee_id: string | null;
    roles: string[];
    permissions: string[];
  };
};

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
    const backendResponse = await fetch(`${GYM_API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const payload = await backendResponse.json().catch(() => ({}));
    if (!backendResponse.ok) {
      return NextResponse.json(
        { detail: backendResponse.status === 401 ? "Correo o contraseña incorrectos" : payload.detail || "No se pudo iniciar sesión" },
        { status: backendResponse.status },
      );
    }

    const login = payload as BackendLoginResponse;
    if (!login.access_token || !login.expires_at || !login.user) {
      return NextResponse.json({ detail: "Respuesta de sesión inválida" }, { status: 502 });
    }

    const expiresAt = new Date(login.expires_at);
    if (Number.isNaN(expiresAt.getTime()) || expiresAt <= new Date()) {
      return NextResponse.json({ detail: "La sesión recibida ya expiró" }, { status: 502 });
    }

    const response = NextResponse.json({ user: login.user });
    response.cookies.set(SESSION_COOKIE, login.access_token, {
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