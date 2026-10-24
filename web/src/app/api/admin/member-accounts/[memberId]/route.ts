import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet } from "@/lib/backend-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ memberId: string }> },
): Promise<NextResponse> {
  const { memberId } = await params;
  return proxyAuthenticatedGet(
    request,
    `/admin/member-accounts/${encodeURIComponent(memberId)}`,
  );
}
