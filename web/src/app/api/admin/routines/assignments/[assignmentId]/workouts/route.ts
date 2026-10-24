import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet, proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function GET(
  request: NextRequest,
  { params }: { params: Promise<{ assignmentId: string }> },
): Promise<NextResponse> {
  return params.then(({ assignmentId }) =>
    proxyAuthenticatedGet(
      request,
      `/admin/routines/assignments/${encodeURIComponent(assignmentId)}/workouts${request.nextUrl.search}`,
    ),
  );
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ assignmentId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { assignmentId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/routines/assignments/${encodeURIComponent(assignmentId)}/workouts`,
    "POST",
    body,
  );
}
