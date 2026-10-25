import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ paymentId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { paymentId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/billing/payment-complements/${encodeURIComponent(paymentId)}/cancel`,
    "POST",
    body,
  );
}
