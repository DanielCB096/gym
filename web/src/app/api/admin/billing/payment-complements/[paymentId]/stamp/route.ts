import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ paymentId: string }> },
): Promise<NextResponse> {
  const { paymentId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/billing/payment-complements/${encodeURIComponent(paymentId)}/stamp`,
    "POST",
    {},
  );
}
