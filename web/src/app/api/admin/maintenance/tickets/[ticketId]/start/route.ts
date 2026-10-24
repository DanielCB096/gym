import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ ticketId: string }> },
): Promise<NextResponse> {
  const { ticketId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/maintenance/tickets/${encodeURIComponent(ticketId)}/start`,
    "POST",
    undefined,
  );
}
