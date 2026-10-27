import { API_URL, REQUEST_TIMEOUT_MS } from "./config";
import type {
  CodeRequestResult,
  MemberClassPage,
  MemberClassReservation,
  MemberLoginResult,
  MemberProfile,
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type RequestOptions = {
  method?: "GET" | "POST";
  body?: unknown;
  token?: string;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });
  } catch (error) {
    const message =
      error instanceof Error && error.name === "AbortError"
        ? "El servidor tardó demasiado en responder. Intenta de nuevo."
        : "No se pudo conectar con el servidor. Revisa tu conexión e intenta de nuevo.";
    throw new ApiError(0, message);
  } finally {
    clearTimeout(timeout);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    throw new ApiError(response.status, detailFrom(payload) ?? fallbackMessage(response.status));
  }
  return payload as T;
}

function detailFrom(payload: unknown): string | null {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
  }
  return null;
}

function fallbackMessage(status: number): string {
  if (status === 401) {
    return "Tu sesión no es válida. Vuelve a entrar.";
  }
  if (status >= 500) {
    return "El gimnasio no está disponible en este momento. Intenta más tarde.";
  }
  return "No se pudo completar la solicitud. Intenta de nuevo.";
}

export function requestLoginCode(email: string): Promise<CodeRequestResult> {
  return request<CodeRequestResult>("/member/auth/request-code", {
    method: "POST",
    body: { email },
  });
}

export function verifyLoginCode(email: string, code: string): Promise<MemberLoginResult> {
  return request<MemberLoginResult>("/member/auth/verify", {
    method: "POST",
    body: { email, code },
  });
}

export function getMemberProfile(token: string): Promise<MemberProfile> {
  return request<MemberProfile>("/member/me", { token });
}

export function logoutMember(token: string): Promise<void> {
  return request<void>("/member/auth/logout", { method: "POST", token });
}

export function getMemberClasses(token: string, days = 14): Promise<MemberClassPage> {
  return request<MemberClassPage>(`/member/classes?days=${days}`, { token });
}

export function reserveMemberClass(
  token: string,
  sessionId: string,
): Promise<MemberClassReservation> {
  return request<MemberClassReservation>(
    `/member/classes/sessions/${sessionId}/reservations`,
    { method: "POST", token },
  );
}

export function cancelMemberReservation(
  token: string,
  reservationId: string,
): Promise<MemberClassReservation> {
  return request<MemberClassReservation>(
    `/member/classes/reservations/${reservationId}/cancel`,
    { method: "POST", token },
  );
}
