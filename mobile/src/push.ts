import Constants from "expo-constants";
import type { NotificationResponse } from "expo-notifications";
import { Platform } from "react-native";

import { registerMemberPushToken, revokeMemberPushToken } from "./api";
import type { MemberPushPlatform } from "./types";

type PushRegistration = {
  token: string;
  platform: MemberPushPlatform;
};

export type PushTap = {
  notificationId: string | null;
  kind: string | null;
  refId: string | null;
};

// One installation registers once per session; the backend transfers a device
// token to whichever member signs in last, so keeping it in memory is enough.
let registered: PushRegistration | null = null;

function devicePlatform(): MemberPushPlatform | null {
  if (Platform.OS === "ios") {
    return "ios";
  }
  if (Platform.OS === "android") {
    return "android";
  }
  return null;
}

function projectId(): string | null {
  const extra = Constants.expoConfig?.extra as
    | { eas?: { projectId?: string } }
    | undefined;
  return extra?.eas?.projectId ?? Constants.easConfig?.projectId ?? null;
}

async function resolveDeviceToken(): Promise<PushRegistration | null> {
  const platform = devicePlatform();
  const project = projectId();
  // Web has no push token, and without an EAS project there is nothing to ask
  // Expo for; the app keeps working and simply does not ring the phone.
  if (!platform || !project) {
    return null;
  }
  const notifications = await import("expo-notifications");
  const current = await notifications.getPermissionsAsync();
  const granted =
    current.granted ||
    (current.canAskAgain && (await notifications.requestPermissionsAsync()).granted);
  if (!granted) {
    return null;
  }
  const { data } = await notifications.getExpoPushTokenAsync({ projectId: project });
  return data ? { token: data, platform } : null;
}

export async function registerPushForSession(accessToken: string): Promise<void> {
  try {
    const registration = await resolveDeviceToken();
    if (!registration) {
      return;
    }
    await registerMemberPushToken(accessToken, registration.token, registration.platform);
    registered = registration;
  } catch {
    // The inbox in the app keeps working without push permissions or network.
  }
}

function tapFromResponse(response: NotificationResponse): PushTap | null {
  const data = response.notification.request.content.data ?? {};
  const kind = typeof data.kind === "string" ? data.kind : null;
  const rawId = data.notification_id;
  const notificationId = typeof rawId === "string" ? rawId : null;
  const rawRef = data.ref_id;
  const refId = typeof rawRef === "string" ? rawRef : null;
  if (!kind && !notificationId) {
    return null;
  }
  return { kind, notificationId, refId };
}

// Native only: the web preview has no notification responses. The tap that
// launched the app is read once from the last response and cleared so a later
// remount does not navigate again.
export async function subscribePushTaps(
  onTap: (tap: PushTap) => void,
): Promise<() => void> {
  if (!devicePlatform()) {
    return () => {};
  }
  let notifications: typeof import("expo-notifications");
  try {
    notifications = await import("expo-notifications");
  } catch {
    return () => {};
  }
  const subscription = notifications.addNotificationResponseReceivedListener(
    (response) => {
      const tap = tapFromResponse(response);
      if (tap) {
        onTap(tap);
      }
    },
  );
  const last = notifications.getLastNotificationResponse();
  if (last) {
    notifications.clearLastNotificationResponse();
    const tap = tapFromResponse(last);
    if (tap) {
      onTap(tap);
    }
  }
  return () => subscription.remove();
}

export async function unregisterPushForSession(accessToken: string): Promise<void> {
  const registration = registered;
  registered = null;
  if (!registration) {
    return;
  }
  try {
    await revokeMemberPushToken(accessToken, registration.token);
  } catch {
    // Signing out still deactivates the member's tokens on the server.
  }
}
