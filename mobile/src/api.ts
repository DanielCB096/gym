import { Platform } from "react-native";

import { API_URL, REQUEST_TIMEOUT_MS } from "./config";
import type {
  CodeRequestResult,
  MemberAccessCode,
  MemberAccessCodeStatus,
  MemberAccount,
  MemberAutoRenewal,
  MemberBillableOriginPage,
  MemberClassPage,
  MemberClassReservation,
  MemberCheckoutPlanList,
  MemberFiscalProfile,
  MemberGoal,
  MemberGoalInput,
  MemberHostedCheckout,
  MemberInvoicePage,
  MemberInvoiceRequestInput,
  MemberInvoiceRequestResult,
  MemberLoginResult,
  MemberPaymentPage,
  MemberProfile,
  MemberMeasurement,
  MemberMeasurementInput,
  MemberNotification,
  MemberNotificationCategory,
  MemberNotificationPage,
  MemberNotificationPreferences,
  MemberPhysioOverview,
  MemberProgress,
  MemberProgressPhoto,
  MemberProgressPhotoInput,
  MemberProgressPhotoList,
  MemberPushPlatform,
  MemberPushToken,
  MemberRoutineDetail,
  MemberRoutineList,
  MemberWorkout,
  MemberWorkoutInput,
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
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  form?: FormData;
  token?: string;
  headers?: Record<string, string>;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...options.headers,
  };
  if (options.form === undefined && options.body !== undefined) {
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
      body:
        options.form ??
        (options.body === undefined ? undefined : JSON.stringify(options.body)),
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

export function requestMemberAccessCode(token: string): Promise<MemberAccessCode> {
  return request<MemberAccessCode>("/member/access/code", {
    method: "POST",
    token,
  });
}

export function getMemberAccessCodeStatus(
  token: string,
): Promise<MemberAccessCodeStatus> {
  return request<MemberAccessCodeStatus>("/member/access/code", { token });
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

export function getMemberPhysio(token: string): Promise<MemberPhysioOverview> {
  return request<MemberPhysioOverview>("/member/physio", { token });
}

export function getMemberRoutines(token: string): Promise<MemberRoutineList> {
  return request<MemberRoutineList>("/member/routines", { token });
}

export function getMemberRoutine(token: string, assignmentId: string): Promise<MemberRoutineDetail> {
  return request<MemberRoutineDetail>(`/member/routines/${assignmentId}`, { token });
}

export function getMemberProgress(token: string): Promise<MemberProgress> {
  return request<MemberProgress>("/member/progress", { token });
}

export function logMemberWorkout(
  token: string,
  assignmentId: string,
  input: MemberWorkoutInput,
): Promise<MemberWorkout> {
  return request<MemberWorkout>(`/member/routines/${assignmentId}/workouts`, {
    method: "POST",
    token,
    body: input,
  });
}

export function recordMemberMeasurement(
  token: string,
  input: MemberMeasurementInput,
): Promise<MemberMeasurement> {
  return request<MemberMeasurement>("/member/progress/measurements", {
    method: "POST",
    token,
    body: input,
  });
}

export function createMemberGoal(
  token: string,
  input: MemberGoalInput,
): Promise<MemberGoal> {
  return request<MemberGoal>("/member/progress/goals", {
    method: "POST",
    token,
    body: input,
  });
}

export function cancelMemberGoal(token: string, goalId: string): Promise<MemberGoal> {
  return request<MemberGoal>(`/member/progress/goals/${goalId}/cancel`, {
    method: "POST",
    token,
  });
}

export function getMemberProgressPhotos(token: string): Promise<MemberProgressPhotoList> {
  return request<MemberProgressPhotoList>("/member/progress/photos", { token });
}

export type PhotoUploadAsset = {
  uri: string;
  name: string;
  type: string;
};

export function memberProgressPhotoUri(filePath: string): string {
  return `${API_URL}${filePath}`;
}

export async function uploadMemberProgressPhoto(
  token: string,
  asset: PhotoUploadAsset,
  input: MemberProgressPhotoInput,
): Promise<MemberProgressPhoto> {
  const form = new FormData();
  if (Platform.OS === "web") {
    const blob = await (await fetch(asset.uri)).blob();
    form.append("photo", blob, asset.name);
  } else {
    form.append("photo", {
      uri: asset.uri,
      name: asset.name,
      type: asset.type,
    } as unknown as Blob);
  }
  form.append("angle", input.angle);
  if (input.captured_at) {
    form.append("captured_at", input.captured_at);
  }
  if (input.notes) {
    form.append("notes", input.notes);
  }
  form.append("consent", input.consent ? "true" : "false");
  return request<MemberProgressPhoto>("/member/progress/photos", {
    method: "POST",
    token,
    form,
  });
}

export function deleteMemberProgressPhoto(token: string, photoId: string): Promise<void> {
  return request<void>(`/member/progress/photos/${photoId}`, {
    method: "DELETE",
    token,
  });
}

export function getMemberPayments(token: string, pageSize = 20): Promise<MemberPaymentPage> {
  return request<MemberPaymentPage>(`/member/payments?page=1&page_size=${pageSize}`, {
    token,
  });
}

export function getMemberCheckoutPlans(token: string): Promise<MemberCheckoutPlanList> {
  return request<MemberCheckoutPlanList>("/member/membership/plans", { token });
}

export function getMemberAutoRenewal(token: string): Promise<MemberAutoRenewal> {
  return request<MemberAutoRenewal>("/member/membership/auto-renewal", { token });
}

export function updateMemberAutoRenewal(
  token: string,
  enabled: boolean,
): Promise<MemberAutoRenewal> {
  return request<MemberAutoRenewal>("/member/membership/auto-renewal", {
    method: "POST",
    token,
    body: { enabled },
  });
}

export function createMemberCheckout(
  token: string,
  planId: string,
  idempotencyKey: string,
): Promise<MemberHostedCheckout> {
  return request<MemberHostedCheckout>("/member/membership/checkout", {
    method: "POST",
    token,
    body: { plan_id: planId },
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

export function getMemberAccount(token: string): Promise<MemberAccount> {
  return request<MemberAccount>("/member/account", { token });
}

export function getMemberInvoices(token: string, pageSize = 20): Promise<MemberInvoicePage> {
  return request<MemberInvoicePage>(`/member/invoices?page=1&page_size=${pageSize}`, {
    token,
  });
}

export function getMemberBillableOrigins(
  token: string,
  pageSize = 50,
): Promise<MemberBillableOriginPage> {
  return request<MemberBillableOriginPage>(
    `/member/invoices/origins?page=1&page_size=${pageSize}`,
    { token },
  );
}

export function getMemberFiscalProfile(
  token: string,
): Promise<MemberFiscalProfile | null> {
  return request<{ profile: MemberFiscalProfile | null }>(
    "/member/fiscal-profile",
    { token },
  ).then((result) => result.profile);
}

export function requestMemberInvoice(
  token: string,
  input: MemberInvoiceRequestInput,
): Promise<MemberInvoiceRequestResult> {
  return request<MemberInvoiceRequestResult>("/member/invoices", {
    method: "POST",
    token,
    body: input,
  });
}

export function getMemberNotifications(
  token: string,
  pageSize = 30,
): Promise<MemberNotificationPage> {
  return request<MemberNotificationPage>(`/member/notifications?page=1&page_size=${pageSize}`, {
    token,
  });
}

export function getUnreadNotificationCount(token: string): Promise<number> {
  return request<{ unread: number }>("/member/notifications/unread-count", { token }).then(
    (result) => result.unread,
  );
}

export function markMemberNotificationRead(
  token: string,
  notificationId: string,
): Promise<MemberNotification> {
  return request<MemberNotification>(`/member/notifications/${notificationId}/read`, {
    method: "POST",
    token,
  });
}

export function markAllMemberNotificationsRead(
  token: string,
): Promise<number> {
  return request<{ updated: number }>("/member/notifications/read-all", {
    method: "POST",
    token,
  }).then((result) => result.updated);
}

export function getMemberNotificationPreferences(
  token: string,
): Promise<MemberNotificationPreferences> {
  return request<MemberNotificationPreferences>("/member/notification-preferences", {
    token,
  });
}

export function updateMemberNotificationPreferences(
  token: string,
  categories: {
    category: MemberNotificationCategory;
    push_enabled?: boolean;
    email_enabled?: boolean;
  }[],
): Promise<MemberNotificationPreferences> {
  return request<MemberNotificationPreferences>("/member/notification-preferences", {
    method: "PATCH",
    token,
    body: { categories },
  });
}

export function updateMemberNotificationQuietHours(
  token: string,
  quietHours: { start: string; end: string } | null,
): Promise<MemberNotificationPreferences> {
  return request<MemberNotificationPreferences>("/member/notification-preferences", {
    method: "PATCH",
    token,
    body: { quiet_hours: quietHours },
  });
}

export function registerMemberPushToken(
  token: string,
  pushToken: string,
  platform: MemberPushPlatform,
): Promise<MemberPushToken> {
  return request<MemberPushToken>("/member/push-tokens", {
    method: "POST",
    token,
    body: { token: pushToken, platform },
  });
}

export function revokeMemberPushToken(
  token: string,
  pushToken: string,
): Promise<void> {
  return request<void>("/member/push-tokens/revoke", {
    method: "POST",
    token,
    body: { token: pushToken },
  });
}
