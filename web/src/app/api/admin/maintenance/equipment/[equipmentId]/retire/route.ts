import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ equipmentId: string }> },
): Promise<NextResponse> {
  const { equipmentId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/maintenance/equipment/${encodeURIComponent(equipmentId)}/retire`,
    "POST",
    undefined,
  );
}
