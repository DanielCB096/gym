import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet } from "@/lib/backend-proxy";

export function GET(request: NextRequest): Promise<NextResponse> {
  const query = new URLSearchParams();
  const status = request.nextUrl.searchParams.get("status");
  const employeeId = request.nextUrl.searchParams.get("employee_id");
  if (status) query.set("status", status);
  if (employeeId) query.set("employee_id", employeeId);
  const suffix = query.toString();
  return proxyAuthenticatedGet(
    request,
    `/admin/staff/attendance/requests${suffix ? `?${suffix}` : ""}`,
  );
}