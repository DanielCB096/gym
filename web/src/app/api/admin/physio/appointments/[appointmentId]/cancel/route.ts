import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ appointmentId: string }> },
): Promise<NextResponse> {
  const { appointmentId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/physio/appointments/${encodeURIComponent(appointmentId)}/cancel`,
    "POST",
    {},
  );
}
