import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ saleId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { saleId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/sales/${encodeURIComponent(saleId)}/returns`,
    "POST",
    body,
  );
}
