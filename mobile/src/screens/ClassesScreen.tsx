import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import {
  ApiError,
  cancelMemberReservation,
  getMemberClasses,
  reserveMemberClass,
} from "../api";
import { describeError } from "../errors";
import {
  blockedReasonLabel,
  formatDateTime,
  formatMoney,
  reservationStatusLabel,
} from "../format";
import { colors, radius, sharedStyles, spacing } from "../theme";
import type { MemberClass, MemberClassPage } from "../types";

type Props = {
  token: string;
  onBack: () => void;
  onSessionExpired: () => void;
};

export function ClassesScreen({ token, onBack, onSessionExpired }: Props) {
  const [page, setPage] = useState<MemberClassPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(
    async (mode: "initial" | "refresh" | "silent") => {
      if (mode === "initial") {
        setLoading(true);
      }
      if (mode === "refresh") {
        setRefreshing(true);
      }
      try {
        const next = await getMemberClasses(token);
        setPage(next);
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
    [onSessionExpired, token],
  );

  useEffect(() => {
    void load("initial");
  }, [load]);

  async function runAction(item: MemberClass, action: () => Promise<unknown>) {
    setBusyId(item.id);
    setError(null);
    try {
      await action();
      await load("silent");
    } catch (actionError) {
      if (actionError instanceof ApiError && actionError.status === 401) {
        onSessionExpired();
        return;
      }
      setError(describeError(actionError));
    } finally {
      setBusyId(null);
    }
  }

  function handleReserve(item: MemberClass) {
    void runAction(item, () => reserveMemberClass(token, item.id));
  }

  function handleCancel(item: MemberClass) {
    const reservation = item.reservation;
    if (!reservation) {
      return;
    }
    void runAction(item, () => cancelMemberReservation(token, reservation.id));
  }

  function renderAction(item: MemberClass) {
    const busy = busyId === item.id;
    const cancelable =
      item.reservation !== null &&
      (item.reservation.status === "reserved" || item.reservation.status === "waitlist");

    if (cancelable) {
      return (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Cancelar reserva de ${item.title}`}
          disabled={busy}
          onPress={() => handleCancel(item)}
          style={({ pressed }) => [
            sharedStyles.secondaryButton,
            pressed && sharedStyles.secondaryButtonPressed,
            busy && sharedStyles.primaryButtonDisabled,
          ]}
        >
          {busy ? (
            <ActivityIndicator color={colors.text} />
          ) : (
            <Text style={styles.cancelText}>Cancelar reserva</Text>
          )}
        </Pressable>
      );
    }

    if (item.can_reserve) {
      return (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Reservar ${item.title}`}
          disabled={busy}
          onPress={() => handleReserve(item)}
          style={({ pressed }) => [
            sharedStyles.primaryButton,
            pressed && sharedStyles.primaryButtonPressed,
            busy && sharedStyles.primaryButtonDisabled,
          ]}
        >
          {busy ? (
            <ActivityIndicator color={colors.accentText} />
          ) : (
            <Text style={sharedStyles.primaryButtonText}>
              {item.spots_left > 0 ? "Reservar lugar" : "Unirme a la lista de espera"}
            </Text>
          )}
        </Pressable>
      );
    }

    return (
      <View style={styles.blockedBox}>
        <Text style={styles.blockedText}>
          {blockedReasonLabel(item.blocked_reason) ?? "No disponible para reservar"}
        </Text>
      </View>
    );
  }

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
        <Text style={sharedStyles.label}>Próximos 14 días</Text>
        <Text style={sharedStyles.title}>Clases</Text>
        <Text style={sharedStyles.body}>
          Reserva tu lugar desde la app. Si la clase está llena, puedes entrar a
          la lista de espera cuando esté disponible.
        </Text>
      </View>

      {error ? (
        <View style={styles.errorBanner}>
          <Text style={sharedStyles.error}>{error}</Text>
        </View>
      ) : null}

      {loading && !page ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.accent} />
          <Text style={sharedStyles.body}>Cargando clases…</Text>
        </View>
      ) : null}

      {page && page.items.length === 0 ? (
        <View style={sharedStyles.card}>
          <Text style={sharedStyles.body}>
            No hay clases programadas en los próximos días. Vuelve a revisar más
            tarde.
          </Text>
        </View>
      ) : null}

      {page?.items.map((item) => (
        <View key={item.id} style={[sharedStyles.card, styles.classCard]}>
          <View style={styles.classHeader}>
            <View style={styles.classHeading}>
              <Text style={styles.classDate}>{formatDateTime(item.starts_at)}</Text>
              <Text style={styles.classTitle}>{item.title}</Text>
            </View>
            {item.reservation ? (
              <View style={styles.pill}>
                <Text style={styles.pillText}>
                  {reservationStatusLabel(item.reservation.status)}
                </Text>
              </View>
            ) : null}
          </View>

          <Text style={sharedStyles.body}>
            {[item.class_type_name, item.room_name, item.instructor_name]
              .filter(Boolean)
              .join(" · ")}
          </Text>

          <View style={styles.metaRow}>
            <Text style={sharedStyles.hint}>
              {item.spots_left > 0
                ? `${item.spots_left} de ${item.capacity} lugares disponibles`
                : "Clase llena"}
            </Text>
            {item.waitlist_count > 0 ? (
              <Text style={sharedStyles.hint}>
                Lista de espera: {item.waitlist_count}
              </Text>
            ) : null}
          </View>

          {item.reservation?.status === "waitlist" &&
          item.reservation.waitlist_position !== null ? (
            <Text style={styles.waitlist}>
              Estás en la lista de espera, posición{" "}
              {item.reservation.waitlist_position}.
            </Text>
          ) : null}

          {item.notes ? <Text style={sharedStyles.hint}>{item.notes}</Text> : null}

          {item.access_type === "premium" ? (
            <Text style={styles.premium}>
              Clase premium · {formatMoney(item.extra_price_cents)} adicionales
            </Text>
          ) : null}

          {renderAction(item)}

          {item.reservation ? (
            <Text style={sharedStyles.hint}>
              Cancelación sin penalización hasta {item.cancel_window_hours} h antes
              del inicio.
            </Text>
          ) : null}
        </View>
      ))}

      {page && page.pages > 1 ? (
        <Text style={sharedStyles.hint}>
          Mostrando las primeras {page.items.length} clases de {page.total}.
        </Text>
      ) : null}

      <Text style={sharedStyles.hint}>
        Desliza hacia abajo para actualizar la cartelera.
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
  loading: {
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.xl,
  },
  classCard: {
    gap: spacing.sm,
  },
  classHeader: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: spacing.sm,
    justifyContent: "space-between",
  },
  classHeading: {
    flex: 1,
    gap: spacing.xs,
  },
  classDate: {
    color: colors.accent,
    fontSize: 13,
    fontWeight: "800",
    letterSpacing: 0.6,
    textTransform: "uppercase",
  },
  classTitle: {
    color: colors.text,
    fontSize: 21,
    fontWeight: "800",
  },
  pill: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  pillText: {
    color: colors.text,
    fontSize: 12,
    fontWeight: "700",
  },
  metaRow: {
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md,
    justifyContent: "space-between",
  },
  waitlist: {
    color: colors.warning,
    fontSize: 14,
    fontWeight: "700",
  },
  premium: {
    color: colors.info,
    fontSize: 14,
    fontWeight: "700",
  },
  cancelText: {
    color: colors.danger,
    fontSize: 15,
    fontWeight: "700",
  },
  blockedBox: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.md,
    paddingVertical: 13,
  },
  blockedText: {
    color: colors.textMuted,
    fontSize: 14,
    fontWeight: "700",
    textAlign: "center",
  },
});
