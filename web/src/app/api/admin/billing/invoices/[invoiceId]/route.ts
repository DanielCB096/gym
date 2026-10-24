import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet } from "@/lib/backend-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ invoiceId: string }> },
): Promise<NextResponse> {
  const { invoiceId } = await params;
  return proxyAuthenticatedGet(
    request,
    `/admin/billing/invoices/${encodeURIComponent(invoiceId)}`,
  );
}
