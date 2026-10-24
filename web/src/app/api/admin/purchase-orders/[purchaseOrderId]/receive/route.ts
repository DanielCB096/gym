import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ purchaseOrderId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { purchaseOrderId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/purchase-orders/${encodeURIComponent(purchaseOrderId)}/receive`,
    "POST",
    body,
  );
}
