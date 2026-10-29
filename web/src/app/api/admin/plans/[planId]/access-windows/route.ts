import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ planId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { planId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/plans/${encodeURIComponent(planId)}/access-windows`,
    "PUT",
    body,
  );
}
