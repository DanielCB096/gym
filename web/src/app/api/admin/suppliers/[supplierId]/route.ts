import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ supplierId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { supplierId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/suppliers/${encodeURIComponent(supplierId)}`,
    "PATCH",
    body,
  );
}
