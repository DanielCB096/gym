import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet, proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function GET(request: NextRequest): Promise<NextResponse> {
  return proxyAuthenticatedGet(request, `/admin/billing/invoices${request.nextUrl.search}`);
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  return proxyAuthenticatedJson(request, "/admin/billing/invoices", "POST", body);
}
