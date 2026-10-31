import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  ApiError,
  getMemberNotificationPreferences,
  getMemberNotifications,
  markAllMemberNotificationsRead,
  markMemberNotificationRead,
  updateMemberNotificationPreferences,
  updateMemberNotificationQuietHours,
} from "../api";
import { describeError } from "../errors";
import { formatDateTime, notificationKindLabel } from "../format";
import {
  notificationDestination,
  type NotificationDestination,
} from "../notificationRouting";
import { PUSH_PROBE_ENABLED, scheduleLocalPushProbe } from "../pushProbe";
import { colors, radius, sharedStyles, spacing } from "../theme";
import type {
  MemberClubQuietHours,
  MemberNotification,
  MemberNotificationCategory,
  MemberNotificationPage,
  MemberNotificationPreference,
  MemberNotificationQuietHours,
} from "../types";

const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;

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
  const [quietHours, setQuietHours] =
    useState<MemberNotificationQuietHours | null>(null);
  const [clubQuietHours, setClubQuietHours] =
    useState<MemberClubQuietHours | null>(null);
  const [quietStart, setQuietStart] = useState("");
  const [quietEnd, setQuietEnd] = useState("");
  const [quietBusy, setQuietBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [preferenceBusy, setPreferenceBusy] =
    useState<MemberNotificationCategory | null>(null);
  const [probeBusy, setProbeBusy] = useState(false);
  const [probeNotice, setProbeNotice] = useState<string | null>(null);
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
        setQuietHours(prefs.quiet_hours);
        setClubQuietHours(prefs.club_quiet_hours);
        setQuietStart(prefs.quiet_hours?.start ?? "");
        setQuietEnd(prefs.quiet_hours?.end ?? "");
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

  async function saveQuietHours(payload: { start: string; end: string } | null) {
    setQuietBusy(true);
    try {
      const updated = await updateMemberNotificationQuietHours(token, payload);
      setPreferences(updated.items);
      setQuietHours(updated.quiet_hours);
      setClubQuietHours(updated.club_quiet_hours);
      setQuietStart(updated.quiet_hours?.start ?? "");
      setQuietEnd(updated.quiet_hours?.end ?? "");
      setNotice(
        payload
          ? `Silencio de ${payload.start} a ${payload.end}: en ese tramo tu teléfono no suena. Los avisos te esperan en la bandeja.`
          : "Quitamos tu horario de silencio: tu teléfono vuelve a sonar cuando llegue un aviso.",
      );
      setError(null);
    } catch (quietError) {
      if (quietError instanceof ApiError && quietError.status === 401) {
        onSessionExpired();
        return;
      }
      setError(describeError(quietError));
    } finally {
      setQuietBusy(false);
    }
  }

  async function handleSaveQuietHours() {
    if (quietBusy) {
      return;
    }
    const start = quietStart.trim();
    const end = quietEnd.trim();
    if (!start && !end) {
      await saveQuietHours(null);
      return;
    }
    if (!TIME_PATTERN.test(start) || !TIME_PATTERN.test(end)) {
      setError("Escribe las horas como HH:MM, por ejemplo 22:00 y 07:00.");
      return;
    }
    if (start === end) {
      setError("La hora de inicio y la de fin deben ser distintas.");
      return;
    }
    await saveQuietHours({ start, end });
  }

  async function handleScheduleProbe() {
    if (probeBusy) {
      return;
    }
    setProbeBusy(true);
    try {
      const first = inbox?.items[0];
      await scheduleLocalPushProbe(
        first ? { id: first.id, kind: first.kind } : undefined,
      );
      setProbeNotice(
        "Aviso programado para dentro de 20 segundos. Cierra la app sin forzar su detención, espera a que suene y tócalo.",
      );
    } catch (probeError) {
      setProbeNotice(
        probeError instanceof Error ? probeError.message : describeError(probeError),
      );
    } finally {
      setProbeBusy(false);
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

      {preferences ? (
        <View style={sharedStyles.card}>
          <Text style={sharedStyles.label}>Tu horario de silencio</Text>
        <Text style={sharedStyles.body}>
          Elige una franja en la que no quieras que suene el teléfono, en la hora
          del gimnasio. Los avisos no se pierden: se guardan en tu bandeja y el
          teléfono vuelve a sonar cuando la franja termina.
        </Text>
        <Text style={sharedStyles.hint}>
          {quietHours
            ? quietHours.active
              ? `Ahora mismo está en silencio: tu teléfono no sonará hasta las ${quietHours.end}.`
              : `En silencio de ${quietHours.start} a ${quietHours.end}.`
            : "Sin horario propio: tu teléfono suena a cualquier hora."}
        </Text>
        {clubQuietHours ? (
          <Text style={sharedStyles.hint}>
            {clubQuietHours.active
              ? `El gimnasio también mantiene el silencio hasta las ${clubQuietHours.end}.`
              : `El gimnasio también silencia de ${clubQuietHours.start} a ${clubQuietHours.end}.`}
          </Text>
        ) : null}
        <View style={styles.quietRow}>
          <View style={styles.quietField}>
            <Text style={styles.quietLabel}>Desde</Text>
            <TextInput
              accessibilityLabel="Hora de inicio del silencio"
              value={quietStart}
              onChangeText={setQuietStart}
              placeholder="22:00"
              placeholderTextColor={colors.textMuted}
              maxLength={5}
              autoCapitalize="none"
              autoCorrect={false}
              editable={!quietBusy}
              style={sharedStyles.input}
            />
          </View>
          <View style={styles.quietField}>
            <Text style={styles.quietLabel}>Hasta</Text>
            <TextInput
              accessibilityLabel="Hora de fin del silencio"
              value={quietEnd}
              onChangeText={setQuietEnd}
              placeholder="07:00"
              placeholderTextColor={colors.textMuted}
              maxLength={5}
              autoCapitalize="none"
              autoCorrect={false}
              editable={!quietBusy}
              style={sharedStyles.input}
            />
          </View>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Guardar horario de silencio"
          disabled={quietBusy}
          onPress={() => void handleSaveQuietHours()}
          style={({ pressed }) => [
            sharedStyles.primaryButton,
            quietBusy && sharedStyles.primaryButtonDisabled,
            pressed && sharedStyles.primaryButtonPressed,
          ]}
        >
          <Text style={sharedStyles.primaryButtonText}>
            {quietBusy ? "Guardando…" : "Guardar horario"}
          </Text>
        </Pressable>
        {quietHours ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Quitar horario de silencio"
            disabled={quietBusy}
            onPress={() => void saveQuietHours(null)}
            style={({ pressed }) => [
              sharedStyles.secondaryButton,
              quietBusy && sharedStyles.primaryButtonDisabled,
              pressed && sharedStyles.secondaryButtonPressed,
            ]}
          >
            <Text style={sharedStyles.secondaryButtonText}>Quitar horario</Text>
          </Pressable>
        ) : null}
        </View>
      ) : null}

      {PUSH_PROBE_ENABLED ? (
        <View style={sharedStyles.card}>
          <Text style={sharedStyles.label}>Prueba de arranque en frío</Text>
          <Text style={sharedStyles.body}>
            Programa un aviso local con el mismo payload del push. Sal de la app
            antes de que suene y toca el aviso: debe abrir la pantalla que le
            corresponde sin pasar por el inicio.
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Programar aviso local de prueba"
            disabled={probeBusy}
            onPress={() => void handleScheduleProbe()}
            style={({ pressed }) => [
              sharedStyles.secondaryButton,
              probeBusy && sharedStyles.primaryButtonDisabled,
              pressed && sharedStyles.secondaryButtonPressed,
            ]}
          >
            <Text style={sharedStyles.secondaryButtonText}>
              {probeBusy ? "Programando…" : "Programar aviso en 20 segundos"}
            </Text>
          </Pressable>
          {probeNotice ? (
            <Text style={sharedStyles.hint}>{probeNotice}</Text>
          ) : null}
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
  quietRow: {
    flexDirection: "row",
    gap: spacing.md,
    marginTop: spacing.sm,
  },
  quietField: {
    flex: 1,
    gap: spacing.xs,
  },
  quietLabel: {
    color: colors.textMuted,
    fontSize: 13,
    fontWeight: "700",
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
