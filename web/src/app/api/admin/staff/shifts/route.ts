import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet } from "@/lib/backend-proxy";

export function GET(request: NextRequest): Promise<NextResponse> {
  const query = new URLSearchParams();
  const employeeId = request.nextUrl.searchParams.get("employee_id");
  const days = request.nextUrl.searchParams.get("days");
  if (employeeId) query.set("employee_id", employeeId);
  if (days) query.set("days", days);
  const suffix = query.toString();
  return proxyAuthenticatedGet(request, `/admin/staff/shifts${suffix ? `?${suffix}` : ""}`);
}
