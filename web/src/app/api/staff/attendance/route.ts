import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet } from "@/lib/backend-proxy";

export function GET(request: NextRequest): Promise<NextResponse> {
  const days = request.nextUrl.searchParams.get("days");
  return proxyAuthenticatedGet(request, `/staff/attendance${days ? `?days=${encodeURIComponent(days)}` : ""}`);
}
