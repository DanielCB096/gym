import { NextRequest, NextResponse } from "next/server";

import { proxyAuthenticatedJson } from "@/lib/backend-proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ workoutId: string }> },
): Promise<NextResponse> {
  const { workoutId } = await params;
  return proxyAuthenticatedJson(
    request,
    `/admin/routines/workouts/${encodeURIComponent(workoutId)}/review`,
    "POST",
    undefined,
  );
}
