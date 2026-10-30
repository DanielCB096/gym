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

import { ApiError, getMemberPhysio } from "../api";
import { describeError } from "../errors";
import {
  formatDate,
  formatDateTime,
  physioPackStatusLabel,
  physioStatusLabel,
} from "../format";
import { colors, radius, sharedStyles, spacing } from "../theme";
import type { MemberPhysioAppointment, MemberPhysioOverview } from "../types";

type Props = {
  token: string;
  onBack: () => void;
  onSessionExpired: () => void;
};

export function PhysioScreen({ token, onBack, onSessionExpired }: Props) {
  const [overview, setOverview] = useState<MemberPhysioOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (mode: "initial" | "refresh") => {
      setLoading(mode === "initial");
      setRefreshing(mode === "refresh");
      try {
        const next = await getMemberPhysio(token);
        setOverview(next);
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

  const next = overview?.next_appointment ?? null;

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
        <Text style={sharedStyles.label}>El consultorio</Text>
        <Text style={sharedStyles.title}>Fisioterapia</Text>
        <Text style={sharedStyles.body}>
          Consulta cuántas sesiones te quedan y cuándo es tu próxima cita. La
          agenda la lleva recepción.
        </Text>
      </View>

      {error ? (
        <View style={styles.errorBanner}>
          <Text style={sharedStyles.error}>{error}</Text>
        </View>
      ) : null}

      {loading && !overview ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.accent} />
          <Text style={sharedStyles.body}>Cargando tu fisioterapia…</Text>
        </View>
      ) : null}

      {overview ? (
        <>
          <View style={[sharedStyles.card, styles.nextCard]}>
            <Text style={sharedStyles.label}>Próxima cita</Text>
            {next ? (
              <AppointmentBody appointment={next} />
            ) : (
              <Text style={sharedStyles.body}>
                No tienes citas próximas. Si necesitas una, pídela en recepción.
              </Text>
            )}
          </View>

          <View style={sharedStyles.card}>
            <Text style={styles.sectionTitle}>Tus paquetes</Text>
            {overview.packs.length === 0 ? (
              <Text style={sharedStyles.body}>
                Aún no tienes un paquete de fisioterapia. Puedes comprarlo en
                recepción.
              </Text>
            ) : (
              overview.packs.map((pack) => (
                <View key={pack.id} style={styles.row}>
                  <View style={styles.rowHeading}>
                    <Text style={styles.rowTitle}>{pack.offer_name}</Text>
                    <View style={styles.pill}>
                      <Text style={styles.pillText}>
                        {physioPackStatusLabel(pack.status)}
                      </Text>
                    </View>
                  </View>
                  <Text style={styles.sessions}>
                    {pack.remaining_sessions} de {pack.sessions_total} sesiones
                  </Text>
                  <Text style={sharedStyles.hint}>
                    {pack.service_name} · vence el {formatDate(pack.valid_until)}
                  </Text>
                  {pack.status === "expired" ? (
                    <Text style={sharedStyles.hint}>
                      Este paquete ya venció; sus sesiones no se pueden usar.
                    </Text>
                  ) : null}
                  {pack.status === "exhausted" ? (
                    <Text style={sharedStyles.hint}>
                      Ya usaste todas las sesiones de este paquete.
                    </Text>
                  ) : null}
                </View>
              ))
            )}
          </View>

          <View style={sharedStyles.card}>
            <Text style={styles.sectionTitle}>Historial de citas</Text>
            {overview.history.length === 0 ? (
              <Text style={sharedStyles.body}>
                Todavía no hay citas en tu historial.
              </Text>
            ) : (
              overview.history.map((appointment) => (
                <View key={appointment.id} style={styles.row}>
                  <View style={styles.rowHeading}>
                    <Text style={styles.rowTitle}>{appointment.service_name}</Text>
                    <View style={styles.pill}>
                      <Text style={styles.pillText}>
                        {physioStatusLabel(appointment.status)}
                      </Text>
                    </View>
                  </View>
                  <Text style={sharedStyles.body}>
                    {formatDateTime(appointment.starts_at)} ·{" "}
                    {appointment.therapist_name}
                  </Text>
                  <Text style={sharedStyles.hint}>
                    {appointment.covered_by_pack
                      ? "Cubierta por tu paquete"
                      : "Sesión suelta"}
                    {appointment.room ? ` · ${appointment.room}` : ""}
                  </Text>
                </View>
              ))
            )}
          </View>
        </>
      ) : null}

      <Text style={sharedStyles.hint}>
        Para mover o cancelar tu cita, acude a recepción. Desliza hacia abajo para
        actualizar.
      </Text>
    </ScrollView>
  );
}

function AppointmentBody({ appointment }: { appointment: MemberPhysioAppointment }) {
  return (
    <>
      <Text style={styles.nextService}>{appointment.service_name}</Text>
      <Text style={styles.nextWhen}>{formatDateTime(appointment.starts_at)}</Text>
      <Text style={sharedStyles.body}>
        Con {appointment.therapist_name}
        {appointment.room ? ` · ${appointment.room}` : ""}
      </Text>
      <Text style={sharedStyles.hint}>
        {appointment.covered_by_pack
          ? "Se descontará una sesión de tu paquete."
          : "Se cobra la sesión suelta al llegar."}{" "}
        Llega 10 minutos antes.
      </Text>
    </>
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
  nextCard: {
    borderColor: "rgba(34, 197, 94, 0.5)",
  },
  nextService: {
    color: colors.text,
    fontSize: 24,
    fontWeight: "800",
  },
  nextWhen: {
    color: colors.accent,
    fontSize: 18,
    fontWeight: "700",
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: "800",
  },
  row: {
    borderTopColor: colors.border,
    borderTopWidth: 1,
    gap: 2,
    paddingTop: spacing.sm,
  },
  rowHeading: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
    justifyContent: "space-between",
  },
  rowTitle: {
    color: colors.text,
    flex: 1,
    fontSize: 16,
    fontWeight: "800",
  },
  sessions: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "700",
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
