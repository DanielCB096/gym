import { Platform } from "react-native";

// Solo en builds internos con EXPO_PUBLIC_PUSH_TEST=true. Sirve para probar el
// toque y el arranque en frío sin depender de FCM ni del backend.
export const PUSH_PROBE_ENABLED =
  process.env.EXPO_PUBLIC_PUSH_TEST === "true" && Platform.OS !== "web";

type ProbeNotice = {
  id: string;
  kind: string;
};

export async function scheduleLocalPushProbe(
  notice: ProbeNotice | undefined,
): Promise<void> {
  const notifications = await import("expo-notifications");
  const permissions = await notifications.getPermissionsAsync();
  const granted =
    permissions.granted ||
    (permissions.canAskAgain &&
      (await notifications.requestPermissionsAsync()).granted);
  if (!granted) {
    throw new Error("La app no tiene permiso para mostrar avisos.");
  }
  if (Platform.OS === "android") {
    await notifications.setNotificationChannelAsync("push-probe", {
      name: "Prueba de arranque en frío",
      importance: notifications.AndroidImportance.HIGH,
    });
  }
  await notifications.scheduleNotificationAsync({
    content: {
      title: "Prueba de arranque en frío",
      body: "Cierra la app y toca este aviso: debe abrir Facturas.",
      data: notice
        ? { notification_id: notice.id, kind: notice.kind }
        : { kind: "invoice_stamped" },
    },
    trigger: {
      type: notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
      seconds: 20,
      channelId: Platform.OS === "android" ? "push-probe" : undefined,
    },
  });
}
