import { Platform, StyleSheet } from "react-native";

export const colors = {
  background: "#07110D",
  surface: "#102019",
  surfaceElevated: "#163024",
  surfaceMuted: "#182A21",
  border: "#294236",
  text: "#F7FAF8",
  textMuted: "#A6B7AD",
  accent: "#A3E635",
  accentDark: "#84CC16",
  accentText: "#173A0A",
  warning: "#F59E0B",
  danger: "#F87171",
  info: "#60A5FA",
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
};

export const radius = {
  sm: 10,
  md: 16,
  lg: 24,
  xl: 32,
};

export const sharedStyles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    padding: spacing.lg,
    paddingBottom: spacing.xl,
    gap: spacing.md,
  },
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.lg,
    borderWidth: 1,
    elevation: 2,
    gap: spacing.sm,
    padding: spacing.lg,
    shadowColor: "#000000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.14,
    shadowRadius: 10,
  },
  statusBanner: {
    borderRadius: radius.md,
    borderWidth: 1,
    padding: spacing.md,
  },
  label: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1.1,
    textTransform: "uppercase",
  },
  title: {
    color: colors.text,
    fontSize: 30,
    fontWeight: "800",
    letterSpacing: -0.6,
    lineHeight: 36,
  },
  sectionHeader: {
    color: colors.text,
    fontSize: 20,
    fontWeight: "900",
    letterSpacing: -0.3,
  },
  body: {
    color: colors.textMuted,
    fontSize: 15,
    lineHeight: 22,
  },
  hint: {
    color: colors.textMuted,
    fontSize: 13,
    lineHeight: 19,
  },
  error: {
    color: colors.danger,
    fontSize: 14,
    lineHeight: 20,
  },
  input: {
    backgroundColor: colors.surfaceMuted,
    borderColor: colors.border,
    borderRadius: radius.md,
    borderWidth: 1,
    color: colors.text,
    fontSize: 16,
    paddingHorizontal: spacing.md,
    paddingVertical: Platform.OS === "ios" ? 16 : 13,
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: colors.accent,
    borderRadius: radius.md,
    paddingVertical: 15,
  },
  primaryButtonPressed: {
    backgroundColor: colors.accentDark,
  },
  primaryButtonDisabled: {
    opacity: 0.55,
  },
  primaryButtonText: {
    color: colors.accentText,
    fontSize: 16,
    fontWeight: "800",
  },
  secondaryButton: {
    alignItems: "center",
    borderColor: colors.border,
    borderRadius: radius.md,
    borderWidth: 1,
    paddingVertical: 13,
  },
  secondaryButtonPressed: {
    backgroundColor: colors.surfaceMuted,
  },
  secondaryButtonText: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "700",
  },
});
