import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet } from "@/lib/backend-proxy";

export function GET(
  request: NextRequest,
  { params }: { params: Promise<{ movementId: string }> },
): Promise<NextResponse> {
  return params.then(({ movementId }) =>
    proxyAuthenticatedGet(
      request,
      `/admin/finance/bank-movements/${encodeURIComponent(movementId)}${request.nextUrl.search}`,
    ),
  );
}
