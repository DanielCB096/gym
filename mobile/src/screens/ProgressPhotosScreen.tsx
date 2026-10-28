import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import * as ImagePicker from "expo-image-picker";

import {
  ApiError,
  deleteMemberProgressPhoto,
  getMemberProgressPhotos,
  memberProgressPhotoUri,
  uploadMemberProgressPhoto,
  type PhotoUploadAsset,
} from "../api";
import { describeError } from "../errors";
import { formatDay, formatFileSize, photoAngleLabel } from "../format";
import { colors, radius, sharedStyles, spacing } from "../theme";
import type { MemberProgressPhoto, MemberProgressPhotoList, ProgressPhotoAngle } from "../types";

type Props = {
  token: string;
  onBack: () => void;
  onSessionExpired: () => void;
};

const ANGLES: ProgressPhotoAngle[] = ["front", "side", "back", "other"];
const MAX_PHOTO_BYTES = 8 * 1024 * 1024;
const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];

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

export function ProgressPhotosScreen({ token, onBack, onSessionExpired }: Props) {
  const [photos, setPhotos] = useState<MemberProgressPhotoList | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<PhotoUploadAsset | null>(null);
  const [angle, setAngle] = useState<ProgressPhotoAngle>("front");
  const [capturedAt, setCapturedAt] = useState(todayIso());
  const [notes, setNotes] = useState("");
  const [consent, setConsent] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [viewing, setViewing] = useState<MemberProgressPhoto | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = useCallback(
    async (mode: "initial" | "refresh" | "silent") => {
      if (mode === "initial") {
        setLoading(true);
      }
      if (mode === "refresh") {
        setRefreshing(true);
      }
      try {
        const next = await getMemberProgressPhotos(token);
        setPhotos(next);
        setError(null);
      } catch (loadError) {
        if (loadError instanceof ApiError && loadError.status === 401) {
          onSessionExpired();
          return;
        }
        setError(describeError(loadError));
      } finally {
        if (mode === "initial") {
          setLoading(false);
        }
        if (mode === "refresh") {
          setRefreshing(false);
        }
      }
    },
    [onSessionExpired, token],
  );

  useEffect(() => {
    void load("initial");
  }, [load]);

  async function pickPhoto(source: "camera" | "library") {
    setUploadError(null);
    setSuccess(null);
    try {
      const permission =
        source === "camera"
          ? await ImagePicker.requestCameraPermissionsAsync()
          : await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        setUploadError(
          source === "camera"
            ? "Necesitamos acceso a la cámara para tomar la foto."
            : "Necesitamos acceso a tus fotos para elegir una.",
        );
        return;
      }
      const options: ImagePicker.ImagePickerOptions = {
        mediaTypes: ["images"],
        quality: 0.8,
      };
      const result =
        source === "camera"
          ? await ImagePicker.launchCameraAsync(options)
          : await ImagePicker.launchImageLibraryAsync(options);
      if (result.canceled) {
        return;
      }
      const asset = result.assets[0];
      if (!asset) {
        return;
      }
      if (asset.fileSize !== undefined && asset.fileSize > MAX_PHOTO_BYTES) {
        setUploadError("La imagen no puede superar 8 MB.");
        return;
      }
      const type = (asset.mimeType ?? "image/jpeg").toLowerCase();
      if (!ACCEPTED_TYPES.includes(type)) {
        setUploadError("La foto debe ser JPEG, PNG o WebP.");
        return;
      }
      setSelected({
        uri: asset.uri,
        name: asset.fileName?.trim() || `progreso-${Date.now()}.jpg`,
        type,
      });
    } catch (pickError) {
      setUploadError(describeError(pickError));
    }
  }

  async function submit() {
    if (!selected) {
      setUploadError("Elige o toma una foto primero.");
      return;
    }
    if (photos !== null && !photos.consent_recorded && !consent) {
      setUploadError("Marca la autorización para guardar tus fotos.");
      return;
    }
    const date = capturedAt.trim();
    if (!isIsoDate(date)) {
      setUploadError("Escribe la fecha con el formato AAAA-MM-DD.");
      return;
    }

    setUploading(true);
    setUploadError(null);
    setSuccess(null);
    try {
      await uploadMemberProgressPhoto(token, selected, {
        angle,
        captured_at: new Date(`${date}T12:00:00`).toISOString(),
        notes: notes.trim() === "" ? null : notes.trim(),
        consent,
      });
      setSelected(null);
      setNotes("");
      setCapturedAt(todayIso());
      setConsent(false);
      setSuccess("Foto guardada. Solo tú y el personal de Rutinas pueden verla.");
      await load("silent");
    } catch (submitError) {
      if (submitError instanceof ApiError && submitError.status === 401) {
        onSessionExpired();
        return;
      }
      setUploadError(describeError(submitError));
    } finally {
      setUploading(false);
    }
  }

  async function openPhoto(photo: MemberProgressPhoto) {
    setConfirmDeleteId(null);
    setViewing(photo);
    try {
      // Links expire in ten minutes; refresh this one before showing it.
      const next = await getMemberProgressPhotos(token);
      setPhotos(next);
      const fresh = next.items.find((item) => item.id === photo.id);
      if (fresh) {
        setViewing(fresh);
      }
    } catch (openError) {
      if (openError instanceof ApiError && openError.status === 401) {
        onSessionExpired();
      }
    }
  }

  async function removePhoto(photo: MemberProgressPhoto) {
    setDeletingId(photo.id);
    setUploadError(null);
    try {
      await deleteMemberProgressPhoto(token, photo.id);
      setViewing(null);
      setConfirmDeleteId(null);
      setPhotos((current) =>
        current === null
          ? current
          : { ...current, items: current.items.filter((item) => item.id !== photo.id) },
      );
      setSuccess("Foto eliminada.");
      await load("silent");
    } catch (deleteError) {
      if (deleteError instanceof ApiError && deleteError.status === 401) {
        onSessionExpired();
        return;
      }
      setUploadError(describeError(deleteError));
    } finally {
      setDeletingId(null);
    }
  }

  const items = photos?.items ?? [];

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

      <View style={styles.hero}>
        <Text style={sharedStyles.label}>Tu progreso</Text>
        <Text style={sharedStyles.title}>Fotos de progreso</Text>
        <Text style={sharedStyles.body}>
          Guarda una foto de frente, perfil o espalda para comparar tu avance con
          el tiempo.
        </Text>
      </View>

      {error ? (
        <View style={styles.errorBanner}>
          <Text style={sharedStyles.error}>{error}</Text>
        </View>
      ) : null}

      {loading && photos === null ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.accent} />
          <Text style={sharedStyles.body}>Cargando tus fotos…</Text>
        </View>
      ) : null}

      <View style={sharedStyles.card}>
        <Text style={styles.sectionTitle}>Subir una foto</Text>
        {photos === null ? null : !photos.consent_recorded ? (
          <>
            <Text style={sharedStyles.hint}>
              Tus fotos se guardan en el servidor del club y solo las ven tú y el
              personal de Rutinas. Puedes eliminarlas cuando quieras.
            </Text>
            <Pressable
              accessibilityRole="checkbox"
              accessibilityState={{ checked: consent }}
              accessibilityLabel="Autorizo el uso de mis fotos de progreso"
              onPress={() => {
                setConsent((value) => !value);
                setUploadError(null);
              }}
              style={styles.checkboxRow}
            >
              <View style={[styles.checkbox, consent && styles.checkboxChecked]}>
                {consent ? <Text style={styles.checkboxMark}>✓</Text> : null}
              </View>
              <Text style={styles.checkboxLabel}>
                Autorizo el registro y resguardo de mis fotos de progreso.
              </Text>
            </Pressable>
          </>
        ) : (
          <Text style={sharedStyles.hint}>Consentimiento registrado.</Text>
        )}

        <View style={styles.pickRow}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Tomar foto"
            onPress={() => void pickPhoto("camera")}
            style={({ pressed }) => [
              sharedStyles.secondaryButton,
              styles.pickButton,
              pressed && sharedStyles.secondaryButtonPressed,
            ]}
          >
            <Text style={sharedStyles.secondaryButtonText}>Tomar foto</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Elegir de la galería"
            onPress={() => void pickPhoto("library")}
            style={({ pressed }) => [
              sharedStyles.secondaryButton,
              styles.pickButton,
              pressed && sharedStyles.secondaryButtonPressed,
            ]}
          >
            <Text style={sharedStyles.secondaryButtonText}>Elegir de galería</Text>
          </Pressable>
        </View>

        {selected ? (
          <View style={styles.previewRow}>
            <Image source={{ uri: selected.uri }} style={styles.preview} resizeMode="cover" />
            <View style={styles.previewMeta}>
              <Text style={styles.previewName} numberOfLines={1}>
                {selected.name}
              </Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Quitar la foto elegida"
                onPress={() => setSelected(null)}
                hitSlop={8}
              >
                <Text style={styles.removeText}>Quitar</Text>
              </Pressable>
            </View>
          </View>
        ) : null}

        <Text style={styles.fieldLabel}>Ángulo</Text>
        <View style={styles.chipRow}>
          {ANGLES.map((option) => (
            <Pressable
              key={option}
              accessibilityRole="button"
              accessibilityState={{ selected: angle === option }}
              accessibilityLabel={photoAngleLabel(option)}
              onPress={() => setAngle(option)}
              style={[styles.chip, angle === option && styles.chipActive]}
            >
              <Text style={[styles.chipText, angle === option && styles.chipTextActive]}>
                {photoAngleLabel(option)}
              </Text>
            </Pressable>
          ))}
        </View>

        <Text style={styles.fieldLabel}>Fecha de la foto</Text>
        <TextInput
          accessibilityLabel="Fecha de la foto"
          autoCapitalize="none"
          maxLength={10}
          onChangeText={setCapturedAt}
          placeholder="AAAA-MM-DD"
          placeholderTextColor={colors.textMuted}
          style={sharedStyles.input}
          value={capturedAt}
        />

        <Text style={styles.fieldLabel}>Nota (opcional)</Text>
        <TextInput
          accessibilityLabel="Nota de la foto"
          maxLength={300}
          multiline
          numberOfLines={2}
          onChangeText={setNotes}
          placeholder="Después de cuatro semanas de rutina"
          placeholderTextColor={colors.textMuted}
          style={[sharedStyles.input, styles.notesInput]}
          value={notes}
        />

        {uploadError ? <Text style={sharedStyles.error}>{uploadError}</Text> : null}
        {success ? <Text style={styles.success}>{success}</Text> : null}

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Guardar foto"
          disabled={uploading}
          onPress={() => void submit()}
          style={({ pressed }) => [
            sharedStyles.primaryButton,
            pressed && !uploading && sharedStyles.primaryButtonPressed,
            uploading && sharedStyles.primaryButtonDisabled,
          ]}
        >
          {uploading ? (
            <ActivityIndicator color={colors.accentText} />
          ) : (
            <Text style={sharedStyles.primaryButtonText}>Guardar foto</Text>
          )}
        </Pressable>
      </View>

      <View style={sharedStyles.card}>
        <Text style={styles.sectionTitle}>Tus fotos ({items.length})</Text>
        {items.length === 0 ? (
          <Text style={sharedStyles.hint}>
            Aún no tienes fotos. Toma la primera para empezar a comparar tu
            progreso.
          </Text>
        ) : (
          <View style={styles.grid}>
            {items.map((photo) => (
              <Pressable
                key={photo.id}
                accessibilityRole="button"
                accessibilityLabel={`Ver foto ${photoAngleLabel(photo.angle)} del ${formatDay(photo.captured_at)}`}
                onPress={() => void openPhoto(photo)}
                style={styles.tile}
              >
                {photo.file_path ? (
                  <Image
                    source={{ uri: memberProgressPhotoUri(photo.file_path) }}
                    style={styles.tileImage}
                    resizeMode="cover"
                  />
                ) : (
                  <View style={[styles.tileImage, styles.tilePlaceholder]}>
                    <Text style={sharedStyles.hint}>Sin imagen</Text>
                  </View>
                )}
                <Text style={styles.tileTitle}>{photoAngleLabel(photo.angle)}</Text>
                <Text style={styles.tileMeta}>
                  {formatDay(photo.captured_at)}
                  {photo.origin === "staff" ? " · Recepción" : ""}
                </Text>
              </Pressable>
            ))}
          </View>
        )}
      </View>

      <Modal
        animationType="fade"
        transparent
        visible={viewing !== null}
        onRequestClose={() => setViewing(null)}
      >
        <View style={styles.viewerBackdrop}>
          <View style={styles.viewerCard}>
            {viewing?.file_path ? (
              <Image
                source={{ uri: memberProgressPhotoUri(viewing.file_path) }}
                style={styles.viewerImage}
                resizeMode="contain"
              />
            ) : null}
            {viewing ? (
              <>
                <Text style={styles.viewerTitle}>
                  {photoAngleLabel(viewing.angle)} · {formatDay(viewing.captured_at)}
                </Text>
                <Text style={sharedStyles.hint}>
                  {formatFileSize(viewing.byte_size)} ·{" "}
                  {viewing.origin === "staff" ? "Subida en recepción" : "Subida desde tu app"}
                </Text>
                {viewing.notes ? <Text style={styles.viewerNotes}>{viewing.notes}</Text> : null}
                <Text style={sharedStyles.hint}>
                  Solo tú y el personal de Rutinas pueden ver esta foto.
                </Text>
                {confirmDeleteId === viewing.id ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Confirmar eliminación de la foto"
                    disabled={deletingId === viewing.id}
                    onPress={() => void removePhoto(viewing)}
                    style={styles.dangerButton}
                  >
                    {deletingId === viewing.id ? (
                      <ActivityIndicator color={colors.text} />
                    ) : (
                      <Text style={styles.dangerButtonText}>Sí, eliminar la foto</Text>
                    )}
                  </Pressable>
                ) : (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Eliminar la foto"
                    onPress={() => setConfirmDeleteId(viewing.id)}
                    style={styles.secondaryDangerButton}
                  >
                    <Text style={styles.secondaryDangerText}>Eliminar foto</Text>
                  </Pressable>
                )}
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Cerrar la foto"
                  onPress={() => {
                    setViewing(null);
                    setConfirmDeleteId(null);
                  }}
                  style={({ pressed }) => [
                    sharedStyles.secondaryButton,
                    pressed && sharedStyles.secondaryButtonPressed,
                  ]}
                >
                  <Text style={sharedStyles.secondaryButtonText}>Cerrar</Text>
                </Pressable>
              </>
            ) : null}
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    padding: spacing.lg,
    paddingBottom: spacing.xl,
    gap: spacing.md,
  },
  back: {
    alignSelf: "flex-start",
    paddingVertical: spacing.xs,
  },
  backText: {
    color: colors.info,
    fontSize: 15,
    fontWeight: "700",
  },
  hero: {
    gap: spacing.sm,
  },
  loading: {
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.lg,
  },
  errorBanner: {
    backgroundColor: "rgba(248, 113, 113, 0.12)",
    borderColor: colors.danger,
    borderRadius: radius.md,
    borderWidth: 1,
    padding: spacing.md,
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: "800",
  },
  checkboxRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  checkbox: {
    alignItems: "center",
    borderColor: colors.border,
    borderRadius: 6,
    borderWidth: 2,
    height: 22,
    justifyContent: "center",
    width: 22,
  },
  checkboxChecked: {
    backgroundColor: colors.accent,
    borderColor: colors.accent,
  },
  checkboxMark: {
    color: colors.accentText,
    fontSize: 14,
    fontWeight: "900",
  },
  checkboxLabel: {
    color: colors.text,
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
  },
  pickRow: {
    flexDirection: "row",
    gap: spacing.sm,
  },
  pickButton: {
    flex: 1,
  },
  previewRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.md,
  },
  preview: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.md,
    height: 64,
    width: 64,
  },
  previewMeta: {
    flex: 1,
    gap: spacing.xs,
  },
  previewName: {
    color: colors.text,
    fontSize: 14,
    fontWeight: "600",
  },
  removeText: {
    color: colors.danger,
    fontSize: 13,
    fontWeight: "700",
  },
  fieldLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1,
    textTransform: "uppercase",
  },
  chipRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  chip: {
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  chipActive: {
    backgroundColor: colors.accent,
    borderColor: colors.accent,
  },
  chipText: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "700",
  },
  chipTextActive: {
    color: colors.accentText,
  },
  notesInput: {
    minHeight: 64,
    textAlignVertical: "top",
  },
  success: {
    color: colors.accent,
    fontSize: 14,
    lineHeight: 20,
  },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md,
  },
  tile: {
    gap: spacing.xs,
    width: "47%",
  },
  tileImage: {
    aspectRatio: 3 / 4,
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.md,
    width: "100%",
  },
  tilePlaceholder: {
    alignItems: "center",
    justifyContent: "center",
  },
  tileTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: "700",
  },
  tileMeta: {
    color: colors.textMuted,
    fontSize: 12,
  },
  viewerBackdrop: {
    backgroundColor: "rgba(2, 6, 23, 0.9)",
    flex: 1,
    justifyContent: "center",
    padding: spacing.lg,
  },
  viewerCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.lg,
    borderWidth: 1,
    gap: spacing.sm,
    padding: spacing.lg,
  },
  viewerImage: {
    aspectRatio: 3 / 4,
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.md,
    width: "100%",
  },
  viewerTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: "800",
  },
  viewerNotes: {
    color: colors.text,
    fontSize: 14,
    lineHeight: 20,
  },
  dangerButton: {
    alignItems: "center",
    backgroundColor: colors.danger,
    borderRadius: radius.md,
    paddingVertical: 13,
  },
  dangerButtonText: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "800",
  },
  secondaryDangerButton: {
    alignItems: "center",
    borderColor: colors.danger,
    borderRadius: radius.md,
    borderWidth: 1,
    paddingVertical: 12,
  },
  secondaryDangerText: {
    color: colors.danger,
    fontSize: 14,
    fontWeight: "700",
  },
});
