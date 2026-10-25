import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ movementId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { movementId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/finance/bank-movements/${encodeURIComponent(movementId)}/unmatch`,
    "POST",
    body,
  );
}
