import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { requestLoginCode, verifyLoginCode } from "../api";
import { describeError } from "../errors";
import { colors, radius, sharedStyles, spacing } from "../theme";
import type { MemberLoginResult } from "../types";

type Props = {
  email: string;
  previewCode: string | null;
  onBack: () => void;
  onAuthenticated: (result: MemberLoginResult) => Promise<void>;
};

export function CodeScreen({ email, previewCode, onBack, onAuthenticated }: Props) {
  const [code, setCode] = useState(previewCode ?? "");
  const [preview, setPreview] = useState<string | null>(previewCode);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [resending, setResending] = useState(false);

  async function submit() {
    if (code.length !== 6) {
      setError("Escribe los 6 dígitos del código.");
      return;
    }
    setVerifying(true);
    setError(null);
    setNotice(null);
    try {
      const result = await verifyLoginCode(email, code);
      await onAuthenticated(result);
    } catch (verifyError) {
      setError(describeError(verifyError));
    } finally {
      setVerifying(false);
    }
  }

  async function resend() {
    setResending(true);
    setError(null);
    setNotice(null);
    try {
      const result = await requestLoginCode(email);
      setPreview(result.preview_code);
      if (result.preview_code) {
        setCode(result.preview_code);
      }
      setNotice(
        "Si el correo está registrado, enviamos un código nuevo a tu correo.",
      );
    } catch (resendError) {
      setError(describeError(resendError));
    } finally {
      setResending(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={sharedStyles.screen}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Usar otro correo"
          onPress={onBack}
          style={styles.back}
          hitSlop={12}
        >
          <Text style={styles.backText}>← Cambiar correo</Text>
        </Pressable>

        <View style={styles.hero}>
          <Text style={sharedStyles.label}>Paso 2 de 2</Text>
          <Text style={sharedStyles.title}>Revisa tu correo</Text>
          <Text style={sharedStyles.body}>
            Si el correo <Text style={styles.email}>{email}</Text> está
            registrado, enviamos un código de 6 dígitos. Vence en 10 minutos.
          </Text>
        </View>

        <TextInput
          value={code}
          onChangeText={(value) => setCode(value.replace(/\D/g, "").slice(0, 6))}
          placeholder="000000"
          placeholderTextColor={colors.textMuted}
          style={styles.codeInput}
          keyboardType="number-pad"
          textContentType="oneTimeCode"
          autoComplete="one-time-code"
          maxLength={6}
          autoFocus
          editable={!verifying}
          onSubmitEditing={submit}
          accessibilityLabel="Código de 6 dígitos"
        />

        {preview ? (
          <View style={styles.previewBox}>
            <Text style={styles.previewLabel}>VISTA PREVIA LOCAL</Text>
            <Text style={styles.previewCode}>{preview}</Text>
            <Text style={sharedStyles.hint}>
              El modo de vista previa simula el correo; usa este código.
            </Text>
          </View>
        ) : null}

        {notice ? <Text style={styles.notice}>{notice}</Text> : null}
        {error ? (
          <Text style={sharedStyles.error} accessibilityLiveRegion="polite">
            {error}
          </Text>
        ) : null}

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Entrar"
          disabled={verifying}
          onPress={submit}
          style={({ pressed }) => [
            sharedStyles.primaryButton,
            pressed && sharedStyles.primaryButtonPressed,
            verifying && sharedStyles.primaryButtonDisabled,
          ]}
        >
          {verifying ? (
            <ActivityIndicator color={colors.accentText} />
          ) : (
            <Text style={sharedStyles.primaryButtonText}>Entrar</Text>
          )}
        </Pressable>

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Reenviar código"
          disabled={resending || verifying}
          onPress={resend}
          style={({ pressed }) => [
            sharedStyles.secondaryButton,
            pressed && sharedStyles.secondaryButtonPressed,
          ]}
        >
          {resending ? (
            <ActivityIndicator color={colors.text} />
          ) : (
            <Text style={sharedStyles.secondaryButtonText}>Reenviar código</Text>
          )}
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    gap: spacing.lg,
    justifyContent: "center",
    padding: spacing.lg,
    paddingVertical: spacing.xl,
  },
  back: {
    alignSelf: "flex-start",
  },
  backText: {
    color: colors.textMuted,
    fontSize: 14,
    fontWeight: "600",
  },
  hero: {
    gap: spacing.sm,
  },
  email: {
    color: colors.text,
    fontWeight: "700",
  },
  codeInput: {
    backgroundColor: colors.surfaceMuted,
    borderColor: colors.border,
    borderRadius: radius.md,
    borderWidth: 1,
    color: colors.text,
    fontSize: 30,
    fontWeight: "700",
    letterSpacing: 12,
    paddingHorizontal: spacing.md,
    paddingVertical: 16,
    textAlign: "center",
  },
  previewBox: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.md,
    borderWidth: 1,
    gap: spacing.xs,
    padding: spacing.md,
  },
  previewLabel: {
    color: colors.warning,
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 1.2,
  },
  previewCode: {
    color: colors.text,
    fontSize: 22,
    fontWeight: "800",
    letterSpacing: 6,
  },
  notice: {
    color: colors.info,
    fontSize: 14,
    lineHeight: 20,
  },
});
