import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ equipmentId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { equipmentId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/maintenance/equipment/${encodeURIComponent(equipmentId)}/status`,
    "POST",
    body,
  );
}
