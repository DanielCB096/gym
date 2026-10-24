import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet } from "@/lib/backend-proxy";

export function GET(
  request: NextRequest,
  { params }: { params: Promise<{ assignmentId: string }> },
): Promise<NextResponse> {
  return params.then(({ assignmentId }) =>
    proxyAuthenticatedGet(
      request,
      `/admin/routines/assignments/${encodeURIComponent(assignmentId)}${request.nextUrl.search}`,
    ),
  );
}
