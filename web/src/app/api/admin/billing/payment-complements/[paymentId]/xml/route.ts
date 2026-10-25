import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedDownload } from "@/lib/backend-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ paymentId: string }> },
): Promise<NextResponse> {
  const { paymentId } = await params;
  return proxyAuthenticatedDownload(
    request,
    `/admin/billing/payment-complements/${encodeURIComponent(paymentId)}/xml`,
  );
}
