import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ bankAccountId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { bankAccountId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/finance/bank-accounts/${encodeURIComponent(bankAccountId)}`,
    "PATCH",
    body,
  );
}
