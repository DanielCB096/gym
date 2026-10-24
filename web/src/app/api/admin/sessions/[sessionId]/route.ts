import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> },
): Promise<NextResponse> {
  return params.then(({ sessionId }) =>
    proxyAuthenticatedJson(
      request,
      `/admin/sessions/${encodeURIComponent(sessionId)}`,
      "DELETE",
      undefined,
    ),
  );
}
