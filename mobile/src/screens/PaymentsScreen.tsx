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

import { ApiError, getMemberAccount, getMemberPayments } from "../api";
import { describeError } from "../errors";
import {
  formatDate,
  formatDateTime,
  formatDay,
  formatMoney,
  formatSignedMoney,
  paymentMethodLabel,
} from "../format";
import { colors, radius, sharedStyles, spacing } from "../theme";
import type { MemberAccount, MemberPaymentPage } from "../types";

type Props = {
  token: string;
  onBack: () => void;
  onSessionExpired: () => void;
};

export function PaymentsScreen({ token, onBack, onSessionExpired }: Props) {
  const [payments, setPayments] = useState<MemberPaymentPage | null>(null);
  const [account, setAccount] = useState<MemberAccount | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (mode: "initial" | "refresh") => {
      setLoading(mode === "initial");
      setRefreshing(mode === "refresh");
      try {
        const [nextPayments, nextAccount] = await Promise.all([
          getMemberPayments(token),
          getMemberAccount(token),
        ]);
        setPayments(nextPayments);
        setAccount(nextAccount);
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

  const balance = account?.balance_cents ?? 0;

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
        <Text style={sharedStyles.label}>Tu cuenta</Text>
        <Text style={sharedStyles.title}>Pagos y estado de cuenta</Text>
        <Text style={sharedStyles.body}>
          Consulta tus pagos de membresía y los movimientos de tu cuenta del
          gimnasio.
        </Text>
      </View>

      {error ? (
        <View style={styles.errorBanner}>
          <Text style={sharedStyles.error}>{error}</Text>
        </View>
      ) : null}

      {loading && !account ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.accent} />
          <Text style={sharedStyles.body}>Cargando tus pagos…</Text>
        </View>
      ) : null}

      {account ? (
        <View style={sharedStyles.card}>
          <Text style={sharedStyles.label}>Saldo de cuenta</Text>
          <Text
            style={[
              styles.balance,
              balance > 0 ? styles.balanceDue : styles.balanceOk,
            ]}
          >
            {formatMoney(balance)}
          </Text>
          <Text style={sharedStyles.hint}>
            {balance > 0
              ? "Puedes liquidarlo en recepción."
              : balance < 0
                ? "Tienes saldo a favor."
                : "No tienes cargos pendientes."}
          </Text>
          <View style={styles.statsRow}>
            <View style={styles.stat}>
              <Text style={styles.statValue}>{account.charges_count}</Text>
              <Text style={styles.statLabel}>Cargos</Text>
            </View>
            <View style={styles.stat}>
              <Text style={styles.statValue}>{account.payments_count}</Text>
              <Text style={styles.statLabel}>Abonos</Text>
            </View>
            <View style={styles.stat}>
              <Text style={styles.statValue}>
                {formatMoney(payments?.total_paid_cents ?? 0)}
              </Text>
              <Text style={styles.statLabel}>Pagado en membresías</Text>
            </View>
          </View>
          <Text style={sharedStyles.hint}>Corte al {formatDay(account.as_of)}.</Text>
        </View>
      ) : null}

      {payments ? (
        <View style={sharedStyles.card}>
          <Text style={styles.sectionTitle}>Pagos de membresía</Text>
          {payments.items.length === 0 ? (
            <Text style={sharedStyles.body}>
              Aún no hay pagos registrados en tu cuenta.
            </Text>
          ) : (
            payments.items.map((payment) => (
              <View key={payment.id} style={styles.row}>
                <View style={styles.rowHeading}>
                  <Text style={styles.rowAmount}>{formatMoney(payment.amount_cents)}</Text>
                  <View style={styles.pill}>
                    <Text style={styles.pillText}>{paymentMethodLabel(payment.method)}</Text>
                  </View>
                </View>
                <Text style={sharedStyles.body}>
                  {[
                    payment.plan_name,
                    formatDateTime(payment.paid_at),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </Text>
                {payment.period_starts_at && payment.period_ends_at ? (
                  <Text style={sharedStyles.hint}>
                    Periodo: {formatDate(payment.period_starts_at)} —{" "}
                    {formatDate(payment.period_ends_at)}
                  </Text>
                ) : null}
                {payment.note ? (
                  <Text style={sharedStyles.hint}>{payment.note}</Text>
                ) : null}
              </View>
            ))
          )}
        </View>
      ) : null}

      {account ? (
        <View style={sharedStyles.card}>
          <Text style={styles.sectionTitle}>Movimientos de cuenta</Text>
          {account.entries.length === 0 ? (
            <Text style={sharedStyles.body}>
              No tienes movimientos en tu cuenta del gimnasio.
            </Text>
          ) : (
            account.entries.map((entry, index) => (
              <View key={`${entry.kind}-${entry.reference}-${index}`} style={styles.row}>
                <View style={styles.rowHeading}>
                  <Text style={styles.rowTitle}>{entry.description}</Text>
                  <Text
                    style={[
                      styles.rowAmount,
                      entry.amount_cents > 0 ? styles.amountCharge : styles.amountCredit,
                    ]}
                  >
                    {formatSignedMoney(entry.amount_cents)}
                  </Text>
                </View>
                <Text style={sharedStyles.hint}>
                  {[
                    formatDateTime(entry.occurred_at),
                    entry.reference,
                    entry.method ? paymentMethodLabel(entry.method) : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </Text>
                <Text style={sharedStyles.hint}>
                  Saldo después del movimiento: {formatMoney(entry.balance_cents)}
                </Text>
              </View>
            ))
          )}
          {account.entries_total > account.entries.length ? (
            <Text style={sharedStyles.hint}>
              Mostrando los últimos {account.entries.length} de{" "}
              {account.entries_total} movimientos.
            </Text>
          ) : null}
        </View>
      ) : null}

      <Text style={sharedStyles.hint}>
        Los cobros y abonos se registran en recepción. Si no reconoces un cargo,
        contacta al gimnasio. Desliza hacia abajo para actualizar.
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
  balance: {
    fontSize: 34,
    fontWeight: "800",
  },
  balanceDue: {
    color: colors.warning,
  },
  balanceOk: {
    color: colors.text,
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
    fontSize: 17,
    fontWeight: "800",
  },
  statLabel: {
    color: colors.textMuted,
    fontSize: 12,
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
    fontSize: 15,
    fontWeight: "700",
  },
  rowAmount: {
    color: colors.text,
    fontSize: 16,
    fontWeight: "800",
  },
  amountCharge: {
    color: colors.danger,
  },
  amountCredit: {
    color: colors.accent,
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
