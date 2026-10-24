import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ ticketId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    body = {};
  }
  const { ticketId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/maintenance/tickets/${encodeURIComponent(ticketId)}/cancel`,
    "POST",
    body,
  );
}
