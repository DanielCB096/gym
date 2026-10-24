import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ reservationId: string }> },
): Promise<NextResponse> {
  const { reservationId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/classes/reservations/${encodeURIComponent(reservationId)}/cancel`,
    "POST",
    undefined,
  );
}
