import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
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
  getMemberBillableOrigins,
  getMemberFiscalProfile,
  requestMemberInvoice,
} from "../api";
import { describeError } from "../errors";
import {
  formatDate,
  formatMoney,
  invoiceOriginLabel,
  invoiceStatusLabel,
  paymentMethodLabel,
} from "../format";
import { colors, radius, sharedStyles, spacing } from "../theme";
import type {
  MemberBillableOrigin,
  MemberFiscalProfile,
  MemberInvoice,
} from "../types";

type Props = {
  token: string;
  onBack: () => void;
  onSessionExpired: () => void;
};

type FormState = {
  rfc: string;
  legal_name: string;
  tax_regime: string;
  postal_code: string;
  cfdi_use: string;
  email: string;
};

const EMPTY_FORM: FormState = {
  rfc: "",
  legal_name: "",
  tax_regime: "612",
  postal_code: "",
  cfdi_use: "G03",
  email: "",
};

function formFromProfile(profile: MemberFiscalProfile | null): FormState {
  if (!profile) {
    return EMPTY_FORM;
  }
  return {
    rfc: profile.rfc,
    legal_name: profile.legal_name,
    tax_regime: profile.tax_regime,
    postal_code: profile.postal_code,
    cfdi_use: profile.cfdi_use,
    email: profile.email ?? "",
  };
}

function validate(form: FormState): string | null {
  const rfc = form.rfc.trim().toUpperCase();
  if (rfc.length < 12 || rfc.length > 13) {
    return "El RFC debe tener 12 o 13 caracteres.";
  }
  if (form.legal_name.trim().length < 2) {
    return "Escribe tu nombre o razón social como aparece en tu constancia fiscal.";
  }
  if (!/^\d{3}$/.test(form.tax_regime.trim())) {
    return "El régimen fiscal debe ser una clave de 3 dígitos (por ejemplo 612).";
  }
  if (!/^\d{5}$/.test(form.postal_code.trim())) {
    return "El código postal debe tener 5 dígitos.";
  }
  if (form.cfdi_use.trim().length !== 3) {
    return "El uso del CFDI debe ser una clave de 3 caracteres (por ejemplo G03).";
  }
  const email = form.email.trim();
  if (email && !email.includes("@")) {
    return "Revisa el correo: no parece válido.";
  }
  return null;
}

// The key only changes when the request payload changes, so a network retry
// replays the same invoice instead of creating a second one.
function idempotencyKey(origin: MemberBillableOrigin, form: FormState): string {
  const source = [
    origin.origin_type,
    origin.origin_id,
    form.rfc.trim().toUpperCase(),
    form.legal_name.trim().toUpperCase(),
    form.tax_regime.trim(),
    form.postal_code.trim(),
    form.cfdi_use.trim().toUpperCase(),
    form.email.trim().toLowerCase(),
  ].join("|");
  let hash = 2166136261;
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `app-${origin.origin_id}-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

export function InvoiceRequestScreen({ token, onBack, onSessionExpired }: Props) {
  const [origins, setOrigins] = useState<MemberBillableOrigin[] | null>(null);
  const [profile, setProfile] = useState<MemberFiscalProfile | null>(null);
  const [selected, setSelected] = useState<MemberBillableOrigin | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [result, setResult] = useState<MemberInvoice | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (mode: "initial" | "refresh") => {
      setLoading(mode === "initial");
      setRefreshing(mode === "refresh");
      try {
        const [listing, fiscal] = await Promise.all([
          getMemberBillableOrigins(token),
          getMemberFiscalProfile(token),
        ]);
        setOrigins(listing.items);
        setProfile(fiscal);
        if (mode === "initial") {
          setForm(formFromProfile(fiscal));
        }
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

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function selectOrigin(origin: MemberBillableOrigin) {
    setSelected(origin);
    setResult(null);
    setError(null);
  }

  async function submit() {
    if (!selected || submitting) {
      return;
    }
    const problem = validate(form);
    if (problem) {
      setError(problem);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const response = await requestMemberInvoice(token, {
        origin_type: selected.origin_type as "sale" | "membership_payment",
        origin_id: selected.origin_id,
        idempotency_key: idempotencyKey(selected, form),
        receptor: {
          rfc: form.rfc.trim(),
          legal_name: form.legal_name.trim(),
          tax_regime: form.tax_regime.trim(),
          postal_code: form.postal_code.trim(),
          cfdi_use: form.cfdi_use.trim(),
          email: form.email.trim() || null,
        },
      });
      setResult(response.invoice);
      setOrigins((current) =>
        current
          ? current.filter((item) => item.origin_id !== selected.origin_id)
          : current,
      );
      setSelected(null);
    } catch (submitError) {
      if (submitError instanceof ApiError && submitError.status === 401) {
        onSessionExpired();
        return;
      }
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
        style={sharedStyles.screen}
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
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
          accessibilityLabel="Volver a facturas"
          onPress={onBack}
          style={styles.back}
          hitSlop={12}
        >
          <Text style={styles.backText}>← Facturas</Text>
        </Pressable>

        <View style={styles.hero}>
          <Text style={sharedStyles.label}>Facturación</Text>
          <Text style={sharedStyles.title}>Solicitar factura</Text>
          <Text style={sharedStyles.body}>
            Elige la compra o el cobro que quieres facturar y confirma tus datos
            fiscales. El personal timbra el comprobante y después podrás
            descargarlo desde Facturas.
          </Text>
        </View>

        {error ? (
          <View style={styles.errorBanner}>
            <Text style={sharedStyles.error} accessibilityLiveRegion="polite">
              {error}
            </Text>
          </View>
        ) : null}

        {result ? (
          <View style={sharedStyles.card}>
            <Text style={sharedStyles.label}>Comprobante {result.folio_label}</Text>
            <Text style={styles.resultTitle}>
              {invoiceStatusLabel(result.status)}
            </Text>
            <Text style={sharedStyles.body}>
              Recibimos tu solicitud por {formatMoney(result.total_cents)}. Cuando
              el timbrado termine, podrás descargar el PDF y el XML desde
              Facturas.
            </Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Ver mis facturas"
              onPress={onBack}
              style={({ pressed }) => [
                sharedStyles.primaryButton,
                pressed && sharedStyles.primaryButtonPressed,
              ]}
            >
              <Text style={sharedStyles.primaryButtonText}>Ver mis facturas</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Solicitar otra factura"
              onPress={() => setResult(null)}
              style={({ pressed }) => [
                sharedStyles.secondaryButton,
                pressed && sharedStyles.secondaryButtonPressed,
              ]}
            >
              <Text style={sharedStyles.secondaryButtonText}>
                Solicitar otra factura
              </Text>
            </Pressable>
          </View>
        ) : null}

        {loading && !origins ? (
          <View style={styles.loading}>
            <ActivityIndicator color={colors.accent} />
            <Text style={sharedStyles.body}>Buscando operaciones por facturar…</Text>
          </View>
        ) : null}

        {!result && origins ? (
          origins.length === 0 ? (
            <View style={sharedStyles.card}>
              <Text style={sharedStyles.body}>
                No tienes operaciones pendientes de facturar. Si ya solicitaste
                una factura, revisa su estado en Facturas.
              </Text>
            </View>
          ) : (
            <View style={styles.list}>
              <Text style={sharedStyles.hint}>
                {origins.length === 1
                  ? "1 operación pendiente de facturar."
                  : `${origins.length} operaciones pendientes de facturar.`}
              </Text>
              {origins.map((origin) => {
                const isSelected = selected?.origin_id === origin.origin_id;
                return (
                  <Pressable
                    key={origin.origin_id}
                    accessibilityRole="button"
                    accessibilityLabel={`Facturar ${invoiceOriginLabel(origin.origin_type)} ${origin.reference}`}
                    accessibilityState={{ selected: isSelected }}
                    onPress={() => selectOrigin(origin)}
                    style={({ pressed }) => [
                      sharedStyles.card,
                      styles.originCard,
                      isSelected && styles.originSelected,
                      pressed && styles.originPressed,
                    ]}
                  >
                    <View style={styles.originHeading}>
                      <Text style={styles.originReference}>{origin.reference}</Text>
                      <Text style={styles.originAmount}>
                        {formatMoney(origin.total_cents)}
                      </Text>
                    </View>
                    <Text style={sharedStyles.body}>{origin.description}</Text>
                    <Text style={sharedStyles.hint}>
                      {invoiceOriginLabel(origin.origin_type)} ·{" "}
                      {formatDate(origin.occurred_at)} ·{" "}
                      {paymentMethodLabel(origin.payment_method)}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          )
        ) : null}

        {selected && !result ? (
          <View style={sharedStyles.card}>
            <Text style={sharedStyles.label}>Datos fiscales</Text>
            <Text style={sharedStyles.body}>
              Factura para {selected.reference} por{" "}
              {formatMoney(selected.total_cents)}.
            </Text>
            {profile ? (
              <Text style={sharedStyles.hint}>
                Usamos los datos que guardaste. Puedes corregirlos: los
                recordaremos para tu próxima factura.
              </Text>
            ) : (
              <Text style={sharedStyles.hint}>
                Captura tus datos como aparecen en tu constancia de situación
                fiscal. Los guardaremos para tu próxima factura.
              </Text>
            )}

            <FiscalField
              label="RFC"
              value={form.rfc}
              onChangeText={(value) => update("rfc", value)}
              placeholder="LOPA800101AAA"
              autoCapitalize="characters"
              maxLength={13}
              editable={!submitting}
            />
            <FiscalField
              label="Nombre o razón social"
              value={form.legal_name}
              onChangeText={(value) => update("legal_name", value)}
              placeholder="Ana López"
              autoCapitalize="words"
              maxLength={254}
              editable={!submitting}
            />
            <View style={styles.row}>
              <View style={styles.rowItem}>
                <FiscalField
                  label="Régimen fiscal"
                  value={form.tax_regime}
                  onChangeText={(value) => update("tax_regime", value)}
                  placeholder="612"
                  keyboardType="number-pad"
                  maxLength={3}
                  editable={!submitting}
                />
              </View>
              <View style={styles.rowItem}>
                <FiscalField
                  label="Código postal"
                  value={form.postal_code}
                  onChangeText={(value) => update("postal_code", value)}
                  placeholder="06700"
                  keyboardType="number-pad"
                  maxLength={5}
                  editable={!submitting}
                />
              </View>
            </View>
            <FiscalField
              label="Uso del CFDI"
              value={form.cfdi_use}
              onChangeText={(value) => update("cfdi_use", value)}
              placeholder="G03"
              autoCapitalize="characters"
              maxLength={3}
              editable={!submitting}
            />
            <FiscalField
              label="Correo para la factura (opcional)"
              value={form.email}
              onChangeText={(value) => update("email", value)}
              placeholder="tu@correo.com"
              keyboardType="email-address"
              autoCapitalize="none"
              maxLength={254}
              editable={!submitting}
            />

            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Enviar solicitud de factura"
              disabled={submitting}
              onPress={() => void submit()}
              style={({ pressed }) => [
                sharedStyles.primaryButton,
                pressed && sharedStyles.primaryButtonPressed,
                submitting && sharedStyles.primaryButtonDisabled,
              ]}
            >
              {submitting ? (
                <ActivityIndicator color={colors.accentText} />
              ) : (
                <Text style={sharedStyles.primaryButtonText}>
                  Solicitar factura
                </Text>
              )}
            </Pressable>
          </View>
        ) : null}

        <Text style={sharedStyles.hint}>
          La factura se emite por el total con IVA incluido. Al enviar la
          solicitud, tus datos fiscales se guardan para la próxima vez.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

type FieldProps = {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder?: string;
  keyboardType?: "default" | "email-address" | "number-pad";
  autoCapitalize?: "none" | "characters" | "words";
  maxLength?: number;
  editable?: boolean;
};

function FiscalField({
  label,
  value,
  onChangeText,
  placeholder,
  keyboardType = "default",
  autoCapitalize = "none",
  maxLength,
  editable = true,
}: FieldProps) {
  return (
    <View style={styles.field}>
      <Text style={sharedStyles.label}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.textMuted}
        style={sharedStyles.input}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize}
        autoCorrect={false}
        maxLength={maxLength}
        editable={editable}
        accessibilityLabel={label}
      />
    </View>
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
  resultTitle: {
    color: colors.accent,
    fontSize: 24,
    fontWeight: "800",
  },
  loading: {
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.xl,
  },
  list: {
    gap: spacing.md,
  },
  originCard: {
    gap: spacing.xs,
  },
  originPressed: {
    backgroundColor: colors.surfaceMuted,
  },
  originSelected: {
    borderColor: colors.accent,
  },
  originHeading: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
    justifyContent: "space-between",
  },
  originReference: {
    color: colors.text,
    fontSize: 17,
    fontWeight: "800",
    letterSpacing: 0.6,
  },
  originAmount: {
    color: colors.text,
    fontSize: 18,
    fontWeight: "800",
  },
  field: {
    gap: spacing.xs,
  },
  row: {
    flexDirection: "row",
    gap: spacing.sm,
  },
  rowItem: {
    flex: 1,
  },
});
