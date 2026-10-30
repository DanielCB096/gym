import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedDownload } from "@/lib/backend-proxy";

export function GET(request: NextRequest): Promise<NextResponse> {
  return proxyAuthenticatedDownload(
    request,
    `/admin/physio/report/export${request.nextUrl.search}`,
  );
}
