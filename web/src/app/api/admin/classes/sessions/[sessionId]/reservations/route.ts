import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet, proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> },
): Promise<NextResponse> {
  const { sessionId } = await params;
  return proxyAuthenticatedGet(
    request,
    `/admin/classes/sessions/${encodeURIComponent(sessionId)}/reservations`,
  );
}

export async function POST(
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
    `/admin/classes/sessions/${encodeURIComponent(sessionId)}/reservations`,
    "POST",
    body,
  );
}
