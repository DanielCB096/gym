import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function POST(request: NextRequest): Promise<NextResponse> {
  return proxyAuthenticatedJson(request, "/admin/staff/notifications/deliveries/send", "POST", undefined);
}
