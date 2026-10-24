import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet, proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function GET(
  request: NextRequest,
  { params }: { params: Promise<{ equipmentId: string }> },
): Promise<NextResponse> {
  return params.then(({ equipmentId }) =>
    proxyAuthenticatedGet(
      request,
      `/admin/maintenance/equipment/${encodeURIComponent(equipmentId)}/records${request.nextUrl.search}`,
    ),
  );
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ equipmentId: string }> },
): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }
  const { equipmentId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/maintenance/equipment/${encodeURIComponent(equipmentId)}/records`,
    "POST",
    body,
  );
}
