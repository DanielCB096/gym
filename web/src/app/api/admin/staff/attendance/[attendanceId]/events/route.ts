import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet } from "@/lib/backend-proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ attendanceId: string }> },
): Promise<NextResponse> {
  const { attendanceId } = await params;
  return proxyAuthenticatedGet(
    request,
    `/admin/staff/attendance/${encodeURIComponent(attendanceId)}/events`,
  );
}
