import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { ApiError, getMemberInvoices } from "../api";
import { API_URL } from "../config";
import { describeError } from "../errors";
import {
  cfdiPaymentMethodLabel,
  formatDate,
  formatMoney,
  invoiceOriginLabel,
  invoiceStatusLabel,
  paymentFormLabel,
} from "../format";
import { colors, radius, sharedStyles, spacing } from "../theme";
import type { MemberInvoice, MemberInvoicePage } from "../types";

type Props = {
  token: string;
  onBack: () => void;
  onSessionExpired: () => void;
};

type DocumentKind = "pdf" | "xml";

export function InvoicesScreen({ token, onBack, onSessionExpired }: Props) {
  const [invoices, setInvoices] = useState<MemberInvoicePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);

  const load = useCallback(
    async (mode: "initial" | "refresh") => {
      setLoading(mode === "initial");
      setRefreshing(mode === "refresh");
      try {
        const next = await getMemberInvoices(token);
        setInvoices(next);
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

  async function openDocument(invoice: MemberInvoice, kind: DocumentKind) {
    const path = kind === "pdf" ? invoice.pdf_path : invoice.xml_path;
    if (!path) {
      return;
    }
    const key = `${invoice.id}-${kind}`;
    setOpening(key);
    try {
      await Linking.openURL(`${API_URL}${path}`);
    } catch {
      setError(
        "No pudimos abrir el documento. Desliza hacia abajo para generar enlaces nuevos.",
      );
    } finally {
      setOpening(null);
    }
  }

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
        <Text style={sharedStyles.label}>Facturación</Text>
        <Text style={sharedStyles.title}>Tus facturas</Text>
        <Text style={sharedStyles.body}>
          Comprobantes fiscales (CFDI) emitidos a tu nombre. Descarga el PDF o el
          XML de cada uno.
        </Text>
      </View>

      {error ? (
        <View style={styles.errorBanner}>
          <Text style={sharedStyles.error}>{error}</Text>
        </View>
      ) : null}

      {loading && !invoices ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.accent} />
          <Text style={sharedStyles.body}>Cargando tus facturas…</Text>
        </View>
      ) : null}

      {invoices ? (
        invoices.items.length === 0 ? (
          <View style={sharedStyles.card}>
            <Text style={sharedStyles.body}>
              Aún no tienes facturas emitidas. Si necesitas un comprobante de tus
              pagos, solicítalo en recepción.
            </Text>
          </View>
        ) : (
          <View style={styles.list}>
            <Text style={sharedStyles.hint}>
              {invoices.total}{" "}
              {invoices.total === 1
                ? "comprobante emitido a tu nombre"
                : "comprobantes emitidos a tu nombre"}
              .
            </Text>
            {invoices.items.map((invoice) => {
              const issued = invoice.issued_at ?? invoice.created_at;
              return (
                <View key={invoice.id} style={sharedStyles.card}>
                  <View style={styles.rowHeading}>
                    <Text style={styles.folio}>{invoice.folio_label}</Text>
                    <View
                      style={[
                        styles.pill,
                        invoice.status === "stamped"
                          ? styles.pillOk
                          : invoice.status === "failed"
                            ? styles.pillBad
                            : null,
                      ]}
                    >
                      <Text
                        style={[
                          styles.pillText,
                          invoice.status === "stamped"
                            ? styles.pillTextOk
                            : invoice.status === "failed"
                              ? styles.pillTextBad
                              : null,
                        ]}
                      >
                        {invoiceStatusLabel(invoice.status)}
                      </Text>
                    </View>
                  </View>

                  <Text style={styles.total}>{formatMoney(invoice.total_cents)}</Text>
                  <Text style={sharedStyles.body}>
                    {invoiceOriginLabel(invoice.origin_type)} · {formatDate(issued)}
                  </Text>

                  {invoice.status === "stamped" || invoice.status === "cancelled" ? (
                    <Text style={sharedStyles.hint}>
                      IVA incluido: {formatMoney(invoice.tax_cents)} ·{" "}
                      {cfdiPaymentMethodLabel(invoice.payment_method)} ·{" "}
                      {paymentFormLabel(invoice.payment_form)}
                    </Text>
                  ) : null}

                  {invoice.uuid ? (
                    <Text style={sharedStyles.hint} selectable>
                      Folio fiscal: {invoice.uuid}
                    </Text>
                  ) : null}

                  {invoice.cancelled_at ? (
                    <Text style={sharedStyles.hint}>
                      Cancelada el {formatDate(invoice.cancelled_at)}.
                    </Text>
                  ) : null}

                  {invoice.is_simulated ? (
                    <Text style={styles.notice}>
                      Comprobante de prueba: el timbrado no proviene del SAT.
                    </Text>
                  ) : null}

                  {invoice.pdf_path || invoice.xml_path ? (
                    <View style={styles.actions}>
                      {invoice.pdf_path ? (
                        <Pressable
                          accessibilityRole="button"
                          accessibilityLabel={`Descargar PDF de la factura ${invoice.folio_label}`}
                          disabled={opening !== null}
                          onPress={() => void openDocument(invoice, "pdf")}
                          style={({ pressed }) => [
                            sharedStyles.secondaryButton,
                            styles.actionButton,
                            pressed && sharedStyles.secondaryButtonPressed,
                            opening !== null && sharedStyles.primaryButtonDisabled,
                          ]}
                        >
                          <Text style={sharedStyles.secondaryButtonText}>
                            {opening === `${invoice.id}-pdf` ? "Abriendo…" : "Descargar PDF"}
                          </Text>
                        </Pressable>
                      ) : null}
                      {invoice.xml_path ? (
                        <Pressable
                          accessibilityRole="button"
                          accessibilityLabel={`Descargar XML de la factura ${invoice.folio_label}`}
                          disabled={opening !== null}
                          onPress={() => void openDocument(invoice, "xml")}
                          style={({ pressed }) => [
                            sharedStyles.secondaryButton,
                            styles.actionButton,
                            pressed && sharedStyles.secondaryButtonPressed,
                            opening !== null && sharedStyles.primaryButtonDisabled,
                          ]}
                        >
                          <Text style={sharedStyles.secondaryButtonText}>
                            {opening === `${invoice.id}-xml` ? "Abriendo…" : "Descargar XML"}
                          </Text>
                        </Pressable>
                      ) : null}
                    </View>
                  ) : (
                    <Text style={sharedStyles.hint}>
                      El comprobante estará disponible cuando el timbrado se
                      complete.
                    </Text>
                  )}
                </View>
              );
            })}
          </View>
        )
      ) : null}

      <Text style={sharedStyles.hint}>
        Los enlaces de descarga son personales y vencen a los 10 minutos. Desliza
        hacia abajo para generar enlaces nuevos.
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
  list: {
    gap: spacing.md,
  },
  rowHeading: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
    justifyContent: "space-between",
  },
  folio: {
    color: colors.text,
    fontSize: 17,
    fontWeight: "800",
    letterSpacing: 0.6,
  },
  pill: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  pillOk: {
    backgroundColor: "rgba(34, 197, 94, 0.16)",
  },
  pillBad: {
    backgroundColor: "rgba(248, 113, 113, 0.16)",
  },
  pillText: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: "700",
  },
  pillTextOk: {
    color: colors.accent,
  },
  pillTextBad: {
    color: colors.danger,
  },
  total: {
    color: colors.text,
    fontSize: 28,
    fontWeight: "800",
  },
  notice: {
    color: colors.warning,
    fontSize: 13,
    lineHeight: 19,
  },
  actions: {
    flexDirection: "row",
    gap: spacing.sm,
    marginTop: spacing.xs,
  },
  actionButton: {
    flex: 1,
  },
});
