import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedDownload } from "@/lib/backend-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ invoiceId: string }> },
): Promise<NextResponse> {
  const { invoiceId } = await params;
  return proxyAuthenticatedDownload(
    request,
    `/admin/billing/invoices/${encodeURIComponent(invoiceId)}/pdf`,
  );
}
