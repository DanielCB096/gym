import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet } from "@/lib/backend-proxy";

export function GET(
  request: NextRequest,
  { params }: { params: Promise<{ packId: string }> },
): Promise<NextResponse> {
  return params.then(({ packId }) =>
    proxyAuthenticatedGet(
      request,
      `/admin/physio/packs/${encodeURIComponent(packId)}`,
    ),
  );
}
