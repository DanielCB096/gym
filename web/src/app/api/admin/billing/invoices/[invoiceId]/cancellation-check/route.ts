import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ invoiceId: string }> },
): Promise<NextResponse> {
  const { invoiceId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/billing/invoices/${encodeURIComponent(invoiceId)}/cancellation-check`,
    "POST",
    undefined,
  );
}
