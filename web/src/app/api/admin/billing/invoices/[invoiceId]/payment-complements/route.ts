import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ invoiceId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { invoiceId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/billing/invoices/${encodeURIComponent(invoiceId)}/payment-complements`,
    "POST",
    body,
  );
}
