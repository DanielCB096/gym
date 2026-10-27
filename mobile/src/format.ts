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

const ASSIGNMENT_LABELS: Record<string, string> = {
  active: "Activa",
  completed: "Completada",
  cancelled: "Cancelada",
};

const GOAL_METRIC_LABELS: Record<string, string> = {
  weight_kg: "Peso",
  waist_cm: "Cintura",
  chest_cm: "Pecho",
  body_fat_percent: "Grasa corporal",
};

const GOAL_METRIC_UNITS: Record<string, string> = {
  weight_kg: "kg",
  waist_cm: "cm",
  chest_cm: "cm",
  body_fat_percent: "%",
};

const GOAL_STATUS_LABELS: Record<string, string> = {
  active: "En curso",
  achieved: "Cumplida",
  cancelled: "Cancelada",
};

const GOAL_DIRECTION_LABELS: Record<string, string> = {
  decrease: "Bajar",
  increase: "Subir",
};

const PAYMENT_METHOD_LABELS: Record<string, string> = {
  cash: "Efectivo",
  card: "Tarjeta",
  transfer: "Transferencia",
  spei: "SPEI",
  account: "Cuenta",
};

const NOTIFICATION_KIND_LABELS: Record<string, string> = {
  workout_reviewed: "Entrenamiento",
  goal_achieved: "Meta cumplida",
  goal_cancelled_by_staff: "Meta cancelada",
  goal_updated_by_staff: "Meta ajustada",
  class_waitlist_promoted: "Clase",
  membership_expiring: "Membresía",
  equipment_out_of_service: "Equipo",
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

export function formatDay(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) {
    return formatDate(value);
  }
  const month = MONTHS[Number(match[2]) - 1];
  if (!month) {
    return formatDate(value);
  }
  return `${Number(match[3])} ${month} ${match[1]}`;
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

export function assignmentStatusLabel(status: string): string {
  return ASSIGNMENT_LABELS[status] ?? status;
}

export function goalMetricLabel(metric: string): string {
  return GOAL_METRIC_LABELS[metric] ?? metric;
}

export function goalStatusLabel(status: string): string {
  return GOAL_STATUS_LABELS[status] ?? status;
}

export function goalDirectionLabel(direction: string): string {
  return GOAL_DIRECTION_LABELS[direction] ?? direction;
}

export function goalMetricUnit(metric: string): string {
  return GOAL_METRIC_UNITS[metric] ?? "";
}

export function formatMetric(metric: string, value: number | null): string {
  if (value === null) {
    return "—";
  }
  const unit = GOAL_METRIC_UNITS[metric] ?? "";
  return unit ? `${value} ${unit}` : String(value);
}

export function paymentMethodLabel(method: string | null): string {
  if (!method) {
    return "—";
  }
  return PAYMENT_METHOD_LABELS[method] ?? method;
}

export function notificationKindLabel(kind: string): string {
  return NOTIFICATION_KIND_LABELS[kind] ?? "Aviso";
}

export function formatSignedMoney(cents: number): string {
  if (cents === 0) {
    return formatMoney(0);
  }
  return `${cents > 0 ? "+" : "−"}${formatMoney(Math.abs(cents))}`;
}
