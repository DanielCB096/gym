import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet, proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ memberId: string }> },
): Promise<NextResponse> {
  const { memberId } = await params;
  return proxyAuthenticatedGet(
    request,
    `/admin/members/${encodeURIComponent(memberId)}/fiscal-profile`,
  );
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ memberId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { memberId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/members/${encodeURIComponent(memberId)}/fiscal-profile`,
    "PUT",
    body,
  );
}
