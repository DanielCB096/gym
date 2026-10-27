import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  ApiError,
  getMemberProgress,
  getMemberRoutines,
  recordMemberMeasurement,
} from "../api";
import { describeError } from "../errors";
import {
  assignmentStatusLabel,
  formatDay,
  formatMetric,
  goalMetricLabel,
  goalStatusLabel,
} from "../format";
import { colors, radius, sharedStyles, spacing } from "../theme";
import type { MemberProgress, MemberRoutineList } from "../types";

type Props = {
  token: string;
  onBack: () => void;
  onOpenRoutine: (assignmentId: string) => void;
  onSessionExpired: () => void;
};

type ParsedMeasurement = {
  value: number | null;
  error: string | null;
};

function parseMeasurement(
  raw: string,
  label: string,
  max: number,
  allowZero = false,
): ParsedMeasurement {
  const normalized = raw.trim().replace(",", ".");
  if (normalized === "") {
    return { value: null, error: null };
  }
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) {
    return { value: null, error: `${label} debe ser un número válido.` };
  }
  const value = Number(normalized);
  if ((allowZero ? value < 0 : value <= 0) || value > max) {
    return {
      value: null,
      error: allowZero
        ? `${label} debe estar entre 0 y ${max}.`
        : `${label} debe ser mayor que 0 y hasta ${max}.`,
    };
  }
  return { value, error: null };
}

export function RoutinesScreen({ token, onBack, onOpenRoutine, onSessionExpired }: Props) {
  const [routines, setRoutines] = useState<MemberRoutineList | null>(null);
  const [progress, setProgress] = useState<MemberProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [weight, setWeight] = useState("");
  const [waist, setWaist] = useState("");
  const [chest, setChest] = useState("");
  const [bodyFat, setBodyFat] = useState("");
  const [measureNotes, setMeasureNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [measureError, setMeasureError] = useState<string | null>(null);
  const [measureSuccess, setMeasureSuccess] = useState<string | null>(null);

  const load = useCallback(
    async (mode: "initial" | "refresh") => {
      setLoading(mode === "initial");
      setRefreshing(mode === "refresh");
      try {
        const [nextRoutines, nextProgress] = await Promise.all([
          getMemberRoutines(token),
          getMemberProgress(token),
        ]);
        setRoutines(nextRoutines);
        setProgress(nextProgress);
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

  const submitMeasurement = async () => {
    const parsedWeight = parseMeasurement(weight, "El peso", 500);
    const parsedWaist = parseMeasurement(waist, "La cintura", 400);
    const parsedChest = parseMeasurement(chest, "El pecho", 400);
    const parsedFat = parseMeasurement(bodyFat, "La grasa corporal", 100, true);
    const invalid = [parsedWeight, parsedWaist, parsedChest, parsedFat].find(
      (parsed) => parsed.error !== null,
    );
    if (invalid?.error) {
      setMeasureError(invalid.error);
      return;
    }
    if (
      parsedWeight.value === null &&
      parsedWaist.value === null &&
      parsedChest.value === null &&
      parsedFat.value === null
    ) {
      setMeasureError("Captura al menos una medida para guardarla.");
      return;
    }

    setSaving(true);
    setMeasureError(null);
    setMeasureSuccess(null);
    try {
      await recordMemberMeasurement(token, {
        weight_kg: parsedWeight.value ?? undefined,
        waist_cm: parsedWaist.value ?? undefined,
        chest_cm: parsedChest.value ?? undefined,
        body_fat_percent: parsedFat.value ?? undefined,
        notes: measureNotes.trim() === "" ? null : measureNotes.trim(),
      });
      setWeight("");
      setWaist("");
      setChest("");
      setBodyFat("");
      setMeasureNotes("");
      setMeasureSuccess("Medidas registradas. Tu progreso ya está actualizado.");
      await load("refresh");
    } catch (saveError) {
      if (saveError instanceof ApiError && saveError.status === 401) {
        onSessionExpired();
        return;
      }
      setMeasureError(describeError(saveError));
    } finally {
      setSaving(false);
    }
  };

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
        <Text style={sharedStyles.label}>Tu plan</Text>
        <Text style={sharedStyles.title}>Rutinas y progreso</Text>
        <Text style={sharedStyles.body}>
          Consulta la rutina que te asignó tu entrenador, tus medidas y el avance
          de tus metas.
        </Text>
      </View>

      {error ? (
        <View style={styles.errorBanner}>
          <Text style={sharedStyles.error}>{error}</Text>
        </View>
      ) : null}

      {loading && !routines ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.accent} />
          <Text style={sharedStyles.body}>Cargando tu plan…</Text>
        </View>
      ) : null}

      {progress ? (
        <View style={sharedStyles.card}>
          <Text style={styles.sectionTitle}>Resumen</Text>
          <View style={styles.statsRow}>
            <View style={styles.stat}>
              <Text style={styles.statValue}>{progress.workouts_total}</Text>
              <Text style={styles.statLabel}>Entrenamientos</Text>
            </View>
            <View style={styles.stat}>
              <Text style={styles.statValue}>{progress.workouts_last_30_days}</Text>
              <Text style={styles.statLabel}>Últimos 30 días</Text>
            </View>
            <View style={styles.stat}>
              <Text style={styles.statValue}>
                {progress.latest_measurement?.weight_kg ?? "—"}
              </Text>
              <Text style={styles.statLabel}>Peso actual (kg)</Text>
            </View>
          </View>
          <Text style={sharedStyles.hint}>
            {progress.last_workout_at
              ? `Último entrenamiento: ${formatDay(progress.last_workout_at)}.`
              : "Todavía no hay entrenamientos registrados."}
          </Text>
        </View>
      ) : null}

      <View style={sharedStyles.card}>
        <Text style={styles.sectionTitle}>Registrar medidas</Text>
        <Text style={sharedStyles.hint}>
          Captura tu peso o alguna medida. Se guarda con la fecha de hoy y tus
          metas se actualizan al instante.
        </Text>
        <View style={styles.fieldRow}>
          <View style={styles.fieldColumn}>
            <Text style={styles.fieldLabel}>Peso (kg)</Text>
            <TextInput
              accessibilityLabel="Peso en kilogramos"
              keyboardType="decimal-pad"
              maxLength={6}
              onChangeText={setWeight}
              placeholder="68.5"
              placeholderTextColor={colors.textMuted}
              style={sharedStyles.input}
              value={weight}
            />
          </View>
          <View style={styles.fieldColumn}>
            <Text style={styles.fieldLabel}>Cintura (cm)</Text>
            <TextInput
              accessibilityLabel="Cintura en centímetros"
              keyboardType="decimal-pad"
              maxLength={6}
              onChangeText={setWaist}
              placeholder="82"
              placeholderTextColor={colors.textMuted}
              style={sharedStyles.input}
              value={waist}
            />
          </View>
        </View>
        <View style={styles.fieldRow}>
          <View style={styles.fieldColumn}>
            <Text style={styles.fieldLabel}>Pecho (cm)</Text>
            <TextInput
              accessibilityLabel="Pecho en centímetros"
              keyboardType="decimal-pad"
              maxLength={6}
              onChangeText={setChest}
              placeholder="98"
              placeholderTextColor={colors.textMuted}
              style={sharedStyles.input}
              value={chest}
            />
          </View>
          <View style={styles.fieldColumn}>
            <Text style={styles.fieldLabel}>Grasa (%)</Text>
            <TextInput
              accessibilityLabel="Grasa corporal en porcentaje"
              keyboardType="decimal-pad"
              maxLength={5}
              onChangeText={setBodyFat}
              placeholder="22"
              placeholderTextColor={colors.textMuted}
              style={sharedStyles.input}
              value={bodyFat}
            />
          </View>
        </View>
        <Text style={styles.fieldLabel}>Notas (opcional)</Text>
        <TextInput
          accessibilityLabel="Notas de la medición"
          maxLength={300}
          multiline
          numberOfLines={2}
          onChangeText={setMeasureNotes}
          placeholder="Medición en casa por la mañana"
          placeholderTextColor={colors.textMuted}
          style={[sharedStyles.input, styles.notesInput]}
          value={measureNotes}
        />
        {measureError ? <Text style={sharedStyles.error}>{measureError}</Text> : null}
        {measureSuccess ? <Text style={styles.success}>{measureSuccess}</Text> : null}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Guardar medidas"
          disabled={saving}
          onPress={() => void submitMeasurement()}
          style={({ pressed }) => [
            sharedStyles.primaryButton,
            pressed && !saving && sharedStyles.primaryButtonPressed,
            saving && sharedStyles.primaryButtonDisabled,
          ]}
        >
          <Text style={sharedStyles.primaryButtonText}>
            {saving ? "Guardando…" : "Guardar medidas"}
          </Text>
        </Pressable>
      </View>

      {progress ? (
        <View style={sharedStyles.card}>
          <Text style={styles.sectionTitle}>Metas</Text>
          {progress.goals.length === 0 ? (
            <Text style={sharedStyles.body}>
              Aún no tienes metas. Tu entrenador puede crearlas en recepción.
            </Text>
          ) : (
            progress.goals.map((goal) => (
              <View key={goal.id} style={styles.goalRow}>
                <View style={styles.goalHeading}>
                  <Text style={styles.goalTitle}>{goalMetricLabel(goal.metric)}</Text>
                  <View style={styles.pill}>
                    <Text style={styles.pillText}>{goalStatusLabel(goal.status)}</Text>
                  </View>
                </View>
                <Text style={sharedStyles.body}>
                  Meta {formatMetric(goal.metric, goal.target_value)} · actual{" "}
                  {formatMetric(goal.metric, goal.current_value)}
                  {goal.progress_percent !== null ? ` · ${goal.progress_percent}%` : ""}
                </Text>
                {goal.target_date ? (
                  <Text style={sharedStyles.hint}>
                    Fecha objetivo: {formatDay(goal.target_date)}.
                  </Text>
                ) : null}
              </View>
            ))
          )}
        </View>
      ) : null}

      {progress && progress.measurements.length > 0 ? (
        <View style={sharedStyles.card}>
          <Text style={styles.sectionTitle}>Últimas medidas</Text>
          {progress.measurements.slice(0, 3).map((measurement) => (
            <View key={measurement.id} style={styles.measureRow}>
              <Text style={styles.measureDate}>
                {formatDay(measurement.measured_at)}
              </Text>
              <Text style={sharedStyles.body}>
                {[
                  measurement.weight_kg !== null ? `Peso ${measurement.weight_kg} kg` : null,
                  measurement.waist_cm !== null ? `Cintura ${measurement.waist_cm} cm` : null,
                  measurement.chest_cm !== null ? `Pecho ${measurement.chest_cm} cm` : null,
                  measurement.body_fat_percent !== null
                    ? `Grasa ${measurement.body_fat_percent} %`
                    : null,
                  measurement.origin === "app" ? "Desde tu app" : "Desde recepción",
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      <View style={styles.routineSection}>
        <Text style={styles.sectionTitle}>Rutinas asignadas</Text>
        {routines && routines.items.length === 0 ? (
          <View style={sharedStyles.card}>
            <Text style={sharedStyles.body}>
              Todavía no tienes una rutina asignada. Pregunta a tu entrenador en el
              gimnasio.
            </Text>
          </View>
        ) : null}

        {routines?.items.map((assignment) => (
          <Pressable
            key={assignment.id}
            accessibilityRole="button"
            accessibilityLabel={`Ver rutina ${assignment.routine_name}`}
            onPress={() => onOpenRoutine(assignment.id)}
            style={({ pressed }) => [
              sharedStyles.card,
              styles.routineCard,
              pressed && styles.routineCardPressed,
            ]}
          >
            <View style={styles.routineHeading}>
              <Text style={styles.routineTitle}>{assignment.routine_name}</Text>
              <View style={styles.pill}>
                <Text style={styles.pillText}>
                  {assignmentStatusLabel(assignment.status)}
                </Text>
              </View>
            </View>
            <Text style={sharedStyles.body}>
              {[
                assignment.trainer_name ? `Entrenador: ${assignment.trainer_name}` : null,
                assignment.frequency_per_week
                  ? `${assignment.frequency_per_week} días por semana`
                  : null,
                `Desde ${formatDay(assignment.start_date)}`,
              ]
                .filter(Boolean)
                .join(" · ")}
            </Text>
            <Text style={sharedStyles.hint}>
              {assignment.workouts_logged} entrenamientos registrados
              {assignment.last_workout_at
                ? ` · último el ${formatDay(assignment.last_workout_at)}`
                : ""}
            </Text>
            <Text style={styles.openLink}>Ver ejercicios →</Text>
          </Pressable>
        ))}
      </View>

      <Text style={sharedStyles.hint}>
        Desliza hacia abajo para actualizar tus rutinas y tu progreso.
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
  sectionTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: "800",
  },
  fieldLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 0.8,
    textTransform: "uppercase",
  },
  fieldRow: {
    flexDirection: "row",
    gap: spacing.sm,
  },
  fieldColumn: {
    flex: 1,
    gap: spacing.xs,
  },
  notesInput: {
    minHeight: 64,
    textAlignVertical: "top",
  },
  success: {
    color: colors.accent,
    fontSize: 14,
    fontWeight: "700",
    lineHeight: 20,
  },
  statsRow: {
    flexDirection: "row",
    gap: spacing.sm,
  },
  stat: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.md,
    flex: 1,
    gap: 2,
    padding: spacing.md,
  },
  statValue: {
    color: colors.text,
    fontSize: 22,
    fontWeight: "800",
  },
  statLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: "700",
  },
  goalRow: {
    borderTopColor: colors.border,
    borderTopWidth: 1,
    gap: spacing.xs,
    paddingTop: spacing.sm,
  },
  goalHeading: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
    justifyContent: "space-between",
  },
  goalTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: "700",
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
  measureRow: {
    borderTopColor: colors.border,
    borderTopWidth: 1,
    gap: 2,
    paddingTop: spacing.sm,
  },
  measureDate: {
    color: colors.accent,
    fontSize: 13,
    fontWeight: "800",
    letterSpacing: 0.4,
    textTransform: "uppercase",
  },
  routineSection: {
    gap: spacing.sm,
  },
  routineCard: {
    gap: spacing.xs,
  },
  routineCardPressed: {
    backgroundColor: colors.surfaceMuted,
  },
  routineHeading: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
    justifyContent: "space-between",
  },
  routineTitle: {
    color: colors.text,
    flex: 1,
    fontSize: 20,
    fontWeight: "800",
  },
  openLink: {
    color: colors.accent,
    fontSize: 14,
    fontWeight: "800",
  },
});
