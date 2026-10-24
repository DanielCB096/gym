import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ userId: string; roleCode: string }> },
): Promise<NextResponse> {
  return params.then(({ userId, roleCode }) =>
    proxyAuthenticatedJson(
      request,
      `/admin/users/${encodeURIComponent(userId)}/roles/${encodeURIComponent(roleCode)}`,
      "DELETE",
      undefined,
    ),
  );
}
