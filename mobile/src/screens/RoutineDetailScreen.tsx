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

import { ApiError, getMemberRoutine, logMemberWorkout } from "../api";
import { describeError } from "../errors";
import { assignmentStatusLabel, formatDay } from "../format";
import { colors, radius, sharedStyles, spacing } from "../theme";
import type { MemberRoutineDetail, MemberWorkoutSet, MemberWorkoutSetInput } from "../types";

type Props = {
  token: string;
  assignmentId: string;
  onBack: () => void;
  onSessionExpired: () => void;
};

type SetDraft = {
  key: string;
  exerciseId: string;
  setNumber: number;
  reps: string;
  weight: string;
};

const MAX_DRAFT_SETS = 60;
const MAX_DRAFT_SETS_PER_EXERCISE = 20;

function groupedSetLines(sets: MemberWorkoutSet[]): { name: string; detail: string }[] {
  const groups: { name: string; detail: string }[] = [];
  for (const item of sets) {
    const weight = item.weight_kg !== null ? ` × ${item.weight_kg} kg` : "";
    const label = `${item.reps}${weight}`;
    const last = groups[groups.length - 1];
    if (last && last.name === item.exercise_name) {
      last.detail = `${last.detail} · ${label}`;
    } else {
      groups.push({ name: item.exercise_name, detail: label });
    }
  }
  return groups;
}

function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function validIsoDate(value: string): boolean {
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

export function RoutineDetailScreen({ token, assignmentId, onBack, onSessionExpired }: Props) {
  const [detail, setDetail] = useState<MemberRoutineDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workoutDate, setWorkoutDate] = useState(todayIso);
  const [duration, setDuration] = useState("");
  const [effort, setEffort] = useState("");
  const [workoutNotes, setWorkoutNotes] = useState("");
  const [setDrafts, setSetDrafts] = useState<SetDraft[]>([]);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  const load = useCallback(
    async (mode: "initial" | "refresh") => {
      setLoading(mode === "initial");
      setRefreshing(mode === "refresh");
      try {
        const next = await getMemberRoutine(token, assignmentId);
        setDetail(next);
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
    [assignmentId, onSessionExpired, token],
  );

  useEffect(() => {
    void load("initial");
  }, [load]);

  const addSetDraft = (line: MemberRoutineDetail["plan"][number]) => {
    const existing = setDrafts.filter((draft) => draft.exerciseId === line.exercise_id);
    if (setDrafts.length >= MAX_DRAFT_SETS) {
      setFormError("Un entrenamiento admite hasta 60 series.");
      return;
    }
    if (existing.length >= MAX_DRAFT_SETS_PER_EXERCISE) {
      setFormError("Cada ejercicio admite hasta 20 series por entrenamiento.");
      return;
    }
    const nextNumber = existing.reduce((max, draft) => Math.max(max, draft.setNumber), 0) + 1;
    setFormError(null);
    setSetDrafts([
      ...setDrafts,
      {
        key: `${line.exercise_id}-${nextNumber}-${setDrafts.length}`,
        exerciseId: line.exercise_id,
        setNumber: nextNumber,
        reps: /^\d+$/.test(line.reps) ? line.reps : "",
        weight: "",
      },
    ]);
  };

  const updateSetDraft = (key: string, field: "reps" | "weight", value: string) => {
    setSetDrafts((current) =>
      current.map((draft) => (draft.key === key ? { ...draft, [field]: value } : draft)),
    );
  };

  const removeSetDraft = (key: string) => {
    setSetDrafts((current) => current.filter((draft) => draft.key !== key));
  };

  const submitWorkout = async () => {
    const performed = workoutDate.trim();
    if (!validIsoDate(performed)) {
      setFormError("Escribe la fecha con el formato AAAA-MM-DD.");
      return;
    }
    if (performed > todayIso()) {
      setFormError("No puedes registrar un entrenamiento en el futuro.");
      return;
    }
    if (detail && performed < detail.assignment.start_date) {
      setFormError("El entrenamiento es anterior al inicio de la rutina.");
      return;
    }
    const parsedDuration = duration.trim();
    if (parsedDuration !== "" && !/^\d{1,3}$/.test(parsedDuration)) {
      setFormError("La duración debe ser un número entero de minutos.");
      return;
    }
    if (parsedDuration !== "" && Number(parsedDuration) > 600) {
      setFormError("La duración no puede pasar de 600 minutos.");
      return;
    }
    const parsedEffort = effort.trim();
    if (parsedEffort !== "" && !/^(10|[1-9])$/.test(parsedEffort)) {
      setFormError("El esfuerzo debe ser un número entero del 1 al 10.");
      return;
    }
    const setsPayload: MemberWorkoutSetInput[] = [];
    for (const draft of setDrafts) {
      const repsText = draft.reps.trim();
      if (!/^\d{1,3}$/.test(repsText) || Number(repsText) < 1 || Number(repsText) > 100) {
        setFormError(
          `Serie ${draft.setNumber}: las repeticiones deben ser un entero entre 1 y 100.`,
        );
        return;
      }
      const weightText = draft.weight.trim().replace(",", ".");
      if (
        weightText !== "" &&
        (!/^\d{1,4}(\.\d{1,2})?$/.test(weightText) || Number(weightText) > 1000)
      ) {
        setFormError(`Serie ${draft.setNumber}: el peso debe estar entre 0 y 1000 kg.`);
        return;
      }
      setsPayload.push({
        exercise_id: draft.exerciseId,
        set_number: draft.setNumber,
        reps: Number(repsText),
        weight_kg: weightText === "" ? null : Number(weightText),
      });
    }

    setSaving(true);
    setFormError(null);
    setFormSuccess(null);
    try {
      await logMemberWorkout(token, assignmentId, {
        performed_at: performed,
        duration_minutes: parsedDuration === "" ? null : Number(parsedDuration),
        perceived_effort: parsedEffort === "" ? null : Number(parsedEffort),
        notes: workoutNotes.trim() === "" ? null : workoutNotes.trim(),
        sets: setsPayload,
      });
      setWorkoutDate(todayIso());
      setDuration("");
      setEffort("");
      setWorkoutNotes("");
      setSetDrafts([]);
      setFormSuccess("Entrenamiento registrado. Tu entrenador lo revisará pronto.");
      await load("refresh");
    } catch (saveError) {
      if (saveError instanceof ApiError && saveError.status === 401) {
        onSessionExpired();
        return;
      }
      setFormError(describeError(saveError));
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
        accessibilityLabel="Volver a rutinas"
        onPress={onBack}
        style={styles.back}
        hitSlop={12}
      >
        <Text style={styles.backText}>← Rutinas</Text>
      </Pressable>

      {error ? (
        <View style={styles.errorBanner}>
          <Text style={sharedStyles.error}>{error}</Text>
        </View>
      ) : null}

      {loading && !detail ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.accent} />
          <Text style={sharedStyles.body}>Cargando la rutina…</Text>
        </View>
      ) : null}

      {detail ? (
        <>
          <View style={styles.hero}>
            <View style={styles.heroHeading}>
              <Text style={sharedStyles.title}>{detail.assignment.routine_name}</Text>
              <View style={styles.pill}>
                <Text style={styles.pillText}>
                  {assignmentStatusLabel(detail.assignment.status)}
                </Text>
              </View>
            </View>
            <Text style={sharedStyles.body}>
              {[
                detail.assignment.trainer_name
                  ? `Entrenador: ${detail.assignment.trainer_name}`
                  : null,
                `Versión ${detail.assignment.routine_version}`,
                `${formatDay(detail.assignment.start_date)}${
                  detail.assignment.end_date
                    ? ` – ${formatDay(detail.assignment.end_date)}`
                    : ""
                }`,
              ]
                .filter(Boolean)
                .join(" · ")}
            </Text>
            {detail.objective ? (
              <Text style={styles.objective}>Objetivo: {detail.objective}</Text>
            ) : null}
            {detail.assignment.notes ? (
              <Text style={sharedStyles.body}>{detail.assignment.notes}</Text>
            ) : null}
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Ejercicios</Text>
            {detail.plan.length === 0 ? (
              <View style={sharedStyles.card}>
                <Text style={sharedStyles.body}>La rutina no tiene ejercicios.</Text>
              </View>
            ) : (
              detail.plan.map((line) => (
                <View key={line.id} style={[sharedStyles.card, styles.lineCard]}>
                  <View style={styles.lineHeading}>
                    <Text style={styles.linePosition}>{line.position}</Text>
                    <Text style={styles.lineName}>{line.exercise_name}</Text>
                  </View>
                  <Text style={sharedStyles.body}>
                    {line.muscle_group} · {line.category}
                  </Text>
                  <Text style={styles.lineDose}>
                    {line.sets} series × {/^\d+$/.test(line.reps) ? `${line.reps} repeticiones` : line.reps}
                    {line.rest_seconds !== null ? ` · ${line.rest_seconds} s de descanso` : ""}
                  </Text>
                  {line.load_note ? (
                    <Text style={styles.lineNote}>Carga: {line.load_note}</Text>
                  ) : null}
                  {line.notes ? <Text style={sharedStyles.hint}>{line.notes}</Text> : null}
                </View>
              ))
            )}
          </View>

          {detail.assignment.status === "active" ? (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Registrar entrenamiento</Text>
              <View style={[sharedStyles.card, styles.formCard]}>
                <Text style={sharedStyles.hint}>
                  Anota la sesión al terminarla, hoy o un día anterior desde el
                  inicio de la rutina. Tu entrenador la revisará después.
                </Text>
                <Text style={styles.fieldLabel}>Fecha (AAAA-MM-DD)</Text>
                <TextInput
                  accessibilityLabel="Fecha del entrenamiento"
                  autoCapitalize="none"
                  autoCorrect={false}
                  keyboardType="numbers-and-punctuation"
                  onChangeText={setWorkoutDate}
                  placeholder="2026-10-27"
                  placeholderTextColor={colors.textMuted}
                  style={sharedStyles.input}
                  value={workoutDate}
                />
                <View style={styles.fieldRow}>
                  <View style={styles.fieldColumn}>
                    <Text style={styles.fieldLabel}>Duración (min)</Text>
                    <TextInput
                      accessibilityLabel="Duración en minutos"
                      keyboardType="number-pad"
                      maxLength={3}
                      onChangeText={setDuration}
                      placeholder="45"
                      placeholderTextColor={colors.textMuted}
                      style={sharedStyles.input}
                      value={duration}
                    />
                  </View>
                  <View style={styles.fieldColumn}>
                    <Text style={styles.fieldLabel}>Esfuerzo (1-10)</Text>
                    <TextInput
                      accessibilityLabel="Esfuerzo percibido"
                      keyboardType="number-pad"
                      maxLength={2}
                      onChangeText={setEffort}
                      placeholder="7"
                      placeholderTextColor={colors.textMuted}
                      style={sharedStyles.input}
                      value={effort}
                    />
                  </View>
                </View>
                <Text style={styles.fieldLabel}>Notas (opcional)</Text>
                <TextInput
                  accessibilityLabel="Notas del entrenamiento"
                  maxLength={2000}
                  multiline
                  numberOfLines={3}
                  onChangeText={setWorkoutNotes}
                  placeholder="¿Cómo te sentiste? ¿Subiste peso en algún ejercicio?"
                  placeholderTextColor={colors.textMuted}
                  style={[sharedStyles.input, styles.notesInput]}
                  value={workoutNotes}
                />
                <View style={styles.setEditor}>
                  <Text style={styles.fieldLabel}>Series (opcional)</Text>
                  <Text style={sharedStyles.hint}>
                    Anota las repeticiones y el peso de cada serie. Se guardan junto
                    con el entrenamiento para que tu entrenador las revise.
                  </Text>
                  {detail.plan.map((line) => {
                    const drafts = setDrafts.filter(
                      (draft) => draft.exerciseId === line.exercise_id,
                    );
                    return (
                      <View key={line.id} style={styles.setExercise}>
                        <Text style={styles.setExerciseName}>{line.exercise_name}</Text>
                        {drafts.map((draft) => (
                          <View key={draft.key} style={styles.setRow}>
                            <Text style={styles.setNumber}>S{draft.setNumber}</Text>
                            <TextInput
                              accessibilityLabel={`Repeticiones de la serie ${draft.setNumber} de ${line.exercise_name}`}
                              keyboardType="number-pad"
                              maxLength={3}
                              onChangeText={(value) =>
                                updateSetDraft(draft.key, "reps", value)
                              }
                              placeholder="Reps"
                              placeholderTextColor={colors.textMuted}
                              style={[sharedStyles.input, styles.setInput]}
                              value={draft.reps}
                            />
                            <TextInput
                              accessibilityLabel={`Peso de la serie ${draft.setNumber} de ${line.exercise_name}`}
                              keyboardType="decimal-pad"
                              maxLength={6}
                              onChangeText={(value) =>
                                updateSetDraft(draft.key, "weight", value)
                              }
                              placeholder="kg"
                              placeholderTextColor={colors.textMuted}
                              style={[sharedStyles.input, styles.setInput]}
                              value={draft.weight}
                            />
                            <Pressable
                              accessibilityRole="button"
                              accessibilityLabel={`Quitar serie ${draft.setNumber} de ${line.exercise_name}`}
                              hitSlop={8}
                              onPress={() => removeSetDraft(draft.key)}
                              style={styles.removeSet}
                            >
                              <Text style={styles.removeSetText}>Quitar</Text>
                            </Pressable>
                          </View>
                        ))}
                        <Pressable
                          accessibilityRole="button"
                          accessibilityLabel={`Añadir serie de ${line.exercise_name}`}
                          hitSlop={8}
                          onPress={() => addSetDraft(line)}
                          style={styles.addSet}
                        >
                          <Text style={styles.addSetText}>+ Añadir serie</Text>
                        </Pressable>
                      </View>
                    );
                  })}
                </View>
                {formError ? <Text style={sharedStyles.error}>{formError}</Text> : null}
                {formSuccess ? <Text style={styles.success}>{formSuccess}</Text> : null}
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Guardar entrenamiento"
                  disabled={saving}
                  onPress={() => void submitWorkout()}
                  style={({ pressed }) => [
                    sharedStyles.primaryButton,
                    pressed && !saving && sharedStyles.primaryButtonPressed,
                    saving && sharedStyles.primaryButtonDisabled,
                  ]}
                >
                  <Text style={sharedStyles.primaryButtonText}>
                    {saving ? "Guardando…" : "Guardar entrenamiento"}
                  </Text>
                </Pressable>
              </View>
            </View>
          ) : null}

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Entrenamientos registrados</Text>
            {detail.workouts.length === 0 ? (
              <View style={sharedStyles.card}>
                <Text style={sharedStyles.body}>
                  Aún no hay entrenamientos registrados para esta rutina.
                </Text>
              </View>
            ) : (
              detail.workouts.map((workout) => (
                <View key={workout.id} style={[sharedStyles.card, styles.workoutCard]}>
                  <Text style={styles.workoutDate}>{formatDay(workout.performed_at)}</Text>
                  <Text style={sharedStyles.body}>
                    {[
                      workout.duration_minutes !== null
                        ? `${workout.duration_minutes} min`
                        : null,
                      workout.perceived_effort !== null
                        ? `Esfuerzo ${workout.perceived_effort}/10`
                        : null,
                      workout.origin === "app" ? "Desde tu app" : "Desde recepción",
                      workout.status === "reviewed" ? "Revisado" : "Por revisar",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </Text>
                  {workout.notes ? (
                    <Text style={sharedStyles.hint}>{workout.notes}</Text>
                  ) : null}
                  {workout.sets.length > 0 ? (
                    <View style={styles.workoutSets}>
                      {groupedSetLines(workout.sets).map((group) => (
                        <Text key={group.name} style={styles.workoutSetLine}>
                          <Text style={styles.workoutSetName}>{group.name}: </Text>
                          {group.detail}
                        </Text>
                      ))}
                    </View>
                  ) : null}
                </View>
              ))
            )}
          </View>

          <Text style={sharedStyles.hint}>
            Tu entrenador revisa los entrenamientos que registres desde la app. Si
            necesitas corregir uno, acude a recepción.
          </Text>
        </>
      ) : null}
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
  hero: {
    gap: spacing.sm,
  },
  heroHeading: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
    justifyContent: "space-between",
  },
  objective: {
    color: colors.info,
    fontSize: 15,
    fontWeight: "700",
    lineHeight: 21,
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
  section: {
    gap: spacing.sm,
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: "800",
  },
  lineCard: {
    gap: spacing.xs,
  },
  lineHeading: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  linePosition: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: 999,
    color: colors.accent,
    fontSize: 13,
    fontWeight: "800",
    minWidth: 28,
    paddingVertical: 2,
    textAlign: "center",
  },
  lineName: {
    color: colors.text,
    flex: 1,
    fontSize: 18,
    fontWeight: "700",
  },
  lineDose: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "600",
  },
  lineNote: {
    color: colors.accent,
    fontSize: 14,
    fontWeight: "700",
  },
  formCard: {
    gap: spacing.sm,
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
    minHeight: 88,
    textAlignVertical: "top",
  },
  setEditor: {
    borderTopColor: colors.border,
    borderTopWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    paddingTop: spacing.sm,
  },
  setExercise: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.md,
    gap: spacing.xs,
    padding: spacing.sm,
  },
  setExerciseName: {
    color: colors.text,
    fontSize: 14,
    fontWeight: "700",
  },
  setRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.xs,
  },
  setNumber: {
    color: colors.accent,
    fontSize: 13,
    fontWeight: "800",
    width: 26,
  },
  setInput: {
    flex: 1,
    minHeight: 42,
    paddingVertical: spacing.xs,
  },
  removeSet: {
    paddingHorizontal: spacing.xs,
  },
  removeSetText: {
    color: colors.danger,
    fontSize: 12,
    fontWeight: "700",
  },
  addSet: {
    alignSelf: "flex-start",
    paddingVertical: spacing.xs,
  },
  addSetText: {
    color: colors.accent,
    fontSize: 13,
    fontWeight: "700",
  },
  workoutSets: {
    gap: 2,
  },
  workoutSetLine: {
    color: colors.textMuted,
    fontSize: 13,
    lineHeight: 19,
  },
  workoutSetName: {
    color: colors.text,
    fontWeight: "700",
  },
  success: {
    color: colors.accent,
    fontSize: 14,
    fontWeight: "700",
    lineHeight: 20,
  },
  workoutCard: {
    gap: spacing.xs,
  },
  workoutDate: {
    color: colors.accent,
    fontSize: 13,
    fontWeight: "800",
    letterSpacing: 0.4,
    textTransform: "uppercase",
  },
});
