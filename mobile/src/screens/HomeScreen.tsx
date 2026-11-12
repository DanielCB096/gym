import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import {
  formatDate,
  formatMoney,
  memberStatusLabel,
  membershipStatusLabel,
} from "../format";
import { colors, radius, sharedStyles, spacing } from "../theme";
import type { MemberProfile } from "../types";

type Props = {
  profile: MemberProfile | null;
  fallbackName: string | null;
  refreshing: boolean;
  error: string | null;
  unreadNotifications: number;
  onRefresh: () => void;
  onLogout: () => void;
  onOpenAccessCode: () => void;
  onOpenClasses: () => void;
  onOpenPhysio: () => void;
  onOpenRoutines: () => void;
  onOpenPayments: () => void;
  onOpenNotifications: () => void;
};

type QuickAction = {
  title: string;
  subtitle: string;
  mark: string;
  onPress: () => void;
};

export function HomeScreen({
  profile,
  fallbackName,
  refreshing,
  error,
  unreadNotifications,
  onRefresh,
  onLogout,
  onOpenAccessCode,
  onOpenClasses,
  onOpenPhysio,
  onOpenRoutines,
  onOpenPayments,
  onOpenNotifications,
}: Props) {
  const quickActions: QuickAction[] = [
    { title: "Clases", subtitle: "Reservar", mark: "CL", onPress: onOpenClasses },
    { title: "Rutinas", subtitle: "Mi plan", mark: "RT", onPress: onOpenRoutines },
    { title: "Estado de cuenta", subtitle: "Movimientos", mark: "$", onPress: onOpenPayments },
  ];

  return (
    <ScrollView
      style={sharedStyles.screen}
      contentContainerStyle={styles.container}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={onRefresh}
          tintColor={colors.accent}
          colors={[colors.accent]}
          progressBackgroundColor={colors.surface}
        />
      }
    >
      <View style={styles.header}>
        <View style={styles.brandRow}>
          <View style={styles.brandMark}>
            <View style={styles.brandMarkInner} />
          </View>
          <Text style={styles.brand}>CENTRO FIT</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Cerrar sesión"
          onPress={onLogout}
          hitSlop={12}
        >
          <Text style={styles.logout}>Salir</Text>
        </Pressable>
      </View>

      {profile ? (
        <>
          <View style={styles.hero}>
            <Text style={styles.kicker}>HOLA DE NUEVO</Text>
            <Text style={sharedStyles.title}>{profile.first_name}</Text>
          </View>

          {error ? (
            <View style={styles.errorBanner}>
              <Text style={sharedStyles.error}>{error}</Text>
            </View>
          ) : null}

          <Pressable
            accessibilityRole="button"
            accessibilityLabel={profile.access_enabled ? "Ver mi código de acceso" : "Acceso no disponible"}
            accessibilityState={{ disabled: !profile.access_enabled }}
            disabled={!profile.access_enabled}
            onPress={onOpenAccessCode}
            style={({ pressed }) => [
              styles.accessCard,
              profile.access_enabled ? styles.accessOn : styles.accessOff,
              pressed && styles.pressed,
            ]}
          >
            <View style={styles.accessCopy}>
              <View style={styles.accessLabelRow}>
                <View style={[styles.statusDot, { backgroundColor: profile.access_enabled ? colors.accent : colors.warning }]} />
                <Text style={styles.accessLabel}>
                  {profile.access_enabled ? "ACCESO HABILITADO" : "ACCESO NO DISPONIBLE"}
                </Text>
              </View>
              <Text style={styles.accessTitle}>
                {profile.access_enabled ? "Listo para entrar" : "Regulariza tu acceso"}
              </Text>
              <Text style={styles.accessHint}>
                {profile.access_enabled ? "Abre tu código para recepción" : "Consulta en recepción las indicaciones"}
              </Text>
            </View>
            {profile.access_enabled ? (
              <View style={styles.accessArrow}>
                <Text style={styles.accessArrowText}>→</Text>
              </View>
            ) : null}
          </Pressable>

          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Resumen</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Ver notificaciones"
              onPress={onOpenNotifications}
              hitSlop={8}
            >
              <Text style={styles.sectionAction}>
                Avisos{unreadNotifications > 0 ? ` · ${unreadNotifications}` : ""}
              </Text>
            </Pressable>
          </View>

          <View style={styles.summaryGrid}>
            <View style={[styles.summaryCard, styles.summaryPrimary]}>
              <Text style={styles.summaryLabel}>MEMBRESÍA</Text>
              <Text style={styles.summaryValue}>
                {profile.membership?.plan_name ?? "Sin plan"}
              </Text>
              <Text style={styles.summaryMeta}>
                {profile.membership
                  ? `${profile.membership.days_remaining} días restantes`
                  : "Pasa a recepción"}
              </Text>
            </View>
            <View style={styles.summaryCard}>
              <Text style={styles.summaryLabel}>SALDO</Text>
              <Text style={[styles.summaryValue, profile.balance_cents > 0 ? styles.balanceDue : undefined]}>
                {formatMoney(profile.balance_cents)}
              </Text>
              <Text style={styles.summaryMeta}>
                {profile.balance_cents < 0 ? "Saldo a favor" : profile.balance_cents > 0 ? "Cargo pendiente" : "Cuenta al día"}
              </Text>
            </View>
          </View>

          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Acciones rápidas</Text>
          </View>
          <View style={styles.quickGrid}>
            {quickActions.map((action) => (
              <Pressable
                key={action.title}
                accessibilityRole="button"
                accessibilityLabel={`${action.title}: ${action.subtitle}`}
                onPress={action.onPress}
                style={({ pressed }) => [styles.quickCard, pressed && styles.pressed]}
              >
                <View style={styles.quickMark}>
                  <Text style={styles.quickMarkText}>{action.mark}</Text>
                </View>
                <Text style={styles.quickTitle}>{action.title}</Text>
                <Text style={styles.quickSubtitle}>{action.subtitle}</Text>
              </Pressable>
            ))}
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Ver fisioterapia"
              onPress={onOpenPhysio}
              style={({ pressed }) => [styles.quickCard, pressed && styles.pressed]}
            >
              <View style={styles.quickMark}>
                <Text style={styles.quickMarkText}>FT</Text>
              </View>
              <Text style={styles.quickTitle}>Fisioterapia</Text>
              <Text style={styles.quickSubtitle}>Mis sesiones</Text>
            </Pressable>
          </View>

          {profile.membership ? (
            <View style={[sharedStyles.card, styles.membershipCard]}>
              <View style={styles.membershipHeader}>
                <Text style={sharedStyles.label}>Estado de membresía</Text>
                <View style={styles.statusPill}>
                  <Text style={styles.statusPillText}>
                    {membershipStatusLabel(profile.membership.status)}
                  </Text>
                </View>
              </View>
              <Text style={styles.membershipDates}>
                {formatDate(profile.membership.starts_at)} — {formatDate(profile.membership.ends_at)}
              </Text>
              {profile.membership.auto_renew ? (
                <Text style={sharedStyles.hint}>Renovación automática activa.</Text>
              ) : null}
            </View>
          ) : null}

          <View style={[sharedStyles.card, styles.accountCard]}>
            <Text style={sharedStyles.label}>Tus datos</Text>
            <View style={styles.infoRow}>
              <Text style={styles.infoKey}>Correo</Text>
              <Text style={styles.infoValue}>{profile.email ?? "Sin correo registrado"}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoKey}>Socio desde</Text>
              <Text style={styles.infoValue}>{formatDate(profile.member_since)}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoKey}>Estado</Text>
              <Text style={styles.infoValue}>{memberStatusLabel(profile.status)}</Text>
            </View>
          </View>

          <Text style={sharedStyles.hint}>Desliza hacia abajo para actualizar tu información.</Text>
        </>
      ) : (
        <View style={styles.emptyState}>
          <Text style={sharedStyles.title}>Hola{fallbackName ? `, ${fallbackName}` : ""}</Text>
          {error ? <Text style={sharedStyles.error}>{error}</Text> : <Text style={sharedStyles.body}>No pudimos cargar tu información.</Text>}
          {refreshing ? (
            <ActivityIndicator color={colors.accent} />
          ) : (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Reintentar"
              onPress={onRefresh}
              style={({ pressed }) => [sharedStyles.primaryButton, pressed && sharedStyles.primaryButtonPressed]}
            >
              <Text style={sharedStyles.primaryButtonText}>Reintentar</Text>
            </Pressable>
          )}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { gap: spacing.md, padding: spacing.lg, paddingBottom: 40 },
  header: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  brandRow: { alignItems: "center", flexDirection: "row", gap: spacing.sm },
  brandMark: { alignItems: "center", backgroundColor: colors.accent, borderRadius: 8, height: 22, justifyContent: "center", width: 22 },
  brandMarkInner: { borderColor: colors.accentText, borderRadius: 4, borderWidth: 2, height: 9, width: 9 },
  brand: { color: colors.text, fontSize: 13, fontWeight: "900", letterSpacing: 2.4 },
  logout: { color: colors.textMuted, fontSize: 14, fontWeight: "700" },
  hero: { gap: 2, paddingTop: spacing.sm },
  kicker: { color: colors.accent, fontSize: 12, fontWeight: "900", letterSpacing: 1.8 },
  errorBanner: { backgroundColor: "rgba(248,113,113,0.12)", borderColor: "rgba(248,113,113,0.25)", borderRadius: radius.md, borderWidth: 1, padding: spacing.md },
  accessCard: { borderRadius: radius.lg, flexDirection: "row", minHeight: 150, overflow: "hidden", padding: spacing.lg, alignItems: "center", justifyContent: "space-between" },
  accessOn: { backgroundColor: colors.accent, borderColor: colors.accent },
  accessOff: { backgroundColor: colors.surfaceElevated, borderColor: "rgba(245,158,11,0.45)", borderWidth: 1 },
  pressed: { opacity: 0.82 },
  accessCopy: { flex: 1, gap: 5 },
  accessLabelRow: { alignItems: "center", flexDirection: "row", gap: spacing.sm },
  statusDot: { borderRadius: 999, height: 8, width: 8 },
  accessLabel: { color: colors.accentText, fontSize: 11, fontWeight: "900", letterSpacing: 1.1 },
  accessTitle: { color: colors.accentText, fontSize: 24, fontWeight: "900", letterSpacing: -0.5 },
  accessHint: { color: "#315B1C", fontSize: 14, lineHeight: 20 },
  accessArrow: { alignItems: "center", backgroundColor: "rgba(23,58,10,0.12)", borderRadius: 999, height: 48, justifyContent: "center", width: 48 },
  accessArrowText: { color: colors.accentText, fontSize: 24, fontWeight: "900" },
  sectionHeader: { alignItems: "center", flexDirection: "row", justifyContent: "space-between", marginTop: spacing.sm },
  sectionTitle: { color: colors.text, fontSize: 19, fontWeight: "900" },
  sectionAction: { color: colors.accent, fontSize: 14, fontWeight: "800" },
  summaryGrid: { flexDirection: "row", gap: spacing.sm },
  summaryCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.lg, borderWidth: 1, flex: 1, gap: 6, minHeight: 132, padding: spacing.md },
  summaryPrimary: { backgroundColor: colors.surfaceElevated },
  summaryLabel: { color: colors.textMuted, fontSize: 10, fontWeight: "900", letterSpacing: 1.2 },
  summaryValue: { color: colors.text, fontSize: 18, fontWeight: "900" },
  summaryMeta: { color: colors.textMuted, fontSize: 12 },
  balanceDue: { color: colors.warning },
  quickGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  quickCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.lg, borderWidth: 1, gap: 5, minHeight: 118, padding: spacing.md, width: "48%" },
  quickMark: { alignItems: "center", backgroundColor: colors.surfaceMuted, borderColor: colors.border, borderRadius: 10, borderWidth: 1, height: 38, justifyContent: "center", marginBottom: 3, width: 38 },
  quickMarkText: { color: colors.accent, fontSize: 12, fontWeight: "900" },
  quickTitle: { color: colors.text, fontSize: 16, fontWeight: "900" },
  quickSubtitle: { color: colors.textMuted, fontSize: 12 },
  membershipCard: { gap: spacing.sm },
  membershipHeader: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  statusPill: { backgroundColor: "rgba(163,230,53,0.12)", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 },
  statusPillText: { color: colors.accent, fontSize: 11, fontWeight: "900" },
  membershipDates: { color: colors.text, fontSize: 15, fontWeight: "700" },
  accountCard: { gap: spacing.sm },
  infoRow: { alignItems: "center", borderTopColor: colors.border, borderTopWidth: 1, flexDirection: "row", justifyContent: "space-between", paddingTop: spacing.sm },
  infoKey: { color: colors.textMuted, fontSize: 13 },
  infoValue: { color: colors.text, flexShrink: 1, fontSize: 13, fontWeight: "700", marginLeft: spacing.md, textAlign: "right" },
  emptyState: { alignItems: "center", flex: 1, gap: spacing.md, justifyContent: "center", paddingVertical: 80 },
});
