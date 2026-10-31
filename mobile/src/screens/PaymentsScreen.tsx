import { useCallback, useEffect, useRef, useState } from "react";
import {
  AppState,
  ActivityIndicator,
  Linking,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import {
  ApiError,
  createMemberCheckout,
  getMemberAccount,
  getMemberCheckoutPlans,
  getMemberPayments,
} from "../api";
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
import type {
  MemberAccount,
  MemberCheckoutPlan,
  MemberCheckoutPlanList,
  MemberPaymentPage,
} from "../types";

type Props = {
  token: string;
  onBack: () => void;
  onSessionExpired: () => void;
};

export function PaymentsScreen({ token, onBack, onSessionExpired }: Props) {
  const [payments, setPayments] = useState<MemberPaymentPage | null>(null);
  const [account, setAccount] = useState<MemberAccount | null>(null);
  const [checkoutPlans, setCheckoutPlans] = useState<MemberCheckoutPlanList | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [checkoutNotice, setCheckoutNotice] = useState<string | null>(null);
  const [startingCheckoutPlanId, setStartingCheckoutPlanId] = useState<string | null>(null);
  const [pendingCheckout, setPendingCheckout] = useState<{
    plan: MemberCheckoutPlan;
    idempotencyKey: string;
    checkoutUrl: string | null;
  } | null>(null);
  const checkoutOpenedRef = useRef(false);

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
        try {
          const nextCheckoutPlans = await getMemberCheckoutPlans(token);
          setCheckoutPlans(nextCheckoutPlans);
          setPendingCheckout(
            nextCheckoutPlans.pending_checkout
              ? {
                  plan: nextCheckoutPlans.pending_checkout.plan,
                  idempotencyKey: nextCheckoutPlans.pending_checkout.idempotency_key,
                  checkoutUrl: nextCheckoutPlans.pending_checkout.checkout_url,
                }
              : null,
          );
          setCheckoutError(null);
        } catch (checkoutLoadError) {
          if (checkoutLoadError instanceof ApiError && checkoutLoadError.status === 401) {
            throw checkoutLoadError;
          }
          setCheckoutError(describeError(checkoutLoadError));
        }
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

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (nextState) => {
      if (nextState === "active" && checkoutOpenedRef.current) {
        checkoutOpenedRef.current = false;
        setCheckoutNotice(
          "Regresaste del checkout. El gimnasio confirmará el pago cuando reciba el aviso seguro de Conekta; desliza hacia abajo para actualizar.",
        );
        void load("refresh");
      }
    });
    return () => subscription.remove();
  }, [load]);

  async function openCheckout(plan: MemberCheckoutPlan) {
    if (startingCheckoutPlanId) {
      return;
    }
    setStartingCheckoutPlanId(plan.id);
    setCheckoutError(null);
    setCheckoutNotice(null);
    const existing = pendingCheckout?.plan.id === plan.id ? pendingCheckout : null;
    const checkout = existing ?? {
      plan,
      idempotencyKey: `member-checkout-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      checkoutUrl: null,
    };
    setPendingCheckout(checkout);
    try {
      let checkoutUrl = checkout.checkoutUrl;
      if (!checkoutUrl) {
        const result = await createMemberCheckout(
          token,
          plan.id,
          checkout.idempotencyKey,
        );
        checkoutUrl = result.checkout_url;
        if (!checkoutUrl) {
          throw new Error("Conekta no devolvió un enlace para continuar el pago.");
        }
        setPendingCheckout({ ...checkout, checkoutUrl });
      }
      checkoutOpenedRef.current = true;
      await Linking.openURL(checkoutUrl);
      setCheckoutNotice(
        "Se abrió el checkout seguro de Conekta. La app no recibe ni guarda los datos de tu tarjeta. El pago solo se confirma cuando el gimnasio recibe y valida el aviso de Conekta.",
      );
    } catch (checkoutStartError) {
      checkoutOpenedRef.current = false;
      if (checkoutStartError instanceof ApiError && checkoutStartError.status === 401) {
        onSessionExpired();
        return;
      }
      setCheckoutError(
        checkoutStartError instanceof ApiError && checkoutStartError.status === 503
          ? "El pago en línea no está disponible en este momento. Consulta en recepción."
          : describeError(checkoutStartError),
      );
    } finally {
      setStartingCheckoutPlanId(null);
    }
  }

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
      {checkoutPlans ? (
        <View style={sharedStyles.card}>
          <Text style={styles.sectionTitle}>Inscripción con pago en línea</Text>
          <Text style={sharedStyles.body}>
            Paga una primera membresía con tarjeta en el checkout seguro de Conekta.
            La app nunca recibe ni guarda los datos de tu tarjeta.
          </Text>
          {pendingCheckout ? (
            <View style={styles.checkoutPlan}>
              <Text style={styles.rowTitle}>{pendingCheckout.plan.name}</Text>
              <Text style={sharedStyles.hint}>
                {formatMoney(
                  pendingCheckout.plan.price_cents,
                  pendingCheckout.plan.currency,
                )} ·{" "}
                {pendingCheckout.plan.duration_days} días
              </Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={
                  startingCheckoutPlanId === pendingCheckout.plan.id
                    ? `Abriendo checkout para ${pendingCheckout.plan.name}`
                    : pendingCheckout.checkoutUrl
                      ? `Volver a abrir checkout de ${pendingCheckout.plan.name}`
                      : `Reintentar la creación del checkout de ${pendingCheckout.plan.name}`
                }
                accessibilityState={{ disabled: startingCheckoutPlanId !== null }}
                disabled={startingCheckoutPlanId !== null}
                onPress={() => void openCheckout(pendingCheckout.plan)}
                style={({ pressed }) => [
                  sharedStyles.primaryButton,
                  pressed && startingCheckoutPlanId === null
                    ? sharedStyles.primaryButtonPressed
                    : null,
                  startingCheckoutPlanId !== null
                    ? sharedStyles.primaryButtonDisabled
                    : null,
                ]}
              >
                {startingCheckoutPlanId === pendingCheckout.plan.id ? (
                  <ActivityIndicator color={colors.accentText} />
                ) : (
                  <Text style={sharedStyles.primaryButtonText}>
                    {pendingCheckout.checkoutUrl
                      ? "Volver al checkout"
                      : "Reintentar checkout"}
                  </Text>
                )}
              </Pressable>
            </View>
          ) : !checkoutPlans.checkout_enabled ? (
            <Text style={sharedStyles.hint}>
              El pago en línea no está habilitado en este momento. Consulta en recepción.
            </Text>
          ) : !checkoutPlans.eligible ? (
            <Text style={sharedStyles.hint}>
              Ya tienes una membresía activa o un pago en proceso. El pago en línea está
              disponible solo para una primera inscripción; para renovar o cambiar tu
              plan, consulta en recepción.
            </Text>
          ) : checkoutPlans.items.length === 0 ? (
            <Text style={sharedStyles.hint}>
              No hay planes disponibles para inscripción en línea.
            </Text>
          ) : (
            checkoutPlans.items.map((plan) => {
              const isStarting = startingCheckoutPlanId === plan.id;
              const disabled = startingCheckoutPlanId !== null;
              return (
                <View key={plan.id} style={styles.checkoutPlan}>
                  <View style={styles.rowHeading}>
                    <Text style={styles.rowTitle}>{plan.name}</Text>
                    <Text style={styles.rowAmount}>
                      {formatMoney(plan.price_cents, plan.currency)}
                    </Text>
                  </View>
                  <Text style={sharedStyles.hint}>
                    {plan.duration_days} días · {plan.currency}
                  </Text>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={
                      isStarting
                        ? `Abriendo checkout para ${plan.name}`
                        : `Pagar ${plan.name} por ${formatMoney(
                            plan.price_cents,
                            plan.currency,
                          )}`
                    }
                    accessibilityState={{ disabled }}
                    disabled={disabled}
                    onPress={() => void openCheckout(plan)}
                    style={({ pressed }) => [
                      sharedStyles.primaryButton,
                      pressed && !disabled ? sharedStyles.primaryButtonPressed : null,
                      disabled ? sharedStyles.primaryButtonDisabled : null,
                    ]}
                  >
                    {isStarting ? (
                      <ActivityIndicator color={colors.accentText} />
                    ) : (
                      <Text style={sharedStyles.primaryButtonText}>Continuar al pago</Text>
                    )}
                  </Pressable>
                </View>
              );
            })
          )}
          {checkoutError ? (
            <Text accessibilityRole="alert" style={sharedStyles.error}>
              {checkoutError}
            </Text>
          ) : null}
          {checkoutNotice ? (
            <Text accessibilityLiveRegion="polite" style={sharedStyles.hint}>
              {checkoutNotice}
            </Text>
          ) : null}
        </View>
      ) : checkoutError ? (
        <View style={styles.errorBanner}>
          <Text accessibilityRole="alert" style={sharedStyles.error}>
            No se pudieron consultar las opciones de pago en línea: {checkoutError}
          </Text>
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
  checkoutPlan: {
    borderTopColor: colors.border,
    borderTopWidth: 1,
    gap: spacing.sm,
    paddingTop: spacing.md,
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
