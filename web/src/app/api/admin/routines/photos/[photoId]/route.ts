import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ photoId: string }> },
): Promise<NextResponse> {
  return params.then(({ photoId }) =>
    proxyAuthenticatedJson(
      request,
      `/admin/routines/photos/${encodeURIComponent(photoId)}`,
      "DELETE",
      undefined,
    ),
  );
}
