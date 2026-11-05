import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ saleId: string }> },
): Promise<NextResponse> {
  const { saleId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/sales/${encodeURIComponent(saleId)}/ticket/email${request.nextUrl.search}`,
    "POST",
    undefined,
  );
}
