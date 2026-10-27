import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ notificationId: string }> },
): Promise<NextResponse> {
  const { notificationId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/notifications/${encodeURIComponent(notificationId)}/read`,
    "POST",
    undefined,
  );
}
