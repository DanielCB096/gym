import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedDownload } from "@/lib/backend-proxy";

export function GET(request: NextRequest): Promise<NextResponse> {
  const query = new URLSearchParams();
  const days = request.nextUrl.searchParams.get("days");
  const employeeId = request.nextUrl.searchParams.get("employee_id");
  const actorId = request.nextUrl.searchParams.get("actor_id");
  if (days) query.set("days", days);
  if (employeeId) query.set("employee_id", employeeId);
  if (actorId) query.set("actor_id", actorId);
  const suffix = query.toString();
  return proxyAuthenticatedDownload(
    request,
    `/admin/staff/attendance/annulments.csv${suffix ? `?${suffix}` : ""}`,
  );
}
