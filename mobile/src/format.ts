const MONTHS = [
  "ene",
  "feb",
  "mar",
  "abr",
  "may",
  "jun",
  "jul",
  "ago",
  "sep",
  "oct",
  "nov",
  "dic",
];

const MEMBERSHIP_LABELS: Record<string, string> = {
  active: "Activa",
  frozen: "Congelada",
  pending_payment: "Pago pendiente",
  suspended: "Suspendida",
  cancelled: "Cancelada",
  expired: "Vencida",
};

const MEMBER_LABELS: Record<string, string> = {
  active: "Activo",
  pending: "Pendiente",
  inactive: "Inactivo",
};

export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return `${String(date.getDate()).padStart(2, "0")} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}

export function formatMoney(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  return `${sign}$${(Math.abs(cents) / 100).toFixed(2)} MXN`;
}

export function membershipStatusLabel(status: string): string {
  return MEMBERSHIP_LABELS[status] ?? status;
}

export function memberStatusLabel(status: string): string {
  return MEMBER_LABELS[status] ?? status;
}
