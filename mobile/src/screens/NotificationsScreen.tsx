import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";

import {
  ApiError,
  getMemberNotificationPreferences,
  getMemberNotifications,
  markAllMemberNotificationsRead,
  markMemberNotificationRead,
  updateMemberNotificationPreferences,
} from "../api";
import { describeError } from "../errors";
import { formatDateTime, notificationKindLabel } from "../format";
import {
  notificationDestination,
  type NotificationDestination,
} from "../notificationRouting";
import { colors, radius, sharedStyles, spacing } from "../theme";
import type {
  MemberNotification,
  MemberNotificationCategory,
  MemberNotificationPage,
  MemberNotificationPreference,
} from "../types";

const DESTINATION_LABELS: Record<NotificationDestination, string> = {
  home: "el inicio",
  invoices: "facturas",
  classes: "clases",
  physio: "fisioterapia",
  routines: "rutinas",
  notifications: "",
};

const CATEGORY_LABELS: Record<MemberNotificationCategory, string> = {
  membership: "Membresía",
  classes: "Clases",
  training: "Rutinas y metas",
  billing: "Facturas",
  equipment: "Equipo fuera de servicio",
  physio: "Fisioterapia",
};

type Props = {
  token: string;
  onBack: () => void;
  onSessionExpired: () => void;
  onUnreadChange: (count: number) => void;
  onOpenInvoices: () => void;
  onOpenClasses: () => void;
  onOpenPhysio: () => void;
  onOpenRoutines: () => void;
  onOpenHome: () => void;
};

export function NotificationsScreen({
  token,
  onBack,
  onSessionExpired,
  onUnreadChange,
  onOpenInvoices,
  onOpenClasses,
  onOpenPhysio,
  onOpenRoutines,
  onOpenHome,
}: Props) {
  const [inbox, setInbox] = useState<MemberNotificationPage | null>(null);
  const [preferences, setPreferences] = useState<
    MemberNotificationPreference[] | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [preferenceBusy, setPreferenceBusy] =
    useState<MemberNotificationCategory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(
    async (mode: "initial" | "refresh") => {
      setLoading(mode === "initial");
      setRefreshing(mode === "refresh");
      try {
        const [next, prefs] = await Promise.all([
          getMemberNotifications(token),
          getMemberNotificationPreferences(token),
        ]);
        setInbox(next);
        setPreferences(prefs.items);
        onUnreadChange(next.unread_total);
        setError(null);
      } catch (loadError) {
        if (loadError instanceof ApiError && loadError.status === 401) {
          onSessionExpired();
          return;
        }
        setError(describeError(loadError));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [onSessionExpired, onUnreadChange, token],
  );

  useEffect(() => {
    void load("initial");
  }, [load]);

  async function handleOpen(item: MemberNotification) {
    if (busy) {
      return;
    }
    if (!item.read_at) {
      setBusy(true);
      try {
        const marked = await markMemberNotificationRead(token, item.id);
        const unread = Math.max(0, (inbox?.unread_total ?? 0) - 1);
        onUnreadChange(unread);
        setInbox((current) =>
          current
            ? {
                ...current,
                unread_total: unread,
                items: current.items.map((row) => (row.id === marked.id ? marked : row)),
              }
            : current,
        );
        setError(null);
      } catch (markError) {
        if (markError instanceof ApiError && markError.status === 401) {
          onSessionExpired();
          return;
        }
        setError(describeError(markError));
        return;
      } finally {
        setBusy(false);
      }
    }
    switch (notificationDestination(item.kind)) {
      case "invoices":
        onOpenInvoices();
        break;
      case "classes":
        onOpenClasses();
        break;
      case "physio":
        onOpenPhysio();
        break;
      case "routines":
        onOpenRoutines();
        break;
      case "home":
        onOpenHome();
        break;
      case "notifications":
        break;
    }
  }

  async function handleMarkAll() {
    if (busy) {
      return;
    }
    setBusy(true);
    try {
      const updated = await markAllMemberNotificationsRead(token);
      setInbox((current) =>
        current
          ? {
              ...current,
              unread_total: 0,
              items: current.items.map((row) => ({ ...row, read_at: row.read_at ?? new Date().toISOString() })),
            }
          : current,
      );
      onUnreadChange(0);
      setNotice(
        updated === 0
          ? "Ya no tienes avisos sin leer."
          : `Marcaste ${updated} aviso${updated === 1 ? "" : "s"} como leído${updated === 1 ? "" : "s"}.`,
      );
      setError(null);
    } catch (markError) {
      if (markError instanceof ApiError && markError.status === 401) {
        onSessionExpired();
        return;
      }
      setError(describeError(markError));
    } finally {
      setBusy(false);
    }
  }

  async function handleTogglePreference(
    category: MemberNotificationCategory,
    pushEnabled: boolean,
  ) {
    if (preferenceBusy !== null) {
      return;
    }
    const previous = preferences;
    setPreferenceBusy(category);
    setPreferences((current) =>
      current
        ? current.map((item) =>
            item.category === category ? { ...item, push_enabled: pushEnabled } : item,
          )
        : current,
    );
    try {
      const updated = await updateMemberNotificationPreferences(token, [
        { category, push_enabled: pushEnabled },
      ]);
      setPreferences(updated.items);
      setNotice(
        pushEnabled
          ? `${CATEGORY_LABELS[category]}: volverás a recibir el aviso en el teléfono.`
          : `${CATEGORY_LABELS[category]}: dejaremos de avisarte en el teléfono. El aviso seguirá en tu bandeja.`,
      );
      setError(null);
    } catch (toggleError) {
      setPreferences(previous);
      if (toggleError instanceof ApiError && toggleError.status === 401) {
        onSessionExpired();
        return;
      }
      setError(describeError(toggleError));
    } finally {
      setPreferenceBusy(null);
    }
  }

  const unreadTotal = inbox?.unread_total ?? 0;

  return (
    <ScrollView
      style={sharedStyles.screen}
      contentContainerStyle={styles.container}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => void load("refresh")}
          tintColor={colors.accent}
          colors={[colors.accent]}
          progressBackgroundColor={colors.surface}
        />
      }
    >
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Volver al inicio"
        onPress={onBack}
        style={styles.back}
        hitSlop={12}
      >
        <Text style={styles.backText}>← Inicio</Text>
      </Pressable>

      <View style={styles.hero}>
        <Text style={sharedStyles.label}>Tus avisos</Text>
        <Text style={sharedStyles.title}>Notificaciones</Text>
        <Text style={sharedStyles.body}>
          Lo que pasó en el gimnasio: revisiones de tus entrenamientos, cambios en
          tus metas, lugares que se liberaron y tu membresía.
        </Text>
        {inbox ? (
          <Text style={sharedStyles.hint}>
            {unreadTotal === 0
              ? "Estás al día."
              : `Tienes ${unreadTotal} aviso${unreadTotal === 1 ? "" : "s"} sin leer.`}
          </Text>
        ) : null}
      </View>

      {error ? (
        <View style={styles.errorBanner}>
          <Text style={sharedStyles.error}>{error}</Text>
        </View>
      ) : null}

      {notice ? (
        <View style={styles.noticeBanner}>
          <Text style={styles.noticeText}>{notice}</Text>
        </View>
      ) : null}

      {unreadTotal > 0 ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Marcar todos los avisos como leídos"
          onPress={() => void handleMarkAll()}
          style={({ pressed }) => [
            sharedStyles.primaryButton,
            busy && sharedStyles.primaryButtonDisabled,
            pressed && sharedStyles.primaryButtonPressed,
          ]}
        >
          <Text style={sharedStyles.primaryButtonText}>Marcar todas como leídas</Text>
        </Pressable>
      ) : null}

      {loading && !inbox ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.accent} />
          <Text style={sharedStyles.body}>Cargando tus avisos…</Text>
        </View>
      ) : null}

      {inbox ? (
        <View style={sharedStyles.card}>
          {inbox.items.length === 0 ? (
            <Text style={sharedStyles.body}>
              Todavía no hay avisos. Aquí verás lo que el gimnasio registre sobre ti.
            </Text>
          ) : (
            inbox.items.map((item) => {
              const destination = notificationDestination(item.kind);
              return (
                <Pressable
                  key={item.id}
                  accessibilityRole="button"
                  accessibilityLabel={
                    destination === "notifications"
                      ? item.read_at
                        ? `Aviso leído: ${item.title}`
                        : `Marcar como leído: ${item.title}`
                      : `Abrir ${DESTINATION_LABELS[destination]}: ${item.title}`
                  }
                  onPress={() => void handleOpen(item)}
                  style={({ pressed }) => [
                    styles.row,
                    item.read_at ? styles.rowRead : styles.rowUnread,
                    pressed && styles.rowPressed,
                  ]}
                >
                  <View style={styles.rowHeading}>
                    <View style={styles.pill}>
                      <Text style={styles.pillText}>{notificationKindLabel(item.kind)}</Text>
                    </View>
                    {!item.read_at ? <View style={styles.unreadDot} /> : null}
                  </View>
                  <Text style={styles.rowTitle}>{item.title}</Text>
                  <Text style={sharedStyles.body}>{item.body}</Text>
                  <Text style={sharedStyles.hint}>{formatDateTime(item.created_at)}</Text>
                </Pressable>
              );
            })
          )}
          {inbox && inbox.total > inbox.items.length ? (
            <Text style={sharedStyles.hint}>
              Mostrando los últimos {inbox.items.length} de {inbox.total} avisos.
            </Text>
          ) : null}
        </View>
      ) : null}

      {preferences ? (
        <View style={sharedStyles.card}>
          <Text style={sharedStyles.label}>Avisos en el teléfono</Text>
          <Text style={sharedStyles.body}>
            Elige qué avisos quieres que suenen en tu teléfono. Si apagas una
            categoría, el aviso se guarda igual en tu bandeja y solo deja de
            interrumpirte.
          </Text>
          {preferences.map((item) => (
            <View key={item.category} style={styles.preferenceRow}>
              <View style={styles.preferenceCopy}>
                <Text style={styles.preferenceTitle}>
                  {CATEGORY_LABELS[item.category]}
                </Text>
                <Text style={sharedStyles.hint}>
                  {item.push_enabled
                    ? "Te avisamos en el teléfono."
                    : "Solo aparece en tu bandeja."}
                </Text>
              </View>
              <Switch
                accessibilityRole="switch"
                accessibilityLabel={`Avisos de ${CATEGORY_LABELS[item.category]} en el teléfono`}
                value={item.push_enabled}
                disabled={preferenceBusy !== null}
                onValueChange={(value) =>
                  void handleTogglePreference(item.category, value)
                }
                trackColor={{ false: colors.surfaceMuted, true: colors.accent }}
                thumbColor={colors.surface}
              />
            </View>
          ))}
        </View>
      ) : null}

      <Text style={sharedStyles.hint}>
        Toca un aviso para marcarlo como leído. Los de factura abren Facturas; los de
        clase, Clases; los de fisioterapia, Fisioterapia; los de rutina y equipo,
        Rutinas; y los de membresía, el inicio. Los avisos no se borran: quedan en tu
        historial. Desliza hacia abajo para actualizar.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: spacing.md,
    padding: spacing.lg,
    paddingBottom: spacing.xl,
  },
  back: {
    alignSelf: "flex-start",
  },
  backText: {
    color: colors.textMuted,
    fontSize: 14,
    fontWeight: "700",
  },
  hero: {
    gap: spacing.xs,
  },
  errorBanner: {
    backgroundColor: "rgba(248, 113, 113, 0.12)",
    borderRadius: radius.md,
    padding: spacing.md,
  },
  noticeBanner: {
    backgroundColor: "rgba(34, 197, 94, 0.12)",
    borderRadius: radius.md,
    padding: spacing.md,
  },
  noticeText: {
    color: colors.text,
    fontSize: 14,
    fontWeight: "600",
  },
  loading: {
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.xl,
  },
  row: {
    borderTopColor: colors.border,
    borderTopWidth: 1,
    gap: spacing.xs,
    paddingTop: spacing.md,
    marginTop: spacing.md,
  },
  rowUnread: {
    borderLeftColor: colors.accent,
    borderLeftWidth: 3,
    paddingLeft: spacing.sm,
  },
  rowRead: {
    opacity: 0.7,
  },
  rowPressed: {
    backgroundColor: colors.surfaceMuted,
  },
  rowHeading: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  preferenceRow: {
    alignItems: "center",
    borderTopColor: colors.border,
    borderTopWidth: 1,
    flexDirection: "row",
    gap: spacing.md,
    justifyContent: "space-between",
    marginTop: spacing.md,
    paddingTop: spacing.md,
  },
  preferenceCopy: {
    flex: 1,
    gap: 2,
  },
  preferenceTitle: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "700",
  },
  rowTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: "800",
  },
  unreadDot: {
    backgroundColor: colors.accent,
    borderRadius: 5,
    height: 10,
    width: 10,
  },
  pill: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  pillText: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: "700",
  },
});
