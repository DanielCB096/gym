import { NextRequest, NextResponse } from "next/server";

import { proxyMemberPaymentMethodSetup } from "@/lib/member-payment-method-proxy";

export function POST(request: NextRequest): Promise<NextResponse> {
  return proxyMemberPaymentMethodSetup(request, "complete");
}
