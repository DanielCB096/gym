import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedGet } from "@/lib/backend-proxy";

export function GET(request: NextRequest): Promise<NextResponse> {
  const query = new URLSearchParams();
  const status = request.nextUrl.searchParams.get("status");
  const page = request.nextUrl.searchParams.get("page");
  const pageSize = request.nextUrl.searchParams.get("page_size");
  if (status) query.set("status", status);
  if (page) query.set("page", page);
  if (pageSize) query.set("page_size", pageSize);
  const suffix = query.toString();
  return proxyAuthenticatedGet(
    request,
    `/admin/staff/notifications/deliveries${suffix ? `?${suffix}` : ""}`,
  );
}
