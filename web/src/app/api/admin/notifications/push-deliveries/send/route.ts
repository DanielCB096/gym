import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function POST(request: NextRequest): Promise<NextResponse> {
  return proxyAuthenticatedJson(request, "/admin/notifications/push-deliveries/send", "POST", undefined);
}
