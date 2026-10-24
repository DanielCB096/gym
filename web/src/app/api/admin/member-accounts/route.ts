import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet } from "@/lib/backend-proxy";

export function GET(request: NextRequest): Promise<NextResponse> {
  return proxyAuthenticatedGet(
    request,
    `/admin/member-accounts${request.nextUrl.search}`,
  );
}
