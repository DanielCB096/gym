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
  onOpenInvoices: () => void;
  onOpenNotifications: () => void;
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
  onOpenInvoices,
  onOpenNotifications,
}: Props) {
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
          <View style={styles.brandDot} />
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
            <Text style={sharedStyles.title}>Hola, {profile.first_name}.</Text>
            <Text style={sharedStyles.body}>
              Este es el estado de tu cuenta con el gimnasio.
            </Text>
          </View>

          {error ? (
            <View style={styles.errorBanner}>
              <Text style={sharedStyles.error}>{error}</Text>
            </View>
          ) : null}

          <Pressable
            accessibilityRole="button"
            accessibilityLabel={
              profile.access_enabled
                ? "Ver mi código de acceso"
                : "Acceso no disponible"
            }
            accessibilityState={{ disabled: !profile.access_enabled }}
            disabled={!profile.access_enabled}
            onPress={onOpenAccessCode}
            style={({ pressed }) => [
              sharedStyles.card,
              styles.accessCard,
              profile.access_enabled ? styles.accessOn : styles.accessOff,
              pressed && styles.navCardPressed,
            ]}
          >
            <View style={styles.accessRow}>
              <View
                style={[
                  styles.statusDot,
                  {
                    backgroundColor: profile.access_enabled
                      ? colors.accent
                      : colors.warning,
                  },
                ]}
              />
              <Text style={styles.accessTitle}>
                {profile.access_enabled ? "Acceso habilitado" : "Acceso no disponible"}
              </Text>
            </View>
            <Text style={sharedStyles.body}>
              {profile.access_enabled
                ? "Muestra tu código en recepción para registrar tu entrada."
                : "Tu membresía no está activa o está vencida. Pasa a recepción para regularizarla."}
            </Text>
            {profile.access_enabled ? (
              <Text style={styles.accessAction}>Ver mi código →</Text>
            ) : null}
          </Pressable>

          <Pressable
            accessibilityRole="button"
            accessibilityLabel={
              unreadNotifications > 0
                ? `Ver notificaciones, ${unreadNotifications} sin leer`
                : "Ver notificaciones"
            }
            onPress={onOpenNotifications}
            style={({ pressed }) => [
              sharedStyles.card,
              styles.navCard,
              pressed && styles.navCardPressed,
            ]}
          >
            <View style={styles.navText}>
              <View style={styles.navTitleRow}>
                <Text style={styles.navTitle}>Avisos del gimnasio</Text>
                {unreadNotifications > 0 ? (
                  <View style={styles.badge}>
                    <Text style={styles.badgeText}>
                      {unreadNotifications > 99 ? "99+" : unreadNotifications}
                    </Text>
                  </View>
                ) : null}
              </View>
              <Text style={sharedStyles.body}>
                Revisiones, metas y clases: lo que el personal resolvió sobre ti.
              </Text>
            </View>
            <Text style={styles.navChevron}>→</Text>
          </Pressable>

          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Ver clases y reservar"
            onPress={onOpenClasses}
            style={({ pressed }) => [
              sharedStyles.card,
              styles.navCard,
              pressed && styles.navCardPressed,
            ]}
          >
            <View style={styles.navText}>
              <Text style={styles.navTitle}>Clases y reservas</Text>
              <Text style={sharedStyles.body}>
                Consulta la cartelera y aparta tu lugar.
              </Text>
            </View>
            <Text style={styles.navChevron}>→</Text>
          </Pressable>

          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Ver fisioterapia"
            onPress={onOpenPhysio}
            style={({ pressed }) => [
              sharedStyles.card,
              styles.navCard,
              pressed && styles.navCardPressed,
            ]}
          >
            <View style={styles.navText}>
              <Text style={styles.navTitle}>Fisioterapia</Text>
              <Text style={sharedStyles.body}>
                Consulta tus sesiones, tu próxima cita y tu historial.
              </Text>
            </View>
            <Text style={styles.navChevron}>→</Text>
          </Pressable>

          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Ver rutinas y progreso"
            onPress={onOpenRoutines}
            style={({ pressed }) => [
              sharedStyles.card,
              styles.navCard,
              pressed && styles.navCardPressed,
            ]}
          >
            <View style={styles.navText}>
              <Text style={styles.navTitle}>Rutinas y progreso</Text>
              <Text style={sharedStyles.body}>
                Revisa tu plan, tus medidas y tus metas.
              </Text>
            </View>
            <Text style={styles.navChevron}>→</Text>
          </Pressable>

          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Ver pagos y estado de cuenta"
            onPress={onOpenPayments}
            style={({ pressed }) => [
              sharedStyles.card,
              styles.navCard,
              pressed && styles.navCardPressed,
            ]}
          >
            <View style={styles.navText}>
              <Text style={styles.navTitle}>Pagos y estado de cuenta</Text>
              <Text style={sharedStyles.body}>
                Revisa tus pagos y los movimientos de tu cuenta.
              </Text>
            </View>
            <Text style={styles.navChevron}>→</Text>
          </Pressable>

          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Ver facturas, solicitar y descargar comprobantes fiscales"
            onPress={onOpenInvoices}
            style={({ pressed }) => [
              sharedStyles.card,
              styles.navCard,
              pressed && styles.navCardPressed,
            ]}
          >
            <View style={styles.navText}>
              <Text style={styles.navTitle}>Facturas</Text>
              <Text style={sharedStyles.body}>
                Solicita facturas y descarga tus comprobantes en PDF y XML.
              </Text>
            </View>
            <Text style={styles.navChevron}>→</Text>
          </Pressable>

          <View style={sharedStyles.card}>
            <Text style={sharedStyles.label}>Membresía</Text>
            {profile.membership ? (
              <>
                <View style={styles.planRow}>
                  <Text style={styles.planName}>{profile.membership.plan_name}</Text>
                  <View style={styles.pill}>
                    <Text style={styles.pillText}>
                      {membershipStatusLabel(profile.membership.status)}
                    </Text>
                  </View>
                </View>
                <Text style={sharedStyles.body}>
                  {formatDate(profile.membership.starts_at)} —{" "}
                  {formatDate(profile.membership.ends_at)}
                </Text>
                <Text style={styles.days}>
                  {profile.membership.days_remaining}
                  <Text style={styles.daysUnit}>
                    {profile.membership.days_remaining === 1
                      ? " día restante"
                      : " días restantes"}
                  </Text>
                </Text>
                {profile.membership.auto_renew ? (
                  <Text style={sharedStyles.hint}>Renovación automática activa.</Text>
                ) : null}
              </>
            ) : (
              <Text style={sharedStyles.body}>
                Aún no tienes una membresía asignada. Pasa a recepción para
                activarla.
              </Text>
            )}
          </View>

          <View style={sharedStyles.card}>
            <Text style={sharedStyles.label}>Saldo en tu cuenta</Text>
            <Text style={styles.balance}>{formatMoney(profile.balance_cents)}</Text>
            <Text style={sharedStyles.hint}>
              {profile.balance_cents > 0
                ? "Puedes liquidarlo en recepción."
                : profile.balance_cents < 0
                  ? "Tienes saldo a favor."
                  : "No tienes cargos pendientes."}
            </Text>
          </View>

          <View style={sharedStyles.card}>
            <Text style={sharedStyles.label}>Tus datos</Text>
            <View style={styles.infoRow}>
              <Text style={styles.infoKey}>Correo</Text>
              <Text style={styles.infoValue}>
                {profile.email ?? "Sin correo registrado"}
              </Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoKey}>Teléfono</Text>
              <Text style={styles.infoValue}>
                {profile.phone ?? "Sin teléfono registrado"}
              </Text>
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

          <Text style={sharedStyles.hint}>
            Desliza hacia abajo para actualizar tu información.
          </Text>
        </>
      ) : (
        <View style={styles.emptyState}>
          <Text style={sharedStyles.title}>
            Hola{fallbackName ? `, ${fallbackName}` : ""}.
          </Text>
          {error ? (
            <Text style={sharedStyles.error}>{error}</Text>
          ) : (
            <Text style={sharedStyles.body}>No pudimos cargar tu información.</Text>
          )}
          {refreshing ? (
            <ActivityIndicator color={colors.accent} />
          ) : (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Reintentar"
              onPress={onRefresh}
              style={({ pressed }) => [
                sharedStyles.primaryButton,
                pressed && sharedStyles.primaryButtonPressed,
              ]}
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
  container: {
    gap: spacing.md,
    padding: spacing.lg,
    paddingBottom: spacing.xl,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
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
  logout: {
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
    padding: spacing.md,
  },
  accessCard: {
    borderWidth: 1,
  },
  accessOn: {
    borderColor: "rgba(34, 197, 94, 0.5)",
  },
  accessOff: {
    borderColor: "rgba(245, 158, 11, 0.5)",
  },
  accessRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  statusDot: {
    borderRadius: 5,
    height: 10,
    width: 10,
  },
  accessTitle: {
    color: colors.text,
    fontSize: 17,
    fontWeight: "800",
  },
  accessAction: {
    color: colors.accent,
    fontSize: 15,
    fontWeight: "700",
  },
  navCard: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.md,
    justifyContent: "space-between",
  },
  navCardPressed: {
    backgroundColor: colors.surfaceMuted,
  },
  navText: {
    flex: 1,
    gap: spacing.xs,
  },
  navTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: "800",
  },
  navTitleRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  badge: {
    alignItems: "center",
    backgroundColor: colors.accent,
    borderRadius: 999,
    minWidth: 24,
    paddingHorizontal: 7,
    paddingVertical: 2,
  },
  badgeText: {
    color: colors.accentText,
    fontSize: 12,
    fontWeight: "800",
  },
  navChevron: {
    color: colors.accent,
    fontSize: 24,
    fontWeight: "800",
  },
  planRow: {
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
    justifyContent: "space-between",
  },
  planName: {
    color: colors.text,
    flexShrink: 1,
    fontSize: 22,
    fontWeight: "800",
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
  days: {
    color: colors.accent,
    fontSize: 38,
    fontWeight: "800",
  },
  daysUnit: {
    color: colors.textMuted,
    fontSize: 15,
    fontWeight: "600",
  },
  balance: {
    color: colors.text,
    fontSize: 32,
    fontWeight: "800",
  },
  infoRow: {
    alignItems: "flex-start",
    borderTopColor: colors.border,
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: spacing.md,
    justifyContent: "space-between",
    paddingTop: spacing.sm,
  },
  infoKey: {
    color: colors.textMuted,
    fontSize: 14,
  },
  infoValue: {
    color: colors.text,
    flexShrink: 1,
    fontSize: 14,
    fontWeight: "600",
    textAlign: "right",
  },
  emptyState: {
    gap: spacing.md,
    paddingTop: spacing.xl,
  },
});
