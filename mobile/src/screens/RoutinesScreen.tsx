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
  cancelMemberGoal,
  createMemberGoal,
  getMemberProgress,
  getMemberRoutines,
  recordMemberMeasurement,
} from "../api";
import { describeError } from "../errors";
import {
  assignmentStatusLabel,
  formatDay,
  formatMetric,
  goalDirectionLabel,
  goalMetricLabel,
  goalMetricUnit,
  goalStatusLabel,
} from "../format";
import { colors, radius, sharedStyles, spacing } from "../theme";
import type { MemberProgress, MemberRoutineList } from "../types";

type Props = {
  token: string;
  onBack: () => void;
  onOpenRoutine: (assignmentId: string) => void;
  onOpenPhotos: () => void;
  onSessionExpired: () => void;
};

type ParsedMeasurement = {
  value: number | null;
  error: string | null;
};

const GOAL_METRICS = ["weight_kg", "waist_cm", "chest_cm", "body_fat_percent"] as const;
type GoalMetric = (typeof GOAL_METRICS)[number];
const GOAL_DIRECTIONS = ["decrease", "increase"] as const;
type GoalDirection = (typeof GOAL_DIRECTIONS)[number];

function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function isIsoDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    return false;
  }
  const date = new Date(`${value}T00:00:00`);
  return (
    !Number.isNaN(date.getTime()) &&
    date.getFullYear() === Number(match[1]) &&
    date.getMonth() + 1 === Number(match[2]) &&
    date.getDate() === Number(match[3])
  );
}

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

export function RoutinesScreen({
  token,
  onBack,
  onOpenRoutine,
  onOpenPhotos,
  onSessionExpired,
}: Props) {
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
  const [goalMetric, setGoalMetric] = useState<GoalMetric>("weight_kg");
  const [goalDirection, setGoalDirection] = useState<GoalDirection>("decrease");
  const [goalTarget, setGoalTarget] = useState("");
  const [goalTargetDate, setGoalTargetDate] = useState("");
  const [goalNotes, setGoalNotes] = useState("");
  const [goalSaving, setGoalSaving] = useState(false);
  const [goalError, setGoalError] = useState<string | null>(null);
  const [goalSuccess, setGoalSuccess] = useState<string | null>(null);
  const [confirmGoalId, setConfirmGoalId] = useState<string | null>(null);
  const [cancellingGoalId, setCancellingGoalId] = useState<string | null>(null);

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

  const submitGoal = async () => {
    const limit = goalMetric === "body_fat_percent" ? 100 : 1000;
    const parsed = parseMeasurement(goalTarget, "El objetivo", limit);
    if (parsed.error) {
      setGoalError(parsed.error);
      return;
    }
    if (parsed.value === null) {
      setGoalError("Escribe el objetivo de la meta.");
      return;
    }
    const targetDate = goalTargetDate.trim();
    if (targetDate !== "") {
      if (!isIsoDate(targetDate)) {
        setGoalError("Escribe la fecha objetivo con el formato AAAA-MM-DD.");
        return;
      }
      if (targetDate < todayIso()) {
        setGoalError("La fecha objetivo no puede ser anterior a hoy.");
        return;
      }
    }

    setGoalSaving(true);
    setGoalError(null);
    setGoalSuccess(null);
    try {
      await createMemberGoal(token, {
        metric: goalMetric,
        direction: goalDirection,
        target_value: parsed.value,
        target_date: targetDate === "" ? null : targetDate,
        notes: goalNotes.trim() === "" ? null : goalNotes.trim(),
      });
      setGoalTarget("");
      setGoalTargetDate("");
      setGoalNotes("");
      setGoalSuccess("Meta guardada. Tu avance se actualiza con cada medición.");
      await load("refresh");
    } catch (saveError) {
      if (saveError instanceof ApiError && saveError.status === 401) {
        onSessionExpired();
        return;
      }
      setGoalError(describeError(saveError));
    } finally {
      setGoalSaving(false);
    }
  };

  const cancelGoal = async (goalId: string) => {
    setCancellingGoalId(goalId);
    setGoalError(null);
    setGoalSuccess(null);
    try {
      await cancelMemberGoal(token, goalId);
      setConfirmGoalId(null);
      setGoalSuccess("Meta cancelada. Puedes crear otra cuando quieras.");
      await load("refresh");
    } catch (cancelError) {
      if (cancelError instanceof ApiError && cancelError.status === 401) {
        onSessionExpired();
        return;
      }
      setGoalError(describeError(cancelError));
    } finally {
      setCancellingGoalId(null);
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

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Abrir fotos de progreso"
        onPress={onOpenPhotos}
        style={({ pressed }) => [sharedStyles.card, styles.linkCard, pressed && styles.linkCardPressed]}
      >
        <View style={styles.linkCardText}>
          <Text style={styles.sectionTitle}>Fotos de progreso</Text>
          <Text style={sharedStyles.hint}>
            Toma o elige fotos de frente, perfil y espalda para comparar tu avance.
          </Text>
        </View>
        <Text style={styles.linkCardArrow}>→</Text>
      </Pressable>

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
          <Text style={sharedStyles.hint}>
            Crea una meta por medida. La línea base es tu última medición y el
            avance se calcula contra ella.
          </Text>
          <Text style={styles.fieldLabel}>Medida</Text>
          <View style={styles.choiceRow}>
            {GOAL_METRICS.map((metric) => (
              <Pressable
                key={metric}
                accessibilityRole="button"
                accessibilityState={{ selected: goalMetric === metric }}
                onPress={() => setGoalMetric(metric)}
                style={[styles.choice, goalMetric === metric && styles.choiceSelected]}
              >
                <Text
                  style={[
                    styles.choiceText,
                    goalMetric === metric && styles.choiceTextSelected,
                  ]}
                >
                  {goalMetricLabel(metric)}
                </Text>
              </Pressable>
            ))}
          </View>
          <Text style={styles.fieldLabel}>Dirección</Text>
          <View style={styles.choiceRow}>
            {GOAL_DIRECTIONS.map((direction) => (
              <Pressable
                key={direction}
                accessibilityRole="button"
                accessibilityState={{ selected: goalDirection === direction }}
                onPress={() => setGoalDirection(direction)}
                style={[
                  styles.choice,
                  goalDirection === direction && styles.choiceSelected,
                ]}
              >
                <Text
                  style={[
                    styles.choiceText,
                    goalDirection === direction && styles.choiceTextSelected,
                  ]}
                >
                  {goalDirectionLabel(direction)}
                </Text>
              </Pressable>
            ))}
          </View>
          <View style={styles.fieldRow}>
            <View style={styles.fieldColumn}>
              <Text style={styles.fieldLabel}>
                Objetivo ({goalMetricUnit(goalMetric)})
              </Text>
              <TextInput
                accessibilityLabel="Objetivo de la meta"
                keyboardType="decimal-pad"
                maxLength={6}
                onChangeText={setGoalTarget}
                placeholder={goalMetric === "body_fat_percent" ? "20" : "68"}
                placeholderTextColor={colors.textMuted}
                style={sharedStyles.input}
                value={goalTarget}
              />
            </View>
            <View style={styles.fieldColumn}>
              <Text style={styles.fieldLabel}>Fecha objetivo</Text>
              <TextInput
                accessibilityLabel="Fecha objetivo de la meta"
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="numbers-and-punctuation"
                maxLength={10}
                onChangeText={setGoalTargetDate}
                placeholder="Opcional"
                placeholderTextColor={colors.textMuted}
                style={sharedStyles.input}
                value={goalTargetDate}
              />
            </View>
          </View>
          <Text style={styles.fieldLabel}>Nota (opcional)</Text>
          <TextInput
            accessibilityLabel="Nota de la meta"
            maxLength={300}
            multiline
            numberOfLines={2}
            onChangeText={setGoalNotes}
            placeholder="Ej. Bajar para el verano"
            placeholderTextColor={colors.textMuted}
            style={[sharedStyles.input, styles.notesInput]}
            value={goalNotes}
          />
          {goalError ? <Text style={sharedStyles.error}>{goalError}</Text> : null}
          {goalSuccess ? <Text style={styles.success}>{goalSuccess}</Text> : null}
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Guardar meta"
            disabled={goalSaving}
            onPress={() => void submitGoal()}
            style={({ pressed }) => [
              sharedStyles.primaryButton,
              pressed && !goalSaving && sharedStyles.primaryButtonPressed,
              goalSaving && sharedStyles.primaryButtonDisabled,
            ]}
          >
            <Text style={sharedStyles.primaryButtonText}>
              {goalSaving ? "Guardando…" : "Guardar meta"}
            </Text>
          </Pressable>
          {progress.goals.length === 0 ? (
            <Text style={sharedStyles.body}>
              Aún no tienes metas registradas.
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
                  Meta: {goalDirectionLabel(goal.direction).toLowerCase()} a{" "}
                  {formatMetric(goal.metric, goal.target_value)} · actual{" "}
                  {formatMetric(goal.metric, goal.current_value)}
                  {goal.progress_percent !== null ? ` · ${goal.progress_percent}%` : ""}
                </Text>
                {goal.target_date ? (
                  <Text style={sharedStyles.hint}>
                    Fecha objetivo: {formatDay(goal.target_date)}.
                  </Text>
                ) : null}
                <Text style={sharedStyles.hint}>
                  {goal.origin === "app"
                    ? "Creada desde tu app"
                    : "Creada por el personal"}
                </Text>
                {goal.status === "active" && goal.origin === "app" ? (
                  confirmGoalId === goal.id ? (
                    <View style={styles.goalActions}>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel="Confirmar cancelación de la meta"
                        disabled={cancellingGoalId === goal.id}
                        onPress={() => void cancelGoal(goal.id)}
                        hitSlop={8}
                      >
                        <Text style={styles.goalCancelText}>
                          {cancellingGoalId === goal.id
                            ? "Cancelando…"
                            : "Sí, cancelar meta"}
                        </Text>
                      </Pressable>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel="Conservar la meta"
                        onPress={() => setConfirmGoalId(null)}
                        hitSlop={8}
                      >
                        <Text style={sharedStyles.hint}>Conservar meta</Text>
                      </Pressable>
                    </View>
                  ) : (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={`Cancelar meta de ${goalMetricLabel(goal.metric)}`}
                      onPress={() => setConfirmGoalId(goal.id)}
                      hitSlop={8}
                    >
                      <Text style={styles.goalCancelText}>Cancelar meta</Text>
                    </Pressable>
                  )
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
  linkCard: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.md,
  },
  linkCardPressed: {
    backgroundColor: colors.surfaceMuted,
  },
  linkCardText: {
    flex: 1,
    gap: spacing.xs,
  },
  linkCardArrow: {
    color: colors.accent,
    fontSize: 22,
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
  choiceRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.xs,
  },
  choice: {
    backgroundColor: colors.surfaceMuted,
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  choiceSelected: {
    backgroundColor: colors.accent,
    borderColor: colors.accent,
  },
  choiceText: {
    color: colors.textMuted,
    fontSize: 13,
    fontWeight: "700",
  },
  choiceTextSelected: {
    color: colors.accentText,
  },
  goalActions: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.md,
  },
  goalCancelText: {
    color: colors.danger,
    fontSize: 13,
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
