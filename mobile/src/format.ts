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

const WEEKDAYS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

const RESERVATION_LABELS: Record<string, string> = {
  reserved: "Confirmada",
  waitlist: "En lista de espera",
  attended: "Asistida",
  no_show: "No asistió",
  cancelled: "Cancelada",
};

const BLOCKED_REASON_LABELS: Record<string, string> = {
  membership_inactive: "Necesitas una membresía activa",
  premium_class: "Clase premium: reserva en recepción",
  full: "Sin lugares disponibles",
  already_reserved: "Ya tienes una reserva",
  started: "La clase ya comenzó",
};

export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return `${String(date.getDate()).padStart(2, "0")} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${WEEKDAYS[date.getDay()]} ${date.getDate()} ${MONTHS[date.getMonth()]} · ${hours}:${minutes}`;
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

export function reservationStatusLabel(status: string): string {
  return RESERVATION_LABELS[status] ?? status;
}

export function blockedReasonLabel(reason: string | null): string | null {
  if (!reason) {
    return null;
  }
  return BLOCKED_REASON_LABELS[reason] ?? reason;
}
