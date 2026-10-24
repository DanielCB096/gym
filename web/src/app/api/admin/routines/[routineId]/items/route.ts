import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function PUT(
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
    `/admin/routines/${encodeURIComponent(routineId)}/items`,
    "PUT",
    body,
  );
}
