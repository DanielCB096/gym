import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ requestId: string }> },
): Promise<NextResponse> {
  const { requestId } = await params;
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  return proxyAuthenticatedJson(
    request,
    `/admin/staff/attendance/requests/${encodeURIComponent(requestId)}/decision`,
    "POST",
    body,
  );
}