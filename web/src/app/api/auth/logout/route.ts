import { NextRequest, NextResponse } from "next/server";

import { clearSessionCookie, GYM_API_URL, isSameOriginRequest, SESSION_COOKIE } from "@/lib/backend-proxy";

export async function POST(request: NextRequest): Promise<NextResponse> {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({ detail: "Cross-origin request rejected" }, { status: 403 });
  }

  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (token) {
    try {
      await fetch(`${GYM_API_URL}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
    } catch {
      // Clear the browser session even if the backend is temporarily unavailable.
    }
  }

  const response = NextResponse.json({ logged_out: true });
  clearSessionCookie(response);
  return response;
}