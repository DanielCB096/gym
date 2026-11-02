import { NextRequest, NextResponse } from "next/server";

import { GYM_API_URL, isSameOriginRequest } from "@/lib/backend-proxy";

export async function proxyMemberPaymentMethodSetup(
  request: NextRequest,
  operation: "config" | "complete",
): Promise<NextResponse> {
  if (!isSameOriginRequest(request)) {
    return response({ detail: "Cross-origin request rejected" }, 403);
  }
  const declaredLength = Number(request.headers.get("content-length") ?? "");
  if (Number.isFinite(declaredLength) && declaredLength > 1024) {
    return response({ detail: "Invalid request body" }, 413);
  }

  let requestBody: string;
  try {
    requestBody = await request.text();
  } catch {
    return response({ detail: "Invalid request body" }, 400);
  }
  if (requestBody.length > 1024) {
    return response({ detail: "Invalid request body" }, 413);
  }
  let body: unknown;
  try {
    body = JSON.parse(requestBody) as unknown;
  } catch {
    return response({ detail: "Invalid request body" }, 400);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return response({ detail: "Invalid request body" }, 400);
  }
  const record = body as Record<string, unknown>;
  const keys = Object.keys(record).sort().join(",");
  const validSetupToken =
    typeof record.setup_token === "string" &&
    /^[A-Za-z0-9_-]{40,60}$/.test(record.setup_token);
  const validKeys = operation === "config"
    ? keys === "setup_token"
    : keys === "card_token,setup_token";
  if (
    !validKeys ||
    !validSetupToken ||
    (operation === "complete" &&
      (typeof record.card_token !== "string" ||
        !/^tok_[A-Za-z0-9_-]{1,250}$/.test(record.card_token)))
  ) {
    return response({ detail: "Invalid request body" }, 422);
  }

  try {
    const backendResponse = await fetch(
      `${GYM_API_URL}/member/membership/payment-method/setup/${operation}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        cache: "no-store",
      },
    );
    const payload = await backendResponse.json().catch(() => ({}));
    return response(payload, backendResponse.status);
  } catch {
    return response({ detail: "El servicio de pagos no está disponible." }, 502);
  }
}

function response(payload: unknown, status: number): NextResponse {
  const result = NextResponse.json(payload, { status });
  result.headers.set("Cache-Control", "no-store, private");
  result.headers.set("Referrer-Policy", "no-referrer");
  result.headers.set("X-Content-Type-Options", "nosniff");
  return result;
}
