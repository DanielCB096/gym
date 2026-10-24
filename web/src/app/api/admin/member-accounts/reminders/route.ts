import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const body = await request.json().catch(() => ({}));
  return proxyAuthenticatedJson(
    request,
    "/admin/member-accounts/reminders",
    "POST",
    body,
  );
}
