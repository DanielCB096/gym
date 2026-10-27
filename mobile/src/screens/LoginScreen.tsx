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

import { requestLoginCode } from "../api";
import { describeError } from "../errors";
import { colors, sharedStyles, spacing } from "../theme";

type Props = {
  initialError: string | null;
  notice: string | null;
  onCodeRequested: (email: string, previewCode: string | null) => void;
};

export function LoginScreen({ initialError, notice, onCodeRequested }: Props) {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(initialError);
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    const trimmed = email.trim();
    if (!trimmed.includes("@")) {
      setError("Escribe el correo con el que te registraste en el gimnasio.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await requestLoginCode(trimmed);
      onCodeRequested(trimmed, result.preview_code);
    } catch (submitError) {
      setError(describeError(submitError));
    } finally {
      setSubmitting(false);
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
        <View style={styles.brandRow}>
          <View style={styles.brandDot} />
          <Text style={styles.brand}>CENTRO FIT</Text>
        </View>

        <View style={styles.hero}>
          <Text style={sharedStyles.title}>Tu gimnasio,{"\n"}siempre contigo.</Text>
          <Text style={sharedStyles.body}>
            Entra con el correo que registraste en recepción. Te enviamos un
            código de 6 dígitos, sin contraseñas.
          </Text>
        </View>

        <View style={styles.form}>
          <Text style={sharedStyles.label}>Correo electrónico</Text>
          <TextInput
            value={email}
            onChangeText={setEmail}
            placeholder="tu@correo.com"
            placeholderTextColor={colors.textMuted}
            style={sharedStyles.input}
            autoCapitalize="none"
            autoComplete="email"
            autoCorrect={false}
            keyboardType="email-address"
            textContentType="emailAddress"
            returnKeyType="send"
            onSubmitEditing={submit}
            editable={!submitting}
            accessibilityLabel="Correo electrónico"
          />

          {notice ? <Text style={styles.notice}>{notice}</Text> : null}
          {error ? (
            <Text style={sharedStyles.error} accessibilityLiveRegion="polite">
              {error}
            </Text>
          ) : null}

          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Enviar código de acceso"
            disabled={submitting}
            onPress={submit}
            style={({ pressed }) => [
              sharedStyles.primaryButton,
              pressed && sharedStyles.primaryButtonPressed,
              submitting && sharedStyles.primaryButtonDisabled,
            ]}
          >
            {submitting ? (
              <ActivityIndicator color={colors.accentText} />
            ) : (
              <Text style={sharedStyles.primaryButtonText}>Enviar código</Text>
            )}
          </Pressable>
        </View>

        <Text style={sharedStyles.hint}>
          ¿No tienes acceso o cambiaste de correo? Pide en recepción que
          actualicen tus datos.
        </Text>
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
  brandRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  brandDot: {
    backgroundColor: colors.accent,
    borderRadius: 6,
    height: 12,
    width: 12,
  },
  brand: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "800",
    letterSpacing: 2.4,
  },
  hero: {
    gap: spacing.md,
  },
  form: {
    gap: spacing.md,
    marginTop: spacing.sm,
  },
  notice: {
    color: colors.info,
    fontSize: 14,
    lineHeight: 20,
  },
});
