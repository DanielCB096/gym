import Constants from "expo-constants";
import { Platform } from "react-native";

import { registerMemberPushToken, revokeMemberPushToken } from "./api";
import type { MemberPushPlatform } from "./types";

type PushRegistration = {
  token: string;
  platform: MemberPushPlatform;
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
