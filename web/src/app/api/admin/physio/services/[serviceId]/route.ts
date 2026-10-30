import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ serviceId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { serviceId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/physio/services/${encodeURIComponent(serviceId)}`,
    "PATCH",
    body,
  );
}
