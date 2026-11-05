import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedDownload } from "@/lib/backend-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ saleId: string }> },
): Promise<NextResponse> {
  const { saleId } = await params;
  return proxyAuthenticatedDownload(
    request,
    `/admin/sales/${encodeURIComponent(saleId)}/ticket.pdf`,
  );
}
