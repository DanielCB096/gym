import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { ApiError, getMemberAccessCodeStatus, requestMemberAccessCode } from "../api";
import { describeError } from "../errors";
import { colors, radius, sharedStyles, spacing } from "../theme";
import type { MemberAccessCode } from "../types";

type Props = {
  token: string;
  onBack: () => void;
  onSessionExpired: () => void;
};

const STATUS_POLL_MS = 4000;

function secondsUntil(expiresAt: string): number {
  const target = new Date(expiresAt).getTime();
  if (Number.isNaN(target)) {
    return 0;
  }
  return Math.max(0, Math.ceil((target - Date.now()) / 1000));
}

function groupCode(code: string): string {
  return code.length === 6 ? `${code.slice(0, 3)} ${code.slice(3)}` : code;
}

function formatCountdown(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${remainder.toString().padStart(2, "0")}`;
}

export function AccessCodeScreen({ token, onBack, onSessionExpired }: Props) {
  const [accessCode, setAccessCode] = useState<MemberAccessCode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [consumed, setConsumed] = useState(false);
  const [today, setToday] = useState<{ entries: number; limit: number | null } | null>(
    null,
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setConsumed(false);
    setToday(null);
    try {
      const next = await requestMemberAccessCode(token);
      setAccessCode(next);
      setRemaining(secondsUntil(next.expires_at));
    } catch (loadError) {
      if (loadError instanceof ApiError && loadError.status === 401) {
        onSessionExpired();
        return;
      }
      setAccessCode(null);
      setRemaining(0);
      setError(describeError(loadError));
    } finally {
      setLoading(false);
    }
  }, [onSessionExpired, token]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!accessCode) {
      return;
    }
    const tick = () => setRemaining(secondsUntil(accessCode.expires_at));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [accessCode]);

  const expired = accessCode !== null && remaining <= 0;

  useEffect(() => {
    if (!accessCode || consumed || expired) {
      return;
    }
    let cancelled = false;
    const check = async () => {
      try {
        const status = await getMemberAccessCodeStatus(token);
        if (cancelled) {
          return;
        }
        setToday({ entries: status.entries_today, limit: status.daily_entry_limit });
        if (status.status === "consumed") {
          setConsumed(true);
        } else if (status.status === "expired") {
          setRemaining(0);
        }
      } catch (checkError) {
        if (checkError instanceof ApiError && checkError.status === 401) {
          onSessionExpired();
        }
        // Cualquier otro fallo se ignora: el código sigue visible y el
        // siguiente sondeo vuelve a intentarlo.
      }
    };
    void check();
    const timer = setInterval(() => void check(), STATUS_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [accessCode, consumed, expired, onSessionExpired, token]);

  const unusable = consumed || expired;

  return (
    <ScrollView
      style={sharedStyles.screen}
      contentContainerStyle={styles.container}
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
        <Text style={sharedStyles.label}>Acceso al club</Text>
        <Text style={sharedStyles.title}>Tu código de entrada</Text>
        <Text style={sharedStyles.body}>
          Muestra este código en la tablet de recepción. Caduca en cinco minutos
          y solo se puede usar una vez.
        </Text>
      </View>

      {error ? (
        <View style={styles.errorBanner}>
          <Text style={sharedStyles.error}>{error}</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Reintentar"
            onPress={() => void load()}
            style={({ pressed }) => [
              sharedStyles.secondaryButton,
              styles.retry,
              pressed && sharedStyles.secondaryButtonPressed,
            ]}
          >
            <Text style={sharedStyles.secondaryButtonText}>Reintentar</Text>
          </Pressable>
        </View>
      ) : null}

      {loading && !accessCode ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.accent} />
          <Text style={sharedStyles.body}>Generando tu código…</Text>
        </View>
      ) : null}

      {accessCode ? (
        <View style={[sharedStyles.card, styles.codeCard]}>
          <Text style={styles.codeLabel}>
            {consumed ? "Código usado" : expired ? "Código vencido" : "Código vigente"}
          </Text>
          <Text
            accessibilityLabel={`Código de acceso ${accessCode.code}`}
            style={[styles.code, unusable && styles.codeExpired]}
          >
            {groupCode(accessCode.code)}
          </Text>
          <Text style={unusable ? styles.expiredHint : styles.countdown}>
            {consumed
              ? "Recepción ya registró este código. Si no entraste, genera otro o pasa a recepción."
              : expired
                ? "Pide uno nuevo para registrar tu entrada."
                : `Vence en ${formatCountdown(remaining)}`}
          </Text>
          {unusable ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Generar nuevo código"
              onPress={() => void load()}
              style={({ pressed }) => [
                sharedStyles.primaryButton,
                pressed && sharedStyles.primaryButtonPressed,
              ]}
            >
              <Text style={sharedStyles.primaryButtonText}>Generar nuevo código</Text>
            </Pressable>
          ) : (
            <Text style={sharedStyles.hint}>
              Dilo o muéstralo en recepción para que validen tu membresía.
            </Text>
          )}
        </View>
      ) : null}

      {today ? (
        <View style={[sharedStyles.card, styles.todayCard]}>
          <Text style={styles.todayLabel}>Entradas hoy</Text>
          <Text style={styles.todayValue}>
            {today.limit === null
              ? today.entries
              : `${today.entries} de ${today.limit}`}
          </Text>
          <Text
            style={
              today.limit !== null && today.entries >= today.limit
                ? styles.todayExhausted
                : sharedStyles.hint
            }
          >
            {today.limit === null
              ? "Tu plan no tiene límite diario de entradas."
              : today.entries >= today.limit
                ? "Ya usaste tus entradas de hoy: la tablet no registrará otra hasta mañana."
                : today.limit - today.entries === 1
                  ? "Te queda 1 entrada hoy."
                  : `Te quedan ${today.limit - today.entries} entradas hoy.`}
          </Text>
        </View>
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
  hero: {
    gap: spacing.xs,
    paddingTop: spacing.sm,
  },
  errorBanner: {
    backgroundColor: "rgba(248, 113, 113, 0.12)",
    borderRadius: radius.md,
    gap: spacing.sm,
    padding: spacing.md,
  },
  retry: {
    alignSelf: "flex-start",
    paddingHorizontal: spacing.lg,
  },
  loading: {
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.xl,
  },
  codeCard: {
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.xl,
  },
  codeLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1.1,
    textTransform: "uppercase",
  },
  code: {
    color: colors.text,
    fontSize: 54,
    fontWeight: "800",
    letterSpacing: 8,
  },
  codeExpired: {
    color: colors.textMuted,
  },
  countdown: {
    color: colors.accent,
    fontSize: 20,
    fontWeight: "800",
  },
  expiredHint: {
    color: colors.warning,
    fontSize: 15,
    fontWeight: "600",
    textAlign: "center",
  },
  todayCard: {
    gap: spacing.xs,
  },
  todayLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1.1,
    textTransform: "uppercase",
  },
  todayValue: {
    color: colors.text,
    fontSize: 26,
    fontWeight: "800",
  },
  todayExhausted: {
    color: colors.warning,
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 19,
  },
});
