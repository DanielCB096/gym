import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ reservationId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { reservationId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/classes/reservations/${encodeURIComponent(reservationId)}/attendance`,
    "POST",
    body,
  );
}
