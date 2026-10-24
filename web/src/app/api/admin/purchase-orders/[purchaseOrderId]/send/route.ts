import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function POST(
  request: NextRequest,
  { params }: { params: Promise<{ purchaseOrderId: string }> },
): Promise<NextResponse> {
  return params.then(({ purchaseOrderId }) =>
    proxyAuthenticatedJson(
      request,
      `/admin/purchase-orders/${encodeURIComponent(purchaseOrderId)}/send`,
      "POST",
      undefined,
    ),
  );
}
