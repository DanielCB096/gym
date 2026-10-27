import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

const TOKEN_KEY = "centro_fit_member_token";

// The web build is only a local preview surface: the token stays in memory so
// it is never written to browser storage.
export async function loadToken(): Promise<string | null> {
  if (Platform.OS === "web") {
    return null;
  }
  try {
    return await SecureStore.getItemAsync(TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function saveToken(token: string): Promise<void> {
  if (Platform.OS === "web") {
    return;
  }
  try {
    await SecureStore.setItemAsync(TOKEN_KEY, token, {
      keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    });
  } catch {
    // The session still works in memory; it just will not survive a restart.
  }
}

export async function clearToken(): Promise<void> {
  if (Platform.OS === "web") {
    return;
  }
  try {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
  } catch {
    // Nothing else to clean up.
  }
}
