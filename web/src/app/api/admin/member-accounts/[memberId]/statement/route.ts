import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedDownload } from "@/lib/backend-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ memberId: string }> },
): Promise<NextResponse> {
  const { memberId } = await params;
  const documentFormat = request.nextUrl.searchParams.get("format") === "csv" ? "csv" : "pdf";
  return proxyAuthenticatedDownload(
    request,
    `/admin/member-accounts/${encodeURIComponent(memberId)}/statement.${documentFormat}`,
  );
}
