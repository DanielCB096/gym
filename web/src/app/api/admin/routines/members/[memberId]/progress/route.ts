import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet } from "@/lib/backend-proxy";

export function GET(
  request: NextRequest,
  { params }: { params: Promise<{ memberId: string }> },
): Promise<NextResponse> {
  return params.then(({ memberId }) =>
    proxyAuthenticatedGet(
      request,
      `/admin/routines/members/${encodeURIComponent(memberId)}/progress${request.nextUrl.search}`,
    ),
  );
}
