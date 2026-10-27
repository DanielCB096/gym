import { NextRequest, NextResponse } from "next/server";

export const SESSION_COOKIE = "gym_session";
export const GYM_API_URL = (process.env.GYM_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

// The backend rejects photos over 8 MB; leave room for the other form fields.
const MAX_FORM_DATA_BYTES = 9 * 1024 * 1024;

export async function proxyAuthenticatedGet(request: NextRequest, path: string): Promise<NextResponse> {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }

  try {
    const response = await fetch(`${GYM_API_URL}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    const proxyResponse = NextResponse.json(payload, { status: response.status });
    if (response.status === 401) {
      clearSessionCookie(proxyResponse);
    }
    return proxyResponse;
  } catch {
    return NextResponse.json({ detail: "Identity service is unavailable" }, { status: 502 });
  }
}

export async function proxyAuthenticatedDownload(
  request: NextRequest,
  path: string,
): Promise<NextResponse> {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }

  try {
    const response = await fetch(`${GYM_API_URL}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const failure = NextResponse.json(payload, { status: response.status });
      if (response.status === 401) {
        clearSessionCookie(failure);
      }
      return failure;
    }
    // Read bytes, not text: the same helper forwards CSV reports and binary PDF
    // statements. Decoding a PDF as UTF-8 would replace invalid sequences and
    // corrupt the file before it reaches the browser.
    const body = await response.arrayBuffer();
    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") ?? "text/csv; charset=utf-8",
        "Content-Disposition": response.headers.get("content-disposition") ?? "attachment",
        "Cache-Control": response.headers.get("cache-control") ?? "no-store, private",
        "X-Content-Type-Options": response.headers.get("x-content-type-options") ?? "nosniff",
      },
    });
  } catch {
    return NextResponse.json({ detail: "Identity service is unavailable" }, { status: 502 });
  }
}

export async function proxyAuthenticatedJson(
  request: NextRequest,
  path: string,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  body: unknown,
): Promise<NextResponse> {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({ detail: "Cross-origin request rejected" }, { status: 403 });
  }
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }

  try {
    const response = await fetch(`${GYM_API_URL}${path}`, {
      method,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    if (response.status === 204 || response.status === 205) {
      return new NextResponse(null, { status: response.status });
    }
    const proxyResponse = NextResponse.json(payload, { status: response.status });
    if (response.status === 401) {
      clearSessionCookie(proxyResponse);
    }
    return proxyResponse;
  } catch {
    return NextResponse.json({ detail: "Identity service is unavailable" }, { status: 502 });
  }
}

export async function proxyAuthenticatedFormData(
  request: NextRequest,
  path: string,
): Promise<NextResponse> {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({ detail: "Cross-origin request rejected" }, { status: 403 });
  }
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }
  const declaredLength = Number(request.headers.get("content-length") ?? "");
  if (Number.isFinite(declaredLength) && declaredLength > MAX_FORM_DATA_BYTES) {
    return NextResponse.json({ detail: "La imagen supera el límite permitido" }, { status: 413 });
  }

  let body: FormData;
  try {
    body = await request.formData();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }

  try {
    const response = await fetch(`${GYM_API_URL}${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body,
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    const proxyResponse = NextResponse.json(payload, { status: response.status });
    if (response.status === 401) {
      clearSessionCookie(proxyResponse);
    }
    return proxyResponse;
  } catch {
    return NextResponse.json({ detail: "Identity service is unavailable" }, { status: 502 });
  }
}

export function clearSessionCookie(response: NextResponse): void {
  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    expires: new Date(0),
  });
}

export function isSameOriginRequest(request: NextRequest): boolean {
  const originHeader = request.headers.get("origin");
  if (originHeader === null) return true;

  let origin: URL;
  let requestUrl: URL;
  try {
    origin = new URL(originHeader);
    requestUrl = new URL(request.url);
  } catch {
    return false;
  }

  const configuredOrigin = process.env.WEB_ORIGIN;
  if (configuredOrigin) {
    try {
      if (origin.origin === new URL(configuredOrigin).origin) return true;
    } catch {
      return false;
    }
  }
  if (origin.origin === requestUrl.origin) return true;
  if (process.env.NODE_ENV === "production") return false;

  const loopbackHosts = new Set(["localhost", "127.0.0.1", "::1"]);
  return (
    loopbackHosts.has(origin.hostname) &&
    loopbackHosts.has(requestUrl.hostname) &&
    origin.protocol === requestUrl.protocol &&
    origin.port === requestUrl.port
  );
}