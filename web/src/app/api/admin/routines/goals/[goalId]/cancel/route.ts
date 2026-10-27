import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ goalId: string }> },
): Promise<NextResponse> {
  const { goalId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/routines/goals/${encodeURIComponent(goalId)}/cancel`,
    "POST",
    undefined,
  );
}
