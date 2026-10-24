import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ memberId: string; deliveryId: string }> },
): Promise<NextResponse> {
  const { memberId, deliveryId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/member-accounts/${encodeURIComponent(memberId)}/statement/deliveries/${encodeURIComponent(deliveryId)}/retry`,
    "POST",
    {},
  );
}
