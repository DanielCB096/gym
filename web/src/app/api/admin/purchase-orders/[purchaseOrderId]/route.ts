import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet } from "@/lib/backend-proxy";

export function GET(
  request: NextRequest,
  { params }: { params: Promise<{ purchaseOrderId: string }> },
): Promise<NextResponse> {
  return params.then(({ purchaseOrderId }) =>
    proxyAuthenticatedGet(
      request,
      `/admin/purchase-orders/${encodeURIComponent(purchaseOrderId)}`,
    ),
  );
}
