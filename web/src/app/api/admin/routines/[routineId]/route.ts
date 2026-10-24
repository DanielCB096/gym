import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet, proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function GET(
  request: NextRequest,
  { params }: { params: Promise<{ routineId: string }> },
): Promise<NextResponse> {
  return params.then(({ routineId }) =>
    proxyAuthenticatedGet(
      request,
      `/admin/routines/${encodeURIComponent(routineId)}${request.nextUrl.search}`,
    ),
  );
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ routineId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { routineId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/routines/${encodeURIComponent(routineId)}`,
    "PATCH",
    body,
  );
}
