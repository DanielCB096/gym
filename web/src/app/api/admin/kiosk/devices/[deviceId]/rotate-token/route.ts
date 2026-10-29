import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function POST(
  request: NextRequest,
  { params }: { params: Promise<{ deviceId: string }> },
): Promise<NextResponse> {
  return params.then(({ deviceId }) =>
    proxyAuthenticatedJson(
      request,
      `/admin/kiosk/devices/${encodeURIComponent(deviceId)}/rotate-token`,
      "POST",
      undefined,
    ),
  );
}
