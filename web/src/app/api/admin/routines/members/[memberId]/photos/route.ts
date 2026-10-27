import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedFormData, proxyAuthenticatedGet } from "@/lib/backend-proxy";

export function GET(
  request: NextRequest,
  { params }: { params: Promise<{ memberId: string }> },
): Promise<NextResponse> {
  return params.then(({ memberId }) =>
    proxyAuthenticatedGet(
      request,
      `/admin/routines/members/${encodeURIComponent(memberId)}/photos`,
    ),
  );
}

export function POST(
  request: NextRequest,
  { params }: { params: Promise<{ memberId: string }> },
): Promise<NextResponse> {
  return params.then(({ memberId }) =>
    proxyAuthenticatedFormData(
      request,
      `/admin/routines/members/${encodeURIComponent(memberId)}/photos`,
    ),
  );
}
