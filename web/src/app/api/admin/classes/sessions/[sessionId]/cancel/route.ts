import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> },
): Promise<NextResponse> {
  const { sessionId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/classes/sessions/${encodeURIComponent(sessionId)}/cancel`,
    "POST",
    undefined,
  );
}
