import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet, proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function GET(
  request: NextRequest,
  { params }: { params: Promise<{ ticketId: string }> },
): Promise<NextResponse> {
  return params.then(({ ticketId }) =>
    proxyAuthenticatedGet(
      request,
      `/admin/maintenance/tickets/${encodeURIComponent(ticketId)}${request.nextUrl.search}`,
    ),
  );
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ ticketId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { ticketId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/maintenance/tickets/${encodeURIComponent(ticketId)}`,
    "PATCH",
    body,
  );
}
