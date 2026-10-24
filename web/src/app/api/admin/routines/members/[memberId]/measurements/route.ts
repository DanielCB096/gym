import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet, proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function GET(
  request: NextRequest,
  { params }: { params: Promise<{ memberId: string }> },
): Promise<NextResponse> {
  return params.then(({ memberId }) =>
    proxyAuthenticatedGet(
      request,
      `/admin/routines/members/${encodeURIComponent(memberId)}/measurements${request.nextUrl.search}`,
    ),
  );
}

export async function POST(
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
    `/admin/routines/members/${encodeURIComponent(memberId)}/measurements`,
    "POST",
    body,
  );
}
