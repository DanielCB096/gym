import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ routineId: string }> },
): Promise<NextResponse> {
  const { routineId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/routines/${encodeURIComponent(routineId)}/archive`,
    "POST",
    undefined,
  );
}
