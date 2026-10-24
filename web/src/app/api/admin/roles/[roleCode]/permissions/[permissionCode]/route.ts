import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ roleCode: string; permissionCode: string }> },
): Promise<NextResponse> {
  const { roleCode, permissionCode } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/roles/${encodeURIComponent(roleCode)}/permissions/${encodeURIComponent(permissionCode)}`,
    "DELETE",
    undefined,
  );
}
