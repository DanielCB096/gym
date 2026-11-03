import { NextRequest, NextResponse } from "next/server";

import { GYM_API_URL, isSameOriginRequest } from "@/lib/backend-proxy";

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
    const backendResponse = await fetch(`${GYM_API_URL}/auth/mfa/setup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const payload = await backendResponse.json().catch(() => ({}));
    if (!backendResponse.ok) {
      return NextResponse.json({ detail: payload.detail || "No se pudo iniciar MFA" }, { status: backendResponse.status });
    }
    return NextResponse.json(payload);
  } catch {
    return NextResponse.json({ detail: "No se pudo conectar con el backend" }, { status: 502 });
  }
}
