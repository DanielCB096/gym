import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ subscriptionId: string }> },
): Promise<NextResponse> {
  const { subscriptionId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/staff/push/subscriptions/${encodeURIComponent(subscriptionId)}`,
    "DELETE",
    undefined,
  );
}
