import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet, proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function GET(request: NextRequest): Promise<NextResponse> {
  return proxyAuthenticatedGet(request, "/admin/access/settings");
}

export async function PATCH(request: NextRequest): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  return proxyAuthenticatedJson(request, "/admin/access/settings", "PATCH", body);
}
