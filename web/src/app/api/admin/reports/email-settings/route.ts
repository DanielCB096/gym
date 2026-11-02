import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet, proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function GET(request: NextRequest): Promise<NextResponse> {
  return proxyAuthenticatedGet(request, "/admin/reports/email-settings");
}

export async function PUT(request: NextRequest): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "La solicitud no contiene JSON válido." }, { status: 400 });
  }
  return proxyAuthenticatedJson(
    request,
    "/admin/reports/email-settings",
    "PUT",
    body,
  );
}
