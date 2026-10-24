import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ memberId: string }> },
): Promise<NextResponse> {
  const { memberId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/members/${encodeURIComponent(memberId)}/membership/freeze`,
    "POST",
    undefined,
  );
}
