import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ deliveryId: string }> },
): Promise<NextResponse> {
  const { deliveryId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/staff/notifications/deliveries/${encodeURIComponent(deliveryId)}/retry`,
    "POST",
    undefined,
  );
}
