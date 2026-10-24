import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ assignmentId: string }> },
): Promise<NextResponse> {
  const { assignmentId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/routines/assignments/${encodeURIComponent(assignmentId)}/complete`,
    "POST",
    undefined,
  );
}
