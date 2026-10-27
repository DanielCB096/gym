import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedDownload } from "@/lib/backend-proxy";

export function GET(
  request: NextRequest,
  { params }: { params: Promise<{ photoId: string }> },
): Promise<NextResponse> {
  return params.then(({ photoId }) =>
    proxyAuthenticatedDownload(
      request,
      `/admin/routines/photos/${encodeURIComponent(photoId)}/file`,
    ),
  );
}
