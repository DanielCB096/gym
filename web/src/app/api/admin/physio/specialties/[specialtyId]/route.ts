import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ specialtyId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { specialtyId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/physio/specialties/${encodeURIComponent(specialtyId)}`,
    "PATCH",
    body,
  );
}
