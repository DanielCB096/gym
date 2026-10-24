import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { sessionId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/classes/sessions/${encodeURIComponent(sessionId)}`,
    "PATCH",
    body,
  );
}
