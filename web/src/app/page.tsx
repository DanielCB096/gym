"use client";

import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Banknote,
  BarChart3,
  Bell,
  CalendarDays,
  Check,
  ChevronDown,
  CircleHelp,
  ClipboardList,
  Clock3,
  DoorOpen,
  Download,
  Dumbbell,
  Fingerprint,
  Flag,
  History,
  Home,
  Landmark,
  Mail,
  LogOut,
  Menu,
  Minus,
  MonitorSmartphone,
  MoreHorizontal,
  Package,
  PenLine,
  Plus,
  Receipt,
  RotateCcw,
  Search,
  Settings,
  ShieldAlert,
  ShieldCheck,
  ShoppingBasket,
  ShoppingCart,
  Tags,
  Trash2,
  Truck,
  Unlink,
  Upload,
  UserPlus,
  Users,
  Wallet,
  Wifi,
  Wrench,
  X,
  type LucideIcon,
} from "lucide-react";
import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";

type PageName = "Resumen" | "Accesos" | "Socios" | "Personal" | "Clases" | "Fisioterapia" | "Rutinas" | "Inventario" | "Mantenimiento" | "Facturación" | "Conciliación" | "Reportes" | "Kiosco";
type AccessState = "Autorizado" | "Denegado" | "Manual";

type AccessEvent = {
  name: string;
  initials: string;
  plan: string;
  time: string;
  reader: string;
  state: AccessState;
  reason?: string;
  color: string;
};

type SessionUser = {
  id: string;
  email: string;
  employee_id: string | null;
  roles: string[];
  permissions: string[];
};

type BackendEmployee = {
  id: string;
  employee_number: string;
  first_name: string;
  last_name: string;
  email: string | null;
  job_title: string;
  status: "active" | "inactive" | "terminated";
  hired_at: string;
};

type BackendRole = {
  code: string;
  name: string;
  description: string;
  permissions: string[];
};

type PermissionCatalogEntry = {
  code: string;
  label: string;
};

type BackendUser = {
  id: string;
  email: string;
  status: "active" | "disabled";
  employee_id: string | null;
  employee_name: string | null;
  roles: string[];
  last_login_at: string | null;
};

type BackendSession = {
  id: string;
  user_id: string;
  email: string;
  employee_name: string | null;
  created_at: string;
  expires_at: string;
  last_seen_at: string | null;
  is_current: boolean;
};

type BackendNotice = {
  id: string;
  kind: string;
  title: string;
  body: string;
  ref_id: string | null;
  created_at: string;
  read_at: string | null;
  resolved_at: string | null;
};

type BackendAttendance = {
  id: string;
  shift_id: string;
  employee_id: string;
  status: "present" | "late";
  check_in_at: string;
  check_in_source: string;
  check_out_at: string | null;
  check_out_source: string | null;
  voided_at: string | null;
};

type AttendancePolicy = {
  check_in_early_grace_minutes: number;
  lateness_tolerance_minutes: number;
  updated_at?: string | null;
};

type AttendanceRequestStatus = "pending" | "approved" | "rejected";

type AttendanceRequest = {
  id: string;
  attendance_id: string;
  employee_id: string;
  employee_name: string | null;
  mark: "check_in" | "check_out";
  action: "correct" | "void";
  proposed_at: string | null;
  justification: string;
  status: AttendanceRequestStatus;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string;
  current_check_in_at: string | null;
  current_check_out_at: string | null;
  requested_by: string;
};

type AttendanceAnnulment = {
  event_id: string;
  event_type: string;
  occurred_at: string;
  reason: string | null;
  attendance_id: string;
  employee_id: string;
  employee_name: string;
  actor_id: string;
  actor_email: string;
  actor_name: string | null;
};

type AttendanceAnnulmentOperator = {
  actor_id: string;
  actor_email: string;
  actor_name: string | null;
  check_ins: number;
  check_outs: number;
  total: number;
  last_at: string;
};

type AttendanceAnnulmentReport = {
  total: number;
  by_operator: AttendanceAnnulmentOperator[];
  items: AttendanceAnnulment[];
};

type StaffingSettingsEvent = {
  id: string;
  changed_at: string;
  actor_email: string | null;
  actor_name: string | null;
  previous_check_in_early_grace_minutes: number;
  previous_lateness_tolerance_minutes: number;
  check_in_early_grace_minutes: number;
  lateness_tolerance_minutes: number;
};

type AttendanceLogEntry = {
  id: string;
  event_type: string;
  source: string;
  occurred_at: string;
  reason: string | null;
  actor_email: string;
  actor_name: string | null;
};

type BackendShift = {
  id: string;
  employee_id: string;
  starts_at: string;
  ends_at: string;
  status: "scheduled" | "cancelled";
  attendance: BackendAttendance | null;
};

type MyAttendanceBoard = {
  employee_id: string;
  settings: AttendancePolicy;
  items: BackendShift[];
};

type BackendMember = {
  id: string;
  first_name: string;
  last_name: string;
  email: string | null;
  phone: string | null;
  status: "pending" | "active" | "inactive";
  membership_status: string | null;
  plan_name: string | null;
  membership_starts_at: string | null;
  membership_ends_at: string | null;
  auto_renew: boolean | null;
};

type PlanAccessWindow = {
  weekday: number;
  starts_at: string;
  ends_at: string;
};

type BackendPlan = {
  id: string;
  name: string;
  duration_days: number;
  price_cents: number;
  currency: string;
  daily_entry_limit: number | null;
  access_windows: PlanAccessWindow[];
};

type ScheduleDraftRow = {
  key: string;
  weekday: number;
  starts_at: string;
  ends_at: string;
};

const scheduleWeekdayLabels = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const scheduleWeekdayShort = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

function planScheduleSummary(windows: PlanAccessWindow[]): string {
  if (windows.length === 0) return "Abierto todo el día";
  return windows
    .map((window) => `${scheduleWeekdayShort[window.weekday] ?? "?"} ${window.starts_at.slice(0, 5)}–${window.ends_at.slice(0, 5)}`)
    .join(" · ");
}

type AccessSettings = {
  antipassback_seconds: number;
  max_occupancy: number | null;
  occupancy_window_seconds: number;
  updated_at: string;
};

type BackendMembershipState = {
  membership_id: string;
  member_id: string;
  plan_id: string;
  plan_name: string;
  status: string;
  starts_at: string;
  ends_at: string;
  auto_renew: boolean;
  previous_status: string | null;
  plan_changed: boolean;
};

type BackendMembershipPayment = {
  payment_id: string;
  payment_attempt_id: string;
  membership_id: string;
  member_id: string;
  plan_id: string;
  plan_name: string;
  amount_cents: number;
  currency: string;
  method: "cash" | "card" | "transfer";
  paid_at: string;
  cash_session_id: string;
  period_starts_at: string;
  period_ends_at: string;
  membership_status: string;
  auto_renew: boolean;
  renewed: boolean;
  idempotent_replay: boolean;
};

const membershipStatusLabels: Record<string, string> = {
  pending_payment: "Pago pendiente",
  active: "Activa",
  frozen: "Congelada",
  suspended: "Suspendida",
  cancelled: "Cancelada",
  expired: "Vencida",
};

const MEMBER_AVATAR_COLORS = ["mint", "peach", "lavender", "blue", "yellow"];

const MEMBERS_PAGE_SIZE = 10;

type MemberDirectory = {
  items: BackendMember[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  summary: {
    active: number;
    expiring_soon: number;
    frozen: number;
    pending: number;
  };
  plans: { id: string; name: string }[];
};

function memberAvatarColor(id: string): string {
  let hash = 0;
  for (let index = 0; index < id.length; index += 1) {
    hash = (hash * 31 + id.charCodeAt(index)) >>> 0;
  }
  return MEMBER_AVATAR_COLORS[hash % MEMBER_AVATAR_COLORS.length];
}

type BackendAccessEvent = {
  id: string;
  event_id: string;
  member_id: string | null;
  member_name: string | null;
  member_email: string | null;
  plan_name: string | null;
  reader_id: string;
  direction: "entry" | "exit";
  authorized: boolean;
  reason: string;
  note: string | null;
  source: "reader" | "manual";
  occurred_at: string;
  offline: boolean;
};

type AccessDirectory = {
  items: BackendAccessEvent[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  summary: {
    total: number;
    authorized: number;
    denied: number;
    manual: number;
  };
};

type KioskDevice = {
  id: string;
  label: string;
  status: "active" | "revoked";
  created_at: string;
  token_expires_at: string | null;
  last_seen_at: string | null;
};

type KioskDeviceCreated = KioskDevice & { token: string };

type DashboardData = {
  as_of: string;
  members: {
    total: number;
    active: number;
    expiring_soon: number;
    frozen: number;
    pending: number;
  };
  access: {
    entries_today: number;
    denied_today: number;
  };
};

const ACCESS_PAGE_SIZE = 10;

const ACCESS_STATE_PARAMS: Record<AccessState, string> = {
  Autorizado: "authorized",
  Denegado: "denied",
  Manual: "manual",
};

const accessReasonLabels: Record<string, string> = {
  entry_allowed: "Acceso autorizado",
  exit_allowed: "Salida registrada",
  snapshot_missing: "Credencial no válida",
  snapshot_expired: "Credencial desactualizada",
  membership_not_active: "Membresía inactiva",
  membership_not_started: "Membresía no vigente",
  membership_expired: "Membresía vencida",
  blocking_debt: "Adeudo pendiente",
  outside_allowed_hours: "Fuera de horario",
  antipassback: "Entrada duplicada",
  daily_limit: "Límite diario alcanzado",
  occupancy_full: "Aforo completo",
  manual_override: "Autorización manual",
};

function formatAccessTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("es-MX", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(date);
}

function accessDisplayState(event: BackendAccessEvent): AccessState {
  if (event.source === "manual") return "Manual";
  return event.authorized ? "Autorizado" : "Denegado";
}

function accessEventToDisplay(event: BackendAccessEvent): AccessEvent {
  const name = event.member_name ?? "Credencial desconocida";
  const initials = name.split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "?";
  return {
    name,
    initials,
    plan: event.plan_name ?? (event.direction === "exit" ? "Salida" : "Sin plan"),
    time: formatAccessTime(event.occurred_at),
    reader: event.reader_id,
    state: accessDisplayState(event),
    reason: event.source === "manual"
      ? (event.note ?? "Autorización manual")
      : (accessReasonLabels[event.reason] ?? event.reason),
    color: memberAvatarColor(event.member_id ?? event.id),
  };
}

function metricValue(value: number | undefined, loading: boolean): string {
  if (loading || value === undefined) return "—";
  return value.toLocaleString("es-MX");
}

type ProductState = "active" | "low" | "out" | "inactive";

type BackendProduct = {
  id: string;
  sku: string;
  name: string;
  category: string;
  barcode: string | null;
  price_cents: number;
  cost_cents: number | null;
  stock_min: number;
  is_active: boolean;
  stock: number;
  state: ProductState;
  updated_at: string;
};

type ProductSummary = {
  total: number;
  active: number;
  low_stock: number;
  out_of_stock: number;
  inactive: number;
};

type ProductDirectory = {
  items: BackendProduct[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  summary: ProductSummary;
  categories: string[];
};

type BackendSaleLine = {
  sale_item_id: string;
  product_id: string | null;
  product_name: string;
  sku: string;
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
  refunded_quantity: number;
  returnable_quantity: number;
};

type BackendSale = {
  id: string;
  folio: string;
  status: string;
  payment_method: string;
  member_id: string | null;
  member_name: string | null;
  cashier_id: string | null;
  cashier_email: string | null;
  subtotal_cents: number;
  discount_cents: number;
  tax_cents: number;
  total_cents: number;
  refunded_cents: number;
  note: string | null;
  sold_at: string;
  cash_session_id: string | null;
  origin: string;
  client_reference: string | null;
  lines: BackendSaleLine[];
};

type BillingInvoiceStatus = "requested" | "failed" | "stamped" | "cancelled";

type BillingOriginType = "sale" | "membership_payment" | "global" | "credit_note";

type BillingCreditNoteReason = "return" | "discount" | "correction" | "other";

type BillingCreditNoteRef = {
  invoice_id: string;
  folio_label: string;
  status: BillingInvoiceStatus;
  total_cents: number;
  reason: BillingCreditNoteReason;
  note: string | null;
  created_at: string;
};

type BillingPaymentBalanceStatus = "not_applicable" | "unpaid" | "partial" | "paid";

type BillingPaymentComplementRef = {
  payment_id: string;
  folio_label: string;
  status: BillingInvoiceStatus;
  partiality_number: number;
  amount_cents: number;
  payment_form: string;
  paid_on: string;
  prior_balance_cents: number;
  outstanding_balance_cents: number;
  uuid: string | null;
  is_simulated: boolean;
  created_at: string;
};

type BillingPaymentComplement = {
  id: string;
  invoice_id: string;
  invoice_folio_label: string;
  series: string;
  folio: number;
  folio_label: string;
  status: BillingInvoiceStatus;
  partiality_number: number;
  amount_cents: number;
  currency: string;
  payment_form: string;
  paid_on: string;
  prior_balance_cents: number;
  outstanding_balance_cents: number;
  tax_rate_percent: number;
  uuid: string | null;
  is_simulated: boolean;
  provider: string | null;
  provider_reference: string | null;
  xml_available: boolean;
  issued_at: string | null;
  stamped_at: string | null;
  cancelled_at: string | null;
  cancellation_reason_code: string | null;
  cancellation_note: string | null;
  created_at: string;
  created_by: string | null;
  events: BillingInvoiceEvent[];
};

type BillingInvoiceItem = {
  position: number;
  description: string;
  sat_product_code: string;
  sat_unit_code: string;
  unit_name: string;
  quantity: number;
  unit_price_cents: number;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
};

type BillingInvoiceEvent = {
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  actor_id: string | null;
  detail: Record<string, unknown>;
  occurred_at: string;
};

type BillingGlobalInvoiceSale = {
  sale_id: string;
  sale_folio: string;
  sold_at: string;
  total_cents: number;
};

type BillingInvoice = {
  id: string;
  series: string;
  folio: number;
  folio_label: string;
  status: BillingInvoiceStatus;
  origin_type: BillingOriginType;
  origin_id: string;
  origin_reference: string;
  global_year: number | null;
  global_month: number | null;
  member_id: string | null;
  member_name: string | null;
  receptor_rfc: string;
  receptor_name: string;
  receptor_tax_regime: string;
  receptor_postal_code: string;
  receptor_cfdi_use: string;
  receptor_email: string | null;
  currency: string;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  tax_rate_percent: number;
  payment_form: string;
  payment_method: string;
  uuid: string | null;
  is_simulated: boolean;
  provider: string | null;
  provider_reference: string | null;
  xml_available: boolean;
  issued_at: string | null;
  stamped_at: string | null;
  cancelled_at: string | null;
  cancellation_reason_code: string | null;
  cancellation_replacement_uuid: string | null;
  cancellation_note: string | null;
  cancellation_requested_at: string | null;
  cancellation_checked_at: string | null;
  cancellation_pending: boolean;
  created_at: string;
  created_by: string | null;
  related_invoice_id: string | null;
  related_invoice_folio_label: string | null;
  related_invoice_status: string | null;
  credit_note_reason: BillingCreditNoteReason | null;
  credit_note_note: string | null;
  credited_cents: number;
  credit_balance_cents: number;
  credit_notes: BillingCreditNoteRef[];
  paid_cents: number;
  payment_balance_cents: number;
  payment_status: BillingPaymentBalanceStatus;
  payment_complements: BillingPaymentComplementRef[];
  items: BillingInvoiceItem[];
  events: BillingInvoiceEvent[];
  global_sales: BillingGlobalInvoiceSale[];
};

type BillingInvoicePage = {
  items: BillingInvoice[];
  total: number;
  page: number;
  page_size: number;
};

type BillingDelivery = {
  invoice_id: string;
  recipient: string;
  status: "sent" | "simulated";
  attachments: string[];
  sent_at: string;
};

type BillingSummary = {
  total: number;
  requested: number;
  failed: number;
  stamped: number;
  cancelled: number;
  simulated: number;
  stamped_cents: number;
  cancelled_cents: number;
  credit_notes: number;
  credit_note_cents: number;
  net_stamped_cents: number;
  pending_cancellations: number;
};

type BillingPpdAgingBucket = "current" | "days_31_60" | "days_61_90" | "over_90";

type BillingPpdAging = {
  current_cents: number;
  days_31_60_cents: number;
  days_61_90_cents: number;
  over_90_cents: number;
};

type BillingPpdReceivable = {
  invoice_id: string;
  folio_label: string;
  receptor_name: string;
  receptor_rfc: string;
  origin_type: BillingOriginType;
  origin_reference: string;
  member_id: string | null;
  member_name: string | null;
  currency: string;
  total_cents: number;
  paid_cents: number;
  balance_cents: number;
  stamped_at: string | null;
  age_days: number;
  aging_bucket: BillingPpdAgingBucket;
  uuid: string | null;
  is_simulated: boolean;
  stamped_complements: number;
  requested_complements: number;
  failed_complements: number;
  last_payment_on: string | null;
};

type BillingPpdReceivableSummary = {
  as_of: string;
  invoices: number;
  total_cents: number;
  paid_cents: number;
  outstanding_cents: number;
  aging: BillingPpdAging;
  oldest_stamped_at: string | null;
  stamped_complements: number;
  stamped_complement_cents: number;
  requested_complements: number;
  requested_complement_cents: number;
  failed_complements: number;
  failed_complement_cents: number;
};

type BillingPpdReceivablePage = {
  items: BillingPpdReceivable[];
  total: number;
  page: number;
  page_size: number;
  summary: BillingPpdReceivableSummary;
};

type BillingOrigin = {
  origin_type: "sale" | "membership_payment";
  origin_id: string;
  reference: string;
  member_id: string | null;
  member_name: string | null;
  occurred_at: string;
  total_cents: number;
  description: string;
  payment_method: string;
};

type BillingOriginPage = {
  items: BillingOrigin[];
  total: number;
  page: number;
  page_size: number;
};

type BillingFiscalProfile = {
  member_id: string;
  rfc: string;
  legal_name: string;
  tax_regime: string;
  postal_code: string;
  cfdi_use: string;
  email: string | null;
  updated_at: string;
};

type BillingGlobalSale = {
  sale_id: string;
  folio: string;
  sold_at: string;
  total_cents: number;
  payment_method: string;
  description: string;
};

type BillingGlobalInvoiceRef = {
  invoice_id: string;
  folio_label: string;
  status: BillingInvoiceStatus;
};

type BillingGlobalEligibility = {
  year: number;
  month: number;
  period_start: string;
  period_end: string;
  period_closed: boolean;
  total_candidates: number;
  eligible_count: number;
  eligible_total_cents: number;
  subtotal_cents: number;
  tax_cents: number;
  excluded_counts: Record<string, number>;
  items: BillingGlobalSale[];
  page: number;
  page_size: number;
  existing_invoice: BillingGlobalInvoiceRef | null;
};

type BankAccountStatus = "active" | "inactive";
type BankMovementStatus = "pending" | "reconciled" | "difference" | "reviewing";
type BankMovementSource = "membership_payment" | "sale" | "member_account_payment" | "sale_return" | "invoice_payment";

type BankAccount = {
  id: string;
  name: string;
  bank_name: string;
  account_last4: string;
  currency: string;
  status: BankAccountStatus;
  created_at: string;
  updated_at: string;
  movement_count: number;
  pending_count: number;
  reconciled_count: number;
  difference_count: number;
  reviewing_count: number;
  balance_cents: number;
  last_movement_on: string | null;
};

type BankMovement = {
  id: string;
  bank_account_id: string;
  bank_account_name: string;
  bank_name: string;
  account_last4: string;
  occurred_on: string;
  amount_cents: number;
  currency: string;
  reference: string;
  description: string;
  status: BankMovementStatus;
  matched_source: BankMovementSource | null;
  matched_id: string | null;
  matched_label: string | null;
  difference_cents: number | null;
  note: string | null;
  imported_at: string;
  reconciled_at: string | null;
  reviewed_at: string | null;
  suggestion_count: number;
  suggested_label: string | null;
};

type BankMovementSummary = {
  count: number;
  pending: number;
  reconciled: number;
  difference: number;
  reviewing: number;
  inflow_cents: number;
  outflow_cents: number;
  pending_cents: number;
  difference_cents: number;
  oldest_pending_on: string | null;
};

type BankMovementPage = {
  items: BankMovement[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  summary: BankMovementSummary;
};

type BankMovementCandidate = {
  source: BankMovementSource;
  source_id: string;
  label: string;
  detail: string;
  reference: string;
  occurred_on: string;
  amount_cents: number;
  difference_cents: number;
  amount_match: boolean;
  reference_score: number;
  date_distance_days: number;
};

type BankMovementEvent = {
  id: string;
  event_type: string;
  detail: string;
  actor_id: string | null;
  actor_email: string | null;
  occurred_at: string;
};

type BankMovementDetail = BankMovement & {
  candidates: BankMovementCandidate[];
  events: BankMovementEvent[];
};

type BankImportRow = {
  occurred_on: string;
  amount_cents: number;
  reference: string;
  description: string;
};

const RECONCILIATION_PAGE_SIZE = 25;

const bankMovementStatusLabels: Record<BankMovementStatus, string> = {
  pending: "Pendiente",
  reconciled: "Conciliado",
  difference: "Con diferencia",
  reviewing: "En revisión",
};

const bankMovementStatusBadges: Record<BankMovementStatus, string> = {
  pending: "status-warn",
  reconciled: "status-good",
  difference: "status-bad",
  reviewing: "status-neutral",
};

const bankSourceLabels: Record<BankMovementSource, string> = {
  membership_payment: "Cobro de membresía",
  sale: "Venta en mostrador",
  member_account_payment: "Pago a cuenta",
  sale_return: "Devolución de venta",
  invoice_payment: "Complemento PPD",
};

const BILLING_PAGE_SIZE = 10;
const BILLING_PPD_PAGE_SIZE = 10;

const billingStatusLabels: Record<BillingInvoiceStatus, string> = {
  requested: "Solicitada",
  failed: "Error de timbrado",
  stamped: "Timbrada",
  cancelled: "Cancelada",
};

const billingStatusBadges: Record<BillingInvoiceStatus, string> = {
  requested: "status-warn",
  failed: "status-bad",
  stamped: "status-good",
  cancelled: "status-neutral",
};

const billingOriginLabels: Record<BillingOriginType, string> = {
  sale: "Venta en mostrador",
  membership_payment: "Cobro de membresía",
  global: "Factura global",
  credit_note: "Nota de crédito",
};

const billingCreditNoteReasonLabels: Record<BillingCreditNoteReason, string> = {
  return: "Devolución",
  discount: "Descuento",
  correction: "Corrección de importe",
  other: "Otro motivo",
};

const BILLING_CREDIT_NOTE_REASONS: [BillingCreditNoteReason, string][] = [
  ["return", "Devolución"],
  ["discount", "Descuento"],
  ["correction", "Corrección de importe"],
  ["other", "Otro motivo"],
];

const billingMonthLabels = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

const billingGlobalExclusionLabels: Record<string, string> = {
  returned: "Con devolución",
  zero_total: "Importe cero",
  account: "Cargo a cuenta",
  member: "Venta con socio",
  individual_invoice: "Factura individual",
  global_invoice: "En otra global",
};

const billingPaymentMethodLabels: Record<string, string> = {
  cash: "Efectivo",
  card: "Tarjeta",
  transfer: "Transferencia",
  account: "Cuenta del socio",
};

const BILLING_INVOICE_PAYMENT_METHODS: ["PUE" | "PPD", string][] = [
  ["PUE", "PUE · Pago en una sola exhibición"],
  ["PPD", "PPD · Pago en parcialidades o diferido"],
];

const billingPaymentStatusLabels: Record<BillingInvoiceStatus, string> = {
  requested: "Solicitado",
  failed: "Error de timbrado",
  stamped: "Timbrado",
  cancelled: "Cancelado",
};

const billingPaymentBalanceLabels: Record<BillingPaymentBalanceStatus, string> = {
  not_applicable: "No aplica",
  unpaid: "Sin pagos",
  partial: "Pago parcial",
  paid: "Pagada",
};

const billingPaymentBalanceBadges: Record<BillingPaymentBalanceStatus, string> = {
  not_applicable: "status-neutral",
  unpaid: "status-warn",
  partial: "status-warn",
  paid: "status-good",
};

const billingPpdAgingLabels: Record<BillingPpdAgingBucket, string> = {
  current: "0–30 días",
  days_31_60: "31–60 días",
  days_61_90: "61–90 días",
  over_90: "+90 días",
};

const billingPpdAgingBadges: Record<BillingPpdAgingBucket, string> = {
  current: "status-good",
  days_31_60: "status-warn",
  days_61_90: "status-warn",
  over_90: "status-bad",
};

const BILLING_PPD_AGING_FILTERS: ["" | BillingPpdAgingBucket, string][] = [
  ["", "Todos los tramos"],
  ["current", "0–30 días"],
  ["days_31_60", "31–60 días"],
  ["days_61_90", "61–90 días"],
  ["over_90", "+90 días"],
];

const BILLING_TAX_REGIMES: [string, string][] = [
  ["601", "601 · General de Ley Personas Morales"],
  ["603", "603 · Personas Morales con Fines no Lucrativos"],
  ["605", "605 · Sueldos y Salarios e Ingresos Asimilados"],
  ["606", "606 · Arrendamiento"],
  ["607", "607 · Régimen de Enajenación o Adquisición de Bienes"],
  ["608", "608 · Demás ingresos"],
  ["609", "609 · Consolidación"],
  ["610", "610 · Residentes en el Extranjero sin Establecimiento"],
  ["611", "611 · Ingresos por Dividendos (socios y accionistas)"],
  ["612", "612 · Personas Físicas con Actividades Empresariales"],
  ["614", "614 · Ingresos por intereses"],
  ["615", "615 · Régimen de los ingresos por obtención de premios"],
  ["616", "616 · Sin obligaciones fiscales"],
  ["620", "620 · Sociedades Cooperativas de Producción"],
  ["621", "621 · Incorporación Fiscal"],
  ["622", "622 · Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras"],
  ["623", "623 · Opcional para Grupos de Sociedades"],
  ["624", "624 · Coordinados"],
  ["625", "625 · Actividades Empresariales con ingresos a través de Plataformas"],
  ["626", "626 · Régimen Simplificado de Confianza"],
  ["628", "628 · Hidrocarburos"],
  ["629", "629 · De los Regímenes Fiscales Preferentes"],
  ["630", "630 · Enajenación de acciones en bolsa de valores"],
];

const BILLING_CFDI_USES: [string, string][] = [
  ["G01", "G01 · Adquisición de mercancías"],
  ["G02", "G02 · Devoluciones, descuentos o bonificaciones"],
  ["G03", "G03 · Gastos en general"],
  ["D01", "D01 · Instalaciones"],
  ["D02", "D02 · Mobiliario y equipo de oficina"],
  ["D03", "D03 · Equipo de transporte"],
  ["D04", "D04 · Equipo de cómputo y accesorios"],
  ["D05", "D05 · Dados, troqueles, moldes y matrices"],
  ["D06", "D06 · Comunicaciones telefónicas"],
  ["D07", "D07 · Comunicaciones satelitales"],
  ["D08", "D08 · Otra maquinaria y equipo"],
  ["D09", "D09 · Donativos"],
  ["D10", "D10 · Pagos por servicios educativos"],
  ["I01", "I01 · Construcciones"],
  ["I02", "I02 · Mobiliario y equipo de oficina (inversión)"],
  ["I03", "I03 · Equipo de transporte (inversión)"],
  ["I04", "I04 · Equipo de cómputo y accesorios (inversión)"],
  ["I05", "I05 · Dados, troqueles, moldes (inversión)"],
  ["I06", "I06 · Comunicaciones telefónicas (inversión)"],
  ["I07", "I07 · Comunicaciones satelitales (inversión)"],
  ["I08", "I08 · Otra maquinaria y equipo (inversión)"],
  ["P01", "P01 · Por definir"],
  ["S01", "S01 · Sin efectos fiscales"],
  ["CP01", "CP01 · Pagos"],
  ["CN01", "CN01 · Nómina"],
];

const BILLING_PAYMENT_FORMS: [string, string][] = [
  ["01", "01 · Efectivo"],
  ["02", "02 · Cheque nominativo"],
  ["03", "03 · Transferencia electrónica de fondos"],
  ["04", "04 · Tarjeta de crédito"],
  ["05", "05 · Monedero electrónico"],
  ["06", "06 · Dinero electrónico"],
  ["08", "08 · Vales de despensa"],
  ["12", "12 · Dación en pago"],
  ["13", "13 · Pago por subrogación"],
  ["14", "14 · Pago por consignación"],
  ["15", "15 · Condonación"],
  ["16", "16 · Compensación"],
  ["17", "17 · Novación"],
  ["18", "18 · Amortización de crédito"],
  ["19", "19 · Pago de intereses"],
  ["20", "20 · Pago de intereses nominales"],
  ["21", "21 · Incorporación"],
  ["22", "22 · Otras formas de pago"],
  ["99", "99 · Por definir"],
];

const BILLING_PAYMENT_FORM_BY_METHOD: Record<string, string> = {
  cash: "01",
  transfer: "03",
  card: "04",
  account: "99",
};

const BILLING_PAYMENT_COMPLEMENT_FORMS: [string, string][] = BILLING_PAYMENT_FORMS.filter(
  ([value]) => value !== "99",
);

const BILLING_CANCELLATION_REASONS: [string, string][] = [
  ["01", "01 · Comprobante emitido con errores con relación"],
  ["02", "02 · Comprobante emitido con errores sin relación"],
  ["03", "03 · No se llevó a cabo la operación"],
  ["04", "04 · Operación nominativa relacionada en factura global"],
];

const BILLING_UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function billingInvoiceStatus(status: string): BillingInvoiceStatus {
  return (status in billingStatusLabels ? status : "requested") as BillingInvoiceStatus;
}

function billingPaymentFormLabel(code: string): string {
  return BILLING_PAYMENT_FORMS.find(([value]) => value === code)?.[1] ?? code;
}

function billingInvoicePaymentMethodLabel(method: string): string {
  return method === "PPD" ? "Pago en parcialidades o diferido" : "Pago en una sola exhibición";
}

function billingTaxRegimeLabel(code: string): string {
  return BILLING_TAX_REGIMES.find(([value]) => value === code)?.[1] ?? code;
}

function billingCfdiUseLabel(code: string): string {
  return BILLING_CFDI_USES.find(([value]) => value === code)?.[1] ?? code;
}

function billingErrorDetail(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((entry) => {
      if (typeof entry === "string") return entry;
      if (entry && typeof entry === "object" && typeof (entry as { msg?: unknown }).msg === "string") return (entry as { msg: string }).msg;
      return "";
    }).filter(Boolean);
    if (messages.length > 0) return messages.join(" ");
  }
  return fallback;
}

function billingGlobalPeriodLabel(year: number, month: number): string {
  const name = billingMonthLabels[month - 1] ?? String(month);
  return `${name.charAt(0).toUpperCase()}${name.slice(1)} de ${year}`;
}

function billingGlobalPeriodValue(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, "0")}`;
}

function billingGlobalPeriodOptions(): { value: string; label: string }[] {
  const now = new Date();
  return Array.from({ length: 24 }, (_, index) => {
    const period = new Date(now.getFullYear(), now.getMonth() - index, 1);
    const year = period.getFullYear();
    const month = period.getMonth() + 1;
    return { value: billingGlobalPeriodValue(year, month), label: billingGlobalPeriodLabel(year, month) };
  });
}

function defaultBillingGlobalPeriod(): { year: number; month: number } {
  const now = new Date();
  const previous = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return { year: previous.getFullYear(), month: previous.getMonth() + 1 };
}

type SaleSummary = {
  count: number;
  total_cents: number;
  cash_cents: number;
  card_cents: number;
  transfer_cents: number;
  account_cents: number;
  refunds_cents: number;
  refunded_count: number;
};

type SaleDirectory = {
  items: BackendSale[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  summary: SaleSummary;
};

type OfflineSaleEntry = {
  client_reference: string;
  sold_at: string;
  items: { product_id: string; quantity: number }[];
  payment_method: "cash" | "card" | "transfer";
  member_id: string | null;
  note: string | null;
  total_cents: number;
  summary: string;
  error?: string;
};

type OfflineSaleResult = {
  client_reference: string;
  status: "created" | "duplicate" | "rejected";
  sale: BackendSale | null;
  error: string | null;
};

type OfflineSaleSync = {
  results: OfflineSaleResult[];
  created: number;
  duplicates: number;
  rejected: number;
};

type SaleReturnLine = {
  sale_item_id: string;
  product_id: string | null;
  product_name: string;
  sku: string;
  quantity: number;
  unit_price_cents: number;
  line_refund_cents: number;
  disposition: "restock" | "write_off";
};

type SaleReturn = {
  id: string;
  folio: string;
  sale_id: string;
  sale_folio: string;
  cash_session_id: string | null;
  member_id: string | null;
  member_name: string | null;
  actor_id: string | null;
  actor_email: string | null;
  refund_method: string;
  total_refund_cents: number;
  reason: string;
  returned_at: string;
  lines: SaleReturnLine[];
};

type SaleReturnSummary = {
  count: number;
  total_refund_cents: number;
  cash_refund_cents: number;
  card_refund_cents: number;
  transfer_refund_cents: number;
  account_refund_cents: number;
};

type SaleReturnDirectory = {
  items: SaleReturn[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  summary: SaleReturnSummary;
};

type MemberAccountEntry = {
  kind: string;
  occurred_at: string;
  description: string;
  reference: string;
  method: string | null;
  amount_cents: number;
  balance_cents: number;
};

type AccountAging = {
  current_cents: number;
  days_31_60_cents: number;
  days_61_90_cents: number;
  over_90_cents: number;
};

type MemberAccountSummary = {
  member_id: string;
  member_name: string;
  email: string | null;
  phone: string | null;
  member_status: string;
  charges_cents: number;
  credits_cents: number;
  payments_cents: number;
  balance_cents: number;
  credit_limit_cents: number | null;
  credit_available_cents: number | null;
  over_limit: boolean;
  aging: AccountAging;
  charges_count: number;
  payments_count: number;
  last_activity_at: string | null;
  oldest_charge_at: string | null;
};

type MemberAccountDirectory = {
  items: MemberAccountSummary[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  total_receivable_cents: number;
  total_credit_cents: number;
  members_with_balance: number;
  aging: AccountAging;
  over_limit_members: number;
  as_of: string;
};

type MemberAccountStatement = {
  summary: MemberAccountSummary;
  entries: MemberAccountEntry[];
  as_of: string;
};

type StatementDelivery = {
  id: string;
  member_id: string;
  actor_id: string | null;
  actor_email: string | null;
  recipient: string;
  format: string;
  purpose: "statement" | "reminder";
  status: "sent" | "simulated" | "failed";
  as_of: string;
  error: string | null;
  retry_of_id: string | null;
  created_at: string;
};

type StatementDeliveryPage = {
  items: StatementDelivery[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

type StatementReminderResult = {
  member_id: string;
  member_name: string | null;
  status: "sent" | "simulated" | "skipped" | "failed";
  reason: string | null;
  balance_cents: number;
  overdue_cents: number;
  delivery: StatementDelivery | null;
};

type StatementReminderBatch = {
  requested: number;
  sent: number;
  simulated: number;
  skipped: number;
  failed: number;
  results: StatementReminderResult[];
};

type MemberAccountPayment = {
  id: string;
  member_id: string;
  member_name: string | null;
  cash_session_id: string | null;
  actor_id: string | null;
  actor_email: string | null;
  method: string;
  amount_cents: number;
  note: string | null;
  paid_at: string;
  balance_cents: number;
};

type BackendSupplier = {
  id: string;
  name: string;
  contact_name: string | null;
  phone: string | null;
  email: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type SupplierDirectory = {
  items: BackendSupplier[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

type PurchaseOrderStatus = "created" | "sent" | "received" | "cancelled";

type PurchaseOrderLine = {
  item_id: string;
  product_id: string;
  product_name: string;
  sku: string;
  quantity: number;
  received_quantity: number;
  pending_quantity: number;
  unit_cost_cents: number;
  line_total_cents: number;
};

type BackendPurchaseOrder = {
  id: string;
  folio: string;
  supplier_id: string;
  supplier_name: string;
  status: PurchaseOrderStatus;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  expected_at: string | null;
  notes: string | null;
  created_by: string | null;
  created_by_email: string | null;
  received_by: string | null;
  received_by_email: string | null;
  created_at: string;
  sent_at: string | null;
  received_at: string | null;
  cancelled_at: string | null;
  lines: PurchaseOrderLine[];
};

type PurchaseOrderSummary = {
  count: number;
  created: number;
  sent: number;
  received: number;
  cancelled: number;
  total_cents: number;
};

type PurchaseOrderDirectory = {
  items: BackendPurchaseOrder[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  summary: PurchaseOrderSummary;
};

type CashSession = {
  id: string;
  status: string;
  opened_by: string | null;
  opened_by_email: string | null;
  opened_at: string;
  opening_cash_cents: number;
  closed_by: string | null;
  closed_by_email: string | null;
  closed_at: string | null;
  expected_cash_cents: number;
  counted_cash_cents: number | null;
  difference_cents: number | null;
  notes: string | null;
  sales_count: number;
  total_sales_cents: number;
  cash_sales_cents: number;
  card_sales_cents: number;
  transfer_sales_cents: number;
  account_sales_cents: number;
  refunds_count: number;
  total_refunds_cents: number;
  cash_refunds_cents: number;
  account_refunds_cents: number;
  account_payments_count: number;
  account_payments_cents: number;
  cash_account_payments_cents: number;
  membership_payments_count: number;
  membership_payments_cents: number;
  cash_membership_payments_cents: number;
};

type CartLine = {
  product_id: string;
  name: string;
  sku: string;
  unit_price_cents: number;
  quantity: number;
};

type BackendClassType = {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
};

type BackendClassRoom = {
  id: string;
  name: string;
  capacity: number;
  is_active: boolean;
  created_at: string;
};

type BackendInstructor = {
  id: string;
  name: string;
  job_title: string;
};

type ClassSessionState = "scheduled" | "cancelled";

type BackendClassSession = {
  id: string;
  title: string;
  class_type_id: string;
  class_type_name: string;
  room_id: string | null;
  room_name: string | null;
  instructor_id: string | null;
  instructor_name: string | null;
  starts_at: string;
  ends_at: string;
  capacity: number;
  status: ClassSessionState;
  access_type: "included" | "premium";
  extra_price_cents: number;
  waitlist_enabled: boolean;
  cancel_window_hours: number;
  notes: string | null;
  reserved_count: number;
  waitlist_count: number;
  spots_left: number;
  created_at: string;
  updated_at: string;
  cancelled_at: string | null;
};

type ClassSessionSummary = {
  total: number;
  scheduled: number;
  cancelled: number;
  upcoming: number;
  reserved_total: number;
  waitlist_total: number;
};

type ClassSessionDirectory = {
  items: BackendClassSession[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  summary: ClassSessionSummary;
};

type BackendReservationStatus = "waitlist" | "reserved" | "attended" | "no_show" | "cancelled";

type BackendReservation = {
  id: string;
  session_id: string;
  member_id: string;
  member_name: string;
  member_email: string | null;
  status: BackendReservationStatus;
  origin: string;
  waitlist_position: number | null;
  late_cancellation: boolean;
  note: string | null;
  created_at: string;
  cancelled_at: string | null;
  marked_at: string | null;
  charge_sale_id: string | null;
  charge_cents: number | null;
  charge_payment_method: string | null;
  charge_folio: string | null;
  charge_status: "completed" | "refunded" | null;
};

type ClassRoster = {
  session: BackendClassSession;
  reservations: BackendReservation[];
};

type PhysioAppointmentState = "scheduled" | "attended" | "no_show" | "cancelled";

type BackendPhysioService = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  duration_minutes: number;
  price_cents: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type BackendPhysioOffer = {
  id: string;
  service_id: string;
  service_name: string;
  name: string;
  sessions: number;
  price_cents: number;
  list_price_cents: number;
  savings_cents: number;
  discount_percent: number;
  validity_days: number;
  payment_mode: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type BackendPhysioTherapist = {
  id: string;
  name: string;
  job_title: string;
  specialty_id: string | null;
  specialty_name: string | null;
  room_id: string | null;
  room_name: string | null;
};

type BackendPhysioRoom = {
  id: string;
  name: string;
  is_active: boolean;
};

type BackendPhysioSpecialty = {
  id: string;
  name: string;
  is_active: boolean;
};

type BackendPhysioPack = {
  id: string;
  member_id: string;
  member_name: string;
  offer_id: string;
  offer_name: string;
  service_id: string;
  service_name: string;
  sale_id: string;
  sessions_total: number;
  sessions_used: number;
  remaining_sessions: number;
  price_cents: number;
  purchased_at: string;
  valid_until: string;
  status: "active" | "exhausted" | "expired" | "voided";
  extended_days: number;
  voided_at: string | null;
  voided_sessions: number;
  void_reason: string | null;
};

type BackendPhysioPackAdjustment = {
  id: string;
  pack_id: string;
  kind: "extension" | "void";
  days: number | null;
  reason: string;
  actor_id: string | null;
  created_at: string;
};

type BackendPhysioReport = {
  date_from: string;
  date_to: string;
  totals: {
    appointments: number;
    scheduled: number;
    attended: number;
    no_show: number;
    cancelled: number;
    attendance_rate_percent: number;
    no_show_rate_percent: number;
    cancellation_rate_percent: number;
  };
  occupancy: {
    therapists: number;
    available_minutes: number;
    booked_minutes: number;
    attended_minutes: number;
    percent: number;
  };
  revenue: {
    package_cents: number;
    single_cents: number;
    refunded_cents: number;
    net_cents: number;
    discount_cents: number;
    packages_sold: number;
    sessions_sold: number;
    single_charges: number;
  };
  adjustments: { extended: number; extended_days: number; voided: number; voided_sessions: number };
  by_therapist: { therapist_employee_id: string; therapist_name: string; appointments: number; attended: number; no_show: number; attended_minutes: number }[];
  by_service: { service_id: string; service_name: string; appointments: number; attended: number; no_show: number; single_charges: number; single_revenue_cents: number }[];
  by_hour: { hour: number; appointments: number; attended: number }[];
  daily: { day: string; appointments: number; attended: number; no_show: number; cancelled: number; revenue_cents: number }[];
};

type BackendPhysioAppointment = {
  id: string;
  member_id: string;
  member_name: string;
  service_id: string;
  service_name: string;
  service_price_cents: number;
  pack_id: string | null;
  pack_remaining_sessions: number | null;
  therapist_employee_id: string;
  therapist_name: string;
  room_id: string | null;
  room: string | null;
  starts_at: string;
  ends_at: string;
  status: PhysioAppointmentState;
  notes: string | null;
  booked_by: string | null;
  marked_at: string | null;
  marked_by: string | null;
  cancelled_at: string | null;
  cancelled_by: string | null;
  created_at: string;
  updated_at: string;
  charge_sale_id: string | null;
  charge_cents: number | null;
  charge_payment_method: string | null;
  charge_status: "completed" | "refunded" | null;
};

type PhysioPaymentMethod = "cash" | "card" | "transfer" | "account";

const physioStatusLabels: Record<PhysioAppointmentState, string> = {
  scheduled: "Agendada",
  attended: "Asistió",
  no_show: "No asistió",
  cancelled: "Cancelada",
};

const physioPackStatusLabels: Record<BackendPhysioPack["status"], string> = {
  active: "Activo",
  exhausted: "Agotado",
  expired: "Vencido",
  voided: "Anulado",
};

function physioStatusBadge(status: PhysioAppointmentState): string {
  if (status === "attended") return "status-good";
  if (status === "scheduled") return "status-warn";
  if (status === "no_show") return "status-bad";
  return "status-neutral";
}

function physioPackBadge(status: BackendPhysioPack["status"]): string {
  if (status === "active") return "status-good";
  if (status === "expired") return "status-bad";
  return "status-neutral";
}
function todayInputValue(): string {
  const date = new Date();
  const pad = (input: number) => String(input).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function parseBackendMoment(value: string): Date {
  // SQLite drops the offset, so a naive ISO value is UTC, not local time.
  return new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`);
}

function formatPhysioDay(value: string): string {
  return new Intl.DateTimeFormat("es-MX", { weekday: "short", day: "2-digit", month: "short" }).format(parseBackendMoment(value));
}

function formatPhysioClock(value: string): string {
  return new Intl.DateTimeFormat("es-MX", { hour: "2-digit", minute: "2-digit" }).format(parseBackendMoment(value));
}

function formatPhysioDate(value: string): string {
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short", year: "numeric" }).format(parseBackendMoment(value));
}

function formatInputDay(value: string): string {
  return new Intl.DateTimeFormat("es-MX", { weekday: "long", day: "2-digit", month: "long" }).format(new Date(`${value}T12:00:00`));
}

const CLASSES_PAGE_SIZE = 20;

const classStatusLabels: Record<ClassSessionState, string> = {
  scheduled: "Programada",
  cancelled: "Cancelada",
};

const classReservationLabels: Record<BackendReservationStatus, string> = {
  waitlist: "En espera",
  reserved: "Confirmada",
  attended: "Asistió",
  no_show: "No asistió",
  cancelled: "Cancelada",
};

function classSessionBadge(status: ClassSessionState): string {
  return status === "cancelled" ? "status-bad" : "status-good";
}

function classReservationBadge(status: BackendReservationStatus): string {
  if (status === "attended" || status === "reserved") return "status-good";
  if (status === "waitlist") return "status-warn";
  if (status === "no_show") return "status-bad";
  return "status-neutral";
}

function formatClassDay(value: string): string {
  return new Intl.DateTimeFormat("es-MX", { weekday: "short", day: "2-digit", month: "short" }).format(new Date(value));
}

function formatClassClock(value: string): string {
  return new Intl.DateTimeFormat("es-MX", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function formatNoticeMoment(value: string): string {
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function toDateTimeLocalValue(value: string): string {
  const date = new Date(value);
  const pad = (input: number) => String(input).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function fromDateTimeLocalValue(value: string): string {
  return new Date(value).toISOString();
}

function defaultSessionStart(): string {
  const date = new Date();
  date.setMinutes(0, 0, 0);
  date.setHours(date.getHours() + 1);
  return toDateTimeLocalValue(date.toISOString());
}

type BackendExercise = {
  id: string;
  name: string;
  muscle_group: string;
  category: string;
  equipment_name: string | null;
  equipment_id: string | null;
  equipment_status: EquipmentState | null;
  description: string | null;
  video_url: string | null;
  image_url: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type ExerciseDirectory = {
  items: BackendExercise[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  muscle_groups: string[];
  categories: string[];
};

type BackendRoutineLine = {
  id: string;
  exercise_id: string;
  exercise_name: string;
  muscle_group: string;
  category: string;
  equipment_status: EquipmentState | null;
  position: number;
  sets: number;
  reps: string;
  rest_seconds: number | null;
  load_note: string | null;
  notes: string | null;
};

type BackendRoutineRevision = {
  version: number;
  reason: string | null;
  item_count: number;
  changed_by: string | null;
  created_at: string;
};

type BackendRoutine = {
  id: string;
  name: string;
  trainer_id: string | null;
  trainer_name: string | null;
  objective: string | null;
  notes: string | null;
  status: RoutineState;
  version: number;
  item_count: number;
  active_assignments: number;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

type RoutineDetail = {
  routine: BackendRoutine;
  items: BackendRoutineLine[];
  revisions: BackendRoutineRevision[];
};

type RoutineSummary = {
  total: number;
  active: number;
  draft: number;
  archived: number;
};

type RoutineDirectory = {
  items: BackendRoutine[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  summary: RoutineSummary;
};

type RoutineState = "draft" | "active" | "archived";
type AssignmentState = "active" | "completed" | "cancelled";
type WorkoutState = "logged" | "reviewed";

type BackendAssignment = {
  id: string;
  routine_id: string;
  routine_name: string;
  routine_version: number;
  member_id: string;
  member_name: string;
  member_email: string | null;
  trainer_id: string | null;
  trainer_name: string | null;
  start_date: string;
  end_date: string | null;
  frequency_per_week: number | null;
  status: AssignmentState;
  notes: string | null;
  workouts_logged: number;
  last_workout_at: string | null;
  created_at: string;
  ended_at: string | null;
};

type AssignmentDetail = {
  assignment: BackendAssignment;
  routine_version: number;
  plan: BackendRoutineLine[];
};

type AssignmentSummary = {
  total: number;
  active: number;
  completed: number;
  cancelled: number;
};

type AssignmentDirectory = {
  items: BackendAssignment[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  summary: AssignmentSummary;
};

type RecordOrigin = "staff" | "app";

type BackendWorkoutSet = {
  exercise_id: string;
  exercise_name: string;
  position: number;
  set_number: number;
  reps: number;
  weight_kg: number | null;
};

type BackendWorkout = {
  id: string;
  assignment_id: string;
  member_id: string;
  routine_id: string;
  routine_version: number;
  performed_at: string;
  duration_minutes: number | null;
  perceived_effort: number | null;
  notes: string | null;
  status: WorkoutState;
  origin: RecordOrigin;
  reviewed_at: string | null;
  created_at: string;
  sets: BackendWorkoutSet[];
};

function summarizeWorkoutSets(sets: BackendWorkoutSet[]): string {
  const groups: { name: string; detail: string }[] = [];
  for (const item of sets) {
    const label = `${item.reps}${item.weight_kg !== null ? ` × ${item.weight_kg} kg` : ""}`;
    const last = groups[groups.length - 1];
    if (last && last.name === item.exercise_name) {
      last.detail = `${last.detail} · ${label}`;
    } else {
      groups.push({ name: item.exercise_name, detail: label });
    }
  }
  return groups.map((group) => `${group.name}: ${group.detail}`).join(" | ");
}

type WorkoutSetDraft = {
  key: string;
  exerciseId: string;
  setNumber: number;
  reps: string;
  weight: string;
};

const MAX_WORKOUT_DRAFT_SETS = 60;
const MAX_WORKOUT_DRAFT_SETS_PER_EXERCISE = 20;

type BackendMeasurement = {
  id: string;
  member_id: string;
  measured_at: string;
  weight_kg: number | null;
  waist_cm: number | null;
  chest_cm: number | null;
  body_fat_percent: number | null;
  notes: string | null;
  origin: RecordOrigin;
  created_at: string;
};

type MemberProgress = {
  member_id: string;
  member_name: string;
  active_assignments: number;
  workouts_total: number;
  workouts_last_30_days: number;
  last_workout_at: string | null;
  latest_measurement: BackendMeasurement | null;
  measurements: BackendMeasurement[];
};

type GoalMetric = "weight_kg" | "waist_cm" | "chest_cm" | "body_fat_percent";
type GoalDirection = "decrease" | "increase";
type GoalState = "active" | "achieved" | "cancelled";

type BackendGoal = {
  id: string;
  member_id: string;
  metric: GoalMetric;
  direction: GoalDirection;
  target_value: number;
  baseline_value: number | null;
  baseline_measured_at: string | null;
  target_date: string | null;
  notes: string | null;
  status: GoalState;
  origin: RecordOrigin;
  current_value: number | null;
  current_measured_at: string | null;
  progress_percent: number | null;
  achieved: boolean;
  achieved_value: number | null;
  achieved_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
};

type PhotoAngle = "front" | "side" | "back" | "other";

type BackendProgressPhoto = {
  id: string;
  member_id: string;
  angle: PhotoAngle;
  captured_at: string;
  notes: string | null;
  content_type: string;
  byte_size: number;
  origin: "staff" | "app";
  created_at: string;
};

type RoutinesOverview = {
  exercises: number;
  routines_active: number;
  routines_archived: number;
  assignments_active: number;
  workouts_last_7_days: number;
};

const ROUTINES_PAGE_SIZE = 12;
const ASSIGNMENTS_PAGE_SIZE = 12;

const routineStatusLabels: Record<RoutineState, string> = {
  draft: "Borrador",
  active: "Activa",
  archived: "Archivada",
};

const routineStatusBadges: Record<RoutineState, string> = {
  draft: "status-warn",
  active: "status-good",
  archived: "status-neutral",
};

const assignmentStatusLabels: Record<AssignmentState, string> = {
  active: "Activa",
  completed: "Completada",
  cancelled: "Cancelada",
};

const assignmentStatusBadges: Record<AssignmentState, string> = {
  active: "status-good",
  completed: "status-neutral",
  cancelled: "status-bad",
};

const workoutStatusLabels: Record<WorkoutState, string> = {
  logged: "Registrado",
  reviewed: "Revisado",
};

const workoutStatusBadges: Record<WorkoutState, string> = {
  logged: "status-warn",
  reviewed: "status-good",
};

const recordOriginLabels: Record<RecordOrigin, string> = {
  staff: "Personal",
  app: "App",
};

const goalMetricLabels: Record<GoalMetric, string> = {
  weight_kg: "Peso",
  waist_cm: "Cintura",
  chest_cm: "Pecho",
  body_fat_percent: "Grasa corporal",
};

const goalMetricUnits: Record<GoalMetric, string> = {
  weight_kg: " kg",
  waist_cm: " cm",
  chest_cm: " cm",
  body_fat_percent: "%",
};

const goalDirectionLabels: Record<GoalDirection, string> = {
  decrease: "Bajar",
  increase: "Subir",
};

const goalStatusLabels: Record<GoalState, string> = {
  active: "Activa",
  achieved: "Cumplida",
  cancelled: "Cancelada",
};

const goalStatusBadges: Record<GoalState, string> = {
  active: "status-warn",
  achieved: "status-good",
  cancelled: "status-bad",
};

const GOAL_METRICS: GoalMetric[] = ["weight_kg", "waist_cm", "chest_cm", "body_fat_percent"];
const GOAL_DIRECTIONS: GoalDirection[] = ["decrease", "increase"];

const photoAngleLabels: Record<PhotoAngle, string> = {
  front: "Frente",
  side: "Perfil",
  back: "Espalda",
  other: "Otra",
};

const PHOTO_ANGLES: PhotoAngle[] = ["front", "side", "back", "other"];
const MAX_PROGRESS_PHOTO_BYTES = 8 * 1024 * 1024;

function formatDateOnly(value: string | null): string {
  if (!value) return "—";
  const [year, month, day] = value.slice(0, 10).split("-");
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short", year: "numeric" }).format(
    new Date(Number(year), Number(month) - 1, Number(day)),
  );
}

function toDateInputValue(value: string | null): string {
  if (!value) return "";
  return value.slice(0, 10);
}

function todayDateInput(): string {
  const date = new Date();
  const pad = (input: number) => String(input).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function shiftDateInput(iso: string, days: number): string {
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  const date = new Date(year, (month ?? 1) - 1, day ?? 1);
  date.setDate(date.getDate() + days);
  const pad = (input: number) => String(input).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function formatMeasurementValue(value: number | null, unit: string): string {
  if (value === null || value === undefined) return "—";
  return `${value}${unit}`;
}

function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

type EquipmentState = "operational" | "maintenance" | "out_of_service" | "inspection" | "retired";
type TicketState = "open" | "assigned" | "in_progress" | "resolved" | "cancelled";
type TicketSeverity = "low" | "medium" | "high" | "critical";
type TicketKind = "corrective" | "preventive";
type AreaAvailability = "available" | "partial" | "closed";

type BackendEquipment = {
  id: string;
  name: string;
  category: string;
  brand: string | null;
  model: string | null;
  serial_number: string | null;
  location: string | null;
  acquired_on: string | null;
  useful_life_months: number | null;
  purchase_cost_cents: number;
  status: EquipmentState;
  next_preventive_due: string | null;
  notes: string | null;
  retired_at: string | null;
  open_tickets: number;
  last_maintenance_at: string | null;
  created_at: string;
  updated_at: string;
};

type EquipmentSummary = {
  total: number;
  operational: number;
  maintenance: number;
  out_of_service: number;
  inspection: number;
  retired: number;
};

type EquipmentDirectory = {
  items: BackendEquipment[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  summary: EquipmentSummary;
  categories: string[];
  locations: string[];
};

type EquipmentChoice = {
  id: string;
  name: string;
  location: string | null;
  status: EquipmentState;
};

type LinkedExercise = {
  id: string;
  name: string;
  muscle_group: string;
};

type BackendTicket = {
  id: string;
  code: string;
  equipment_id: string;
  equipment_name: string;
  equipment_status: EquipmentState;
  kind: TicketKind;
  severity: TicketSeverity;
  title: string;
  description: string | null;
  status: TicketState;
  reported_by: string | null;
  reporter_email: string | null;
  reported_at: string;
  assigned_to: string | null;
  assignee_name: string | null;
  assigned_at: string | null;
  scheduled_for: string | null;
  started_at: string | null;
  resolved_at: string | null;
  resolution_notes: string | null;
  cost_cents: number;
  blocked_equipment: boolean;
  created_at: string;
  updated_at: string;
};

type TicketSummary = {
  total: number;
  open: number;
  assigned: number;
  in_progress: number;
  resolved: number;
  cancelled: number;
  critical_open: number;
};

type TicketDirectory = {
  items: BackendTicket[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  summary: TicketSummary;
};

type BackendMaintenanceRecord = {
  id: string;
  equipment_id: string;
  equipment_name: string;
  ticket_id: string | null;
  kind: string;
  summary: string;
  notes: string | null;
  performed_at: string;
  cost_cents: number;
  technician_id: string | null;
  technician_name: string | null;
  created_at: string;
};

type MaintenanceRecordDirectory = {
  items: BackendMaintenanceRecord[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  total_cost_cents: number;
};

type EquipmentDetail = {
  equipment: BackendEquipment;
  tickets: BackendTicket[];
  records: BackendMaintenanceRecord[];
  exercises: LinkedExercise[];
};

type TicketDetail = {
  ticket: BackendTicket;
  record: BackendMaintenanceRecord | null;
};

type BackendChecklist = {
  id: string;
  area: string;
  result: "ok" | "observation" | "pending";
  observations: string | null;
  performed_at: string;
  performed_by: string | null;
  performer_email: string | null;
  created_at: string;
};

type ChecklistDirectory = {
  items: BackendChecklist[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

type MaintenanceOverview = {
  equipment_total: number;
  operational: number;
  maintenance: number;
  out_of_service: number;
  tickets_open: number;
  tickets_critical: number;
  preventives_due: number;
  records_last_30_days: number;
};

type AreaServiceStatus = {
  area: string;
  total: number;
  operational: number;
  maintenance: number;
  out_of_service: number;
  inspection: number;
  retired: number;
  availability: AreaAvailability;
};

type ReportName = "overview" | "revenue" | "memberships" | "operations" | "maintenance" | "inventory";

type ReportPeriod = { date_from: string; date_to: string; days: number; timezone: string };
type ReportCountRow = { label: string; count: number };
type ReportAmountRow = { label: string; count: number; amount_cents: number };
type ReportRevenueDay = { day: string; pos_cents: number; membership_cents: number; total_cents: number; sales_count: number; refunds_cents: number };
type ReportAccessDay = { day: string; total: number; denied: number };
type ReportClassDay = { day: string; sessions: number; attended: number };
type ReportEventDay = { day: string; activations: number; terminations: number };
type ReportPlanRow = { plan_id: string; name: string; price_cents: number; duration_days: number; active_count: number; monthly_cents: number; recurring: boolean };
type ReportProductRow = { product_id: string | null; name: string; sku: string; quantity: number; amount_cents: number };
type ReportEquipmentRow = { equipment_id: string; name: string; category: string; location: string | null; status: string; records_count: number; cost_cents: number; open_tickets: number };

type ReportOverview = {
  period: ReportPeriod;
  pos_cents: number;
  pos_gross_cents: number;
  refunds_cents: number;
  refunds_count: number;
  membership_cents: number;
  sales_count: number;
  average_ticket_cents: number;
  payments_count: number;
  mrr_expected_cents: number;
  maintenance_cost_cents: number;
  maintenance_records: number;
  access_total: number;
  access_denied: number;
  access_manual: number;
  class_sessions: number;
  class_capacity: number;
  class_attended: number;
  class_no_show: number;
  class_occupancy_percent: number;
  workouts: number;
  measurements: number;
  members_by_status: ReportCountRow[];
  memberships_by_status: ReportCountRow[];
  new_members: number;
  members_expiring: number;
  equipment_by_status: ReportCountRow[];
  equipment_total: number;
  tickets_open: number;
  tickets_critical: number;
  revenue_by_day: ReportRevenueDay[];
  access_by_day: ReportAccessDay[];
};

type ReportPpdAging = {
  current_cents: number;
  days_31_60_cents: number;
  days_61_90_cents: number;
  over_90_cents: number;
};

type ReportPpdReceivables = {
  as_of: string;
  invoices: number;
  total_cents: number;
  paid_cents: number;
  outstanding_cents: number;
  aging: ReportPpdAging;
  oldest_stamped_at: string | null;
  stamped_complements: number;
  stamped_complement_cents: number;
  requested_complements: number;
  requested_complement_cents: number;
  failed_complements: number;
  failed_complement_cents: number;
};

type RevenueReport = {
  period: ReportPeriod;
  pos_cents: number;
  pos_gross_cents: number;
  refunds_cents: number;
  refunds_count: number;
  membership_cents: number;
  sales_count: number;
  average_ticket_cents: number;
  payments_count: number;
  by_day: ReportRevenueDay[];
  pos_by_method: ReportAmountRow[];
  membership_by_method: ReportAmountRow[];
  by_category: ReportAmountRow[];
  top_products: ReportProductRow[];
  cash_sessions_opened: number;
  cash_sessions_closed: number;
  cash_difference_cents: number;
  ppd_receivables: ReportPpdReceivables;
};

type MembershipReport = {
  period: ReportPeriod;
  members_total: number;
  members_by_status: ReportCountRow[];
  memberships_by_status: ReportCountRow[];
  by_plan: ReportPlanRow[];
  mrr_expected_cents: number;
  payments_cents: number;
  payments_count: number;
  events: ReportCountRow[];
  events_by_day: ReportEventDay[];
  new_members: number;
  members_expiring: number;
};

type OperationsReport = {
  period: ReportPeriod;
  access_total: number;
  access_authorized: number;
  access_denied: number;
  access_manual: number;
  access_by_day: ReportAccessDay[];
  access_by_hour: ReportCountRow[];
  class_sessions: number;
  class_capacity: number;
  class_reserved: number;
  class_attended: number;
  class_no_show: number;
  class_waitlist: number;
  class_cancelled: number;
  class_occupancy_percent: number;
  classes_by_day: ReportClassDay[];
  workouts: number;
  workout_minutes: number;
  measurements: number;
  workouts_by_day: ReportCountRow[];
};

type MaintenanceReport = {
  period: ReportPeriod;
  cost_cents: number;
  records_count: number;
  by_kind: ReportAmountRow[];
  by_equipment: ReportEquipmentRow[];
  tickets_created: number;
  tickets_by_status: ReportCountRow[];
  tickets_by_severity: ReportCountRow[];
  equipment_by_status: ReportCountRow[];
  preventives_due: number;
};

type ReportMovementRow = { label: string; movements: number; units: number };
type ReportInventoryProductRow = { product_id: string; name: string; sku: string; category: string; quantity: number; cost_cents: number; price_cents: number; cost_value_cents: number; retail_value_cents: number };

type InventoryReport = {
  period: ReportPeriod;
  products_total: number;
  products_active: number;
  products_inactive: number;
  stock_units: number;
  stock_value_cents: number;
  retail_value_cents: number;
  low_stock: number;
  out_of_stock: number;
  by_category: ReportAmountRow[];
  by_product: ReportInventoryProductRow[];
  suppliers_total: number;
  suppliers_active: number;
  open_orders: number;
  open_orders_value_cents: number;
  movements_count: number;
  movements_by_type: ReportMovementRow[];
  units_in: number;
  units_out: number;
  orders_created: number;
  orders_by_status: ReportCountRow[];
  orders_value_cents: number;
  orders_received: number;
  orders_received_value_cents: number;
  by_supplier: ReportAmountRow[];
};

const EQUIPMENT_PAGE_SIZE = 12;
const TICKETS_PAGE_SIZE = 12;
const RECORDS_PAGE_SIZE = 12;
const CHECKLISTS_PAGE_SIZE = 12;

const equipmentStatusLabels: Record<EquipmentState, string> = {
  operational: "Operativo",
  maintenance: "En mantenimiento",
  out_of_service: "Fuera de servicio",
  inspection: "En revisión",
  retired: "Retirado",
};

const equipmentStatusBadges: Record<EquipmentState, string> = {
  operational: "status-good",
  maintenance: "status-warn",
  out_of_service: "status-bad",
  inspection: "status-neutral",
  retired: "status-neutral",
};

const ticketStatusLabels: Record<TicketState, string> = {
  open: "Abierto",
  assigned: "Asignado",
  in_progress: "En proceso",
  resolved: "Resuelto",
  cancelled: "Cancelado",
};

const ticketStatusBadges: Record<TicketState, string> = {
  open: "status-warn",
  assigned: "status-neutral",
  in_progress: "status-warn",
  resolved: "status-good",
  cancelled: "status-neutral",
};

const ticketSeverityLabels: Record<TicketSeverity, string> = {
  low: "Baja",
  medium: "Media",
  high: "Alta",
  critical: "Crítica",
};

const ticketSeverityBadges: Record<TicketSeverity, string> = {
  low: "status-neutral",
  medium: "status-warn",
  high: "status-bad",
  critical: "status-critical",
};

const ticketKindLabels: Record<TicketKind, string> = {
  corrective: "Correctivo",
  preventive: "Preventivo",
};

const recordKindLabels: Record<string, string> = {
  preventive: "Preventivo",
  corrective: "Correctivo",
  inspection: "Inspección",
  cleaning: "Limpieza",
  calibration: "Calibración",
};

const checklistResultLabels: Record<string, string> = {
  ok: "Sin novedad",
  observation: "Con observación",
  pending: "Pendiente",
};

const availabilityLabels: Record<AreaAvailability, string> = {
  available: "Disponible",
  partial: "Parcial",
  closed: "Cerrada",
};

const availabilityBadges: Record<AreaAvailability, string> = {
  available: "status-good",
  partial: "status-warn",
  closed: "status-bad",
};

function equipmentUnavailable(status: EquipmentState | null): boolean {
  return status === "maintenance" || status === "out_of_service";
}

function formatMoment(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

const PRODUCTS_PAGE_SIZE = 12;
const SALES_PAGE_SIZE = 8;
const RETURNS_PAGE_SIZE = 8;
const SUPPLIERS_PAGE_SIZE = 12;
const PURCHASE_ORDERS_PAGE_SIZE = 8;

const OFFLINE_QUEUE_KEY = "centrofit.pos.offline-queue.v1";
const OFFLINE_SESSION_KEY = "centrofit.pos.session.v1";
const OFFLINE_PRODUCTS_KEY = "centrofit.pos.products.v1";

function readStoredJson<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeStoredJson(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // A full or disabled localStorage must not break the register.
  }
}

function isUnavailableStatus(status: number): boolean {
  return status === 502 || status === 503 || status === 504;
}

function adjustProductStock(
  products: BackendProduct[],
  items: { product_id: string; quantity: number }[],
  direction: 1 | -1,
): BackendProduct[] {
  return products.map((product) => {
    const item = items.find((line) => line.product_id === product.id);
    if (!item) return product;
    const stock = Math.max(0, product.stock + item.quantity * direction);
    const state: ProductState = stock <= 0 ? "out" : stock <= product.stock_min ? "low" : "active";
    return { ...product, stock, state };
  });
}

function newClientReference(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

const purchaseOrderStatusLabels: Record<string, string> = {
  created: "Creada",
  sent: "Enviada",
  received: "Recibida",
  cancelled: "Cancelada",
};

const purchaseOrderStatusBadges: Record<string, string> = {
  created: "status-neutral",
  sent: "status-warn",
  received: "status-good",
  cancelled: "status-bad",
};

const saleStatusLabels: Record<string, string> = {
  completed: "Completada",
  refunded: "Devuelta",
};

const saleStatusBadges: Record<string, string> = {
  completed: "status-good",
  refunded: "status-bad",
};

const productStateLabels: Record<ProductState, string> = {
  active: "Disponible",
  low: "Stock bajo",
  out: "Sin stock",
  inactive: "Inactivo",
};

const productStateBadges: Record<ProductState, string> = {
  active: "status-good",
  low: "status-warn",
  out: "status-bad",
  inactive: "status-neutral",
};

const paymentMethodLabels: Record<string, string> = {
  cash: "Efectivo",
  card: "Tarjeta",
  transfer: "Transferencia",
  account: "Cuenta del socio",
};

const statementDeliveryStatusLabels: Record<StatementDelivery["status"], string> = {
  sent: "Enviado",
  simulated: "Simulado",
  failed: "Fallido",
};

const statementDeliveryStatusBadges: Record<StatementDelivery["status"], string> = {
  sent: "status-good",
  simulated: "status-warn",
  failed: "status-bad",
};

const statementPurposeLabels: Record<StatementDelivery["purpose"], string> = {
  statement: "Estado de cuenta",
  reminder: "Recordatorio",
};

const reminderResultLabels: Record<StatementReminderResult["status"], string> = {
  sent: "Enviado",
  simulated: "Simulado",
  skipped: "Omitido",
  failed: "Fallido",
};

const reminderResultBadges: Record<StatementReminderResult["status"], string> = {
  sent: "status-good",
  simulated: "status-warn",
  skipped: "status-neutral",
  failed: "status-bad",
};

function formatMoney(cents: number): string {
  return new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" }).format(cents / 100);
}

function formatAgendaMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const hours = minutes / 60;
  return `${Number.isInteger(hours) ? hours : hours.toFixed(1)} h`;
}

function parseMoneyToCents(value: string): number | null {
  const normalized = value.replace(/[^0-9.]/g, "").trim();
  if (!normalized) return null;
  const amount = Number.parseFloat(normalized);
  if (Number.isNaN(amount) || amount < 0) return null;
  return Math.round(amount * 100);
}

function formatSaleTime(value: string): string {
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

// Pages open when the account holds any of the listed permissions. Personal is
// shared: whoever can clock in needs the «Mi jornada» tab even without access
// to the staff directory.
const requiredPermission: Record<PageName, string[]> = {
  Resumen: ["dashboard.read"],
  Accesos: ["access.read"],
  Socios: ["members.read"],
  Personal: ["staff.read", "attendance.self"],
  Clases: ["classes.read"],
  Fisioterapia: ["physio.read"],
  Rutinas: ["routines.read"],
  Inventario: ["inventory.read"],
  Mantenimiento: ["maintenance.read"],
  Facturación: ["billing.read"],
  Conciliación: ["finance.read"],
  Reportes: ["finance.read"],
  Kiosco: ["settings.manage"],
};

const roleLabels: Record<string, string> = {
  owner: "Dueño",
  manager: "Gerente",
  reception: "Recepción",
  trainer: "Entrenador",
  maintenance: "Mantenimiento",
  accountant: "Contador",
};

const primaryNavigation: { label: PageName; icon: LucideIcon }[] = [
  { label: "Resumen", icon: Home },
  { label: "Accesos", icon: DoorOpen },
  { label: "Socios", icon: Users },
  { label: "Personal", icon: Fingerprint },
  { label: "Clases", icon: CalendarDays },
  { label: "Fisioterapia", icon: Activity },
  { label: "Rutinas", icon: Dumbbell },
];

const operationsNavigation: { label: PageName; icon: LucideIcon }[] = [
  { label: "Inventario", icon: ShoppingBasket },
  { label: "Mantenimiento", icon: Wrench },
  { label: "Facturación", icon: Receipt },
  { label: "Conciliación", icon: Landmark },
  { label: "Reportes", icon: BarChart3 },
  { label: "Kiosco", icon: MonitorSmartphone },
];

const permissionRows = [
  { group: "Operación", label: "Panel operativo", code: "dashboard.read" },
  { group: "Socios", label: "Consultar directorio", code: "members.read" },
  { group: "Socios", label: "Crear y actualizar socios", code: "members.manage" },
  { group: "Accesos", label: "Consultar bitácora", code: "access.read" },
  { group: "Accesos", label: "Autorizar entrada manual", code: "access.manual_override" },
  { group: "Personal", label: "Consultar equipo", code: "staff.read" },
  { group: "Personal", label: "Administrar expedientes", code: "staff.manage" },
  { group: "Seguridad", label: "Administrar roles y permisos", code: "roles.manage" },
  { group: "Seguridad", label: "Administrar sesiones activas", code: "sessions.manage" },
  { group: "Asistencia", label: "Consultar asistencias", code: "attendance.read" },
  { group: "Asistencia", label: "Registrar y corregir", code: "attendance.manage" },
  { group: "Asistencia", label: "Marcar la propia asistencia", code: "attendance.self" },
  { group: "Clases", label: "Consultar clases", code: "classes.read" },
  { group: "Clases", label: "Administrar clases y reservas", code: "classes.manage" },
  { group: "Fisioterapia", label: "Consultar agenda y paquetes", code: "physio.read" },
  { group: "Fisioterapia", label: "Administrar citas, paquetes y catálogo", code: "physio.manage" },
  { group: "Fisioterapia", label: "Extender o anular paquetes", code: "physio.adjust" },
  { group: "Rutinas", label: "Consultar rutinas y progreso", code: "routines.read" },
  { group: "Rutinas", label: "Administrar rutinas y progreso", code: "routines.manage" },
  { group: "Inventario", label: "Consultar inventario", code: "inventory.read" },
  { group: "Inventario", label: "Administrar inventario", code: "inventory.manage" },
  { group: "Ventas", label: "Consultar ventas y cortes", code: "sales.read" },
  { group: "Ventas", label: "Registrar ventas y operar la caja", code: "sales.manage" },
  { group: "Ventas", label: "Administrar límites de crédito", code: "sales.credit" },
  { group: "Ventas", label: "Reembolsar servicios cobrados", code: "sales.service_refund" },
  { group: "Mantenimiento", label: "Consultar mantenimiento", code: "maintenance.read" },
  { group: "Mantenimiento", label: "Administrar mantenimiento", code: "maintenance.manage" },
  { group: "Mantenimiento", label: "Reportar fallas y marcar equipos fuera de servicio", code: "maintenance.report" },
  { group: "Finanzas", label: "Consultar reportes financieros", code: "finance.read" },
  { group: "Finanzas", label: "Conciliar pagos y cuentas bancarias", code: "finance.manage" },
  { group: "Facturación", label: "Consultar facturas y datos fiscales", code: "billing.read" },
  { group: "Facturación", label: "Solicitar facturas y capturar datos fiscales", code: "billing.request" },
  { group: "Facturación", label: "Timbrar y cancelar facturas", code: "billing.manage" },
  { group: "Finanzas", label: "Consultar nómina", code: "payroll.read" },
  { group: "Finanzas", label: "Administrar nómina", code: "payroll.manage" },
  { group: "Configuración", label: "Administrar configuración", code: "settings.manage" },
];

const permissionGroupByPrefix: Record<string, string> = {
  dashboard: "Operación",
  members: "Socios",
  access: "Accesos",
  staff: "Personal",
  roles: "Seguridad",
  sessions: "Seguridad",
  attendance: "Asistencia",
  classes: "Clases",
  physio: "Fisioterapia",
  routines: "Rutinas",
  inventory: "Inventario",
  sales: "Ventas",
  maintenance: "Mantenimiento",
  billing: "Facturación",
  payroll: "Finanzas",
  finance: "Finanzas",
  settings: "Configuración",
};

function permissionGroupFor(code: string): string {
  return permissionGroupByPrefix[code.split(".")[0]] ?? "Otros";
}

const hourlyTraffic = [
  { label: "06", value: 30 }, { label: "07", value: 52 }, { label: "08", value: 69 },
  { label: "09", value: 47 }, { label: "10", value: 80 }, { label: "11", value: 64 },
  { label: "12", value: 41 }, { label: "13", value: 58 }, { label: "14", value: 33 },
  { label: "15", value: 49 }, { label: "16", value: 74 }, { label: "17", value: 94 },
  { label: "18", value: 100 }, { label: "19", value: 76 }, { label: "20", value: 55 },
];

function formatDate() {
  return new Intl.DateTimeFormat("es-MX", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date());
}

export default function HomePage() {
  const [activePage, setActivePage] = useState<PageName>("Resumen");
  const [manualRefresh, setManualRefresh] = useState(0);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [recentAccess, setRecentAccess] = useState<BackendAccessEvent[]>([]);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [dashboardError, setDashboardError] = useState("");
  const [accessDirectory, setAccessDirectory] = useState<AccessDirectory | null>(null);
  const [accessLoading, setAccessLoading] = useState(false);
  const [accessError, setAccessError] = useState("");
  const [accessSearch, setAccessSearch] = useState("");
  const [accessQuery, setAccessQuery] = useState("");
  const [accessFilter, setAccessFilter] = useState<"Todos" | AccessState>("Todos");
  const [accessPage, setAccessPage] = useState(1);
  const [manualOpen, setManualOpen] = useState(false);
  const [newMemberOpen, setNewMemberOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notices, setNotices] = useState<BackendNotice[] | null>(null);
  const [unreadNotices, setUnreadNotices] = useState(0);
  const [noticesLoading, setNoticesLoading] = useState(false);
  const [noticesError, setNoticesError] = useState("");
  const [toast, setToast] = useState("");
  const [authState, setAuthState] = useState<"checking" | "signed_in" | "signed_out">("checking");
  const [currentUser, setCurrentUser] = useState<SessionUser | null>(null);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [backendStaff, setBackendStaff] = useState<BackendEmployee[] | null>(null);
  const [backendRoles, setBackendRoles] = useState<BackendRole[] | null>(null);
  const [permissionCatalog, setPermissionCatalog] = useState<PermissionCatalogEntry[] | null>(null);
  const [backendUsers, setBackendUsers] = useState<BackendUser[] | null>(null);
  const [backendSessions, setBackendSessions] = useState<BackendSession[] | null>(null);
  const [backendShifts, setBackendShifts] = useState<BackendShift[] | null>(null);
  const [myShifts, setMyShifts] = useState<BackendShift[] | null>(null);
  const [myAttendanceState, setMyAttendanceState] = useState<"hidden" | "loading" | "ready" | "unlinked" | "error">("hidden");
  const [myAttendancePolicy, setMyAttendancePolicy] = useState<AttendancePolicy>({ check_in_early_grace_minutes: 15, lateness_tolerance_minutes: 0 });
  const [staffLoading, setStaffLoading] = useState(false);
  const [staffError, setStaffError] = useState("");
  const [staffRefresh, setStaffRefresh] = useState(0);
  const [memberDirectory, setMemberDirectory] = useState<MemberDirectory | null>(null);
  const [membersLoading, setMembersLoading] = useState(false);
  const [membersError, setMembersError] = useState("");
  const [memberSearch, setMemberSearch] = useState("");
  const [memberQuery, setMemberQuery] = useState("");
  const [memberPage, setMemberPage] = useState(1);
  const [memberSort, setMemberSort] = useState<"name" | "plan" | "renewal">("name");
  const [memberDirection, setMemberDirection] = useState<"asc" | "desc">("asc");
  const [memberState, setMemberState] = useState<"" | "active" | "expiring_soon" | "frozen" | "pending">("");
  const [memberPlan, setMemberPlan] = useState("");
  const [activeMember, setActiveMember] = useState<BackendMember | null>(null);

  useEffect(() => {
    let active = true;
    fetch("/api/auth/me", { cache: "no-store" })
      .then(async (response) => (response.ok ? (await response.json() as SessionUser) : null))
      .then((user) => {
        if (!active) return;
        setCurrentUser(user);
        setAuthState(user ? "signed_in" : "signed_out");
      })
      .catch(() => {
        if (!active) return;
        setCurrentUser(null);
        setAuthState("signed_out");
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (authState !== "signed_in" || activePage !== "Personal" || !currentUser) return;
    let active = true;

    const loadPersonnelData = async () => {
      setStaffLoading(true);
      setStaffError("");
      setMyAttendanceState("loading");
      try {
        if (currentUser.permissions.includes("staff.read")) {
          const staffResponse = await fetch("/api/admin/staff", { cache: "no-store" });
          if (staffResponse.status === 401) {
            if (active) {
              setCurrentUser(null);
              setAuthState("signed_out");
            }
            return;
          }
          if (!staffResponse.ok) throw new Error("No se pudo consultar el directorio de personal.");
          const employees = await staffResponse.json() as BackendEmployee[];
          if (active) setBackendStaff(employees);
        } else {
          setBackendStaff(null);
        }

        if (currentUser.permissions.includes("attendance.read")) {
          const shiftsResponse = await fetch("/api/admin/staff/shifts?days=21", { cache: "no-store" });
          if (shiftsResponse.status === 401) {
            if (active) {
              setCurrentUser(null);
              setAuthState("signed_out");
            }
            return;
          }
          if (!shiftsResponse.ok) throw new Error("No se pudo consultar los turnos del personal.");
          const shifts = await shiftsResponse.json() as BackendShift[];
          if (active) setBackendShifts(shifts);
        } else if (active) {
          setBackendShifts(null);
        }

        if (currentUser.permissions.includes("attendance.self")) {
          const mineResponse = await fetch("/api/staff/attendance?days=14", { cache: "no-store" });
          if (mineResponse.status === 401) {
            if (active) {
              setCurrentUser(null);
              setAuthState("signed_out");
            }
            return;
          }
          if (mineResponse.status === 409) {
            if (active) {
              setMyShifts(null);
              setMyAttendanceState("unlinked");
            }
          } else if (!mineResponse.ok) {
            if (active) {
              setMyShifts(null);
              setMyAttendanceState("error");
            }
          } else {
            const board = await mineResponse.json() as MyAttendanceBoard;
            if (active) {
              setMyShifts(board.items);
              setMyAttendancePolicy(board.settings);
              setMyAttendanceState("ready");
            }
          }
        } else if (active) {
          setMyShifts(null);
          setMyAttendanceState("hidden");
        }

        if (currentUser.permissions.includes("roles.manage")) {
          const rolesResponse = await fetch("/api/admin/roles", { cache: "no-store" });
          if (rolesResponse.status === 401) {
            if (active) {
              setCurrentUser(null);
              setAuthState("signed_out");
            }
            return;
          }
          if (!rolesResponse.ok) throw new Error("No se pudo consultar la matriz de permisos.");
          const roles = await rolesResponse.json() as BackendRole[];
          if (active) setBackendRoles(roles);

          const catalogResponse = await fetch("/api/admin/permissions", { cache: "no-store" });
          if (catalogResponse.ok) {
            const catalog = await catalogResponse.json() as PermissionCatalogEntry[];
            if (active) setPermissionCatalog(catalog);
          }

          const usersResponse = await fetch("/api/admin/users", { cache: "no-store" });
          if (usersResponse.status === 401) {
            if (active) {
              setCurrentUser(null);
              setAuthState("signed_out");
            }
            return;
          }
          if (!usersResponse.ok) throw new Error("No se pudo consultar las cuentas de acceso.");
          const users = await usersResponse.json() as BackendUser[];
          if (active) setBackendUsers(users);
        } else if (active) {
          setBackendRoles(null);
          setPermissionCatalog(null);
          setBackendUsers(null);
        }

        if (currentUser.permissions.includes("sessions.manage")) {
          const sessionsResponse = await fetch("/api/admin/sessions", { cache: "no-store" });
          if (sessionsResponse.status === 401) {
            if (active) {
              setCurrentUser(null);
              setAuthState("signed_out");
            }
            return;
          }
          if (!sessionsResponse.ok) throw new Error("No se pudo consultar las sesiones activas.");
          const sessions = await sessionsResponse.json() as BackendSession[];
          if (active) setBackendSessions(sessions);
        } else if (active) {
          setBackendSessions(null);
        }
      } catch (error) {
        if (active) setStaffError(error instanceof Error ? error.message : "Error al cargar Personal.");
      } finally {
        if (active) setStaffLoading(false);
      }
    };

    void loadPersonnelData();
    return () => { active = false; };
  }, [activePage, authState, currentUser, staffRefresh]);

  useEffect(() => {
    const handle = window.setTimeout(() => setMemberQuery(memberSearch.trim()), 300);
    return () => window.clearTimeout(handle);
  }, [memberSearch]);

  useEffect(() => {
    setMemberPage(1);
  }, [memberQuery, memberSort, memberDirection, memberState, memberPlan]);

  useEffect(() => {
    if (authState !== "signed_in" || activePage !== "Socios" || !currentUser) return;
    let active = true;

    const loadMembers = async () => {
      setMembersLoading(true);
      setMembersError("");
      try {
        const params = new URLSearchParams({
          page: String(memberPage),
          page_size: String(MEMBERS_PAGE_SIZE),
          sort: memberSort,
          direction: memberDirection,
        });
        if (memberQuery) params.set("search", memberQuery);
        if (memberState) params.set("state", memberState);
        if (memberPlan) params.set("plan_id", memberPlan);
        const response = await fetch(`/api/admin/members?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) {
          if (active) {
            setCurrentUser(null);
            setAuthState("signed_out");
          }
          return;
        }
        if (!response.ok) throw new Error("No se pudo consultar el directorio de socios.");
        const directory = await response.json() as MemberDirectory;
        if (active) setMemberDirectory(directory);
      } catch (error) {
        if (active) setMembersError(error instanceof Error ? error.message : "Error al cargar Socios.");
      } finally {
        if (active) setMembersLoading(false);
      }
    };

    void loadMembers();
    return () => { active = false; };
  }, [activePage, authState, currentUser, manualRefresh, memberDirection, memberPage, memberPlan, memberQuery, memberSort, memberState]);

  useEffect(() => {
    const handle = window.setTimeout(() => setAccessQuery(accessSearch.trim()), 300);
    return () => window.clearTimeout(handle);
  }, [accessSearch]);

  useEffect(() => {
    setAccessPage(1);
  }, [accessQuery, accessFilter]);

  useEffect(() => {
    if (authState !== "signed_in" || activePage !== "Resumen" || !currentUser) return;
    let active = true;

    const loadDashboard = async () => {
      setDashboardLoading(true);
      setDashboardError("");
      try {
        const accessPromise = currentUser.permissions.includes("access.read")
          ? fetch("/api/admin/access-events?page=1&page_size=5", { cache: "no-store" })
          : Promise.resolve(null);
        const dashboardResponse = await fetch("/api/admin/dashboard", { cache: "no-store" });
        if (dashboardResponse.status === 401) {
          if (active) {
            setCurrentUser(null);
            setAuthState("signed_out");
          }
          return;
        }
        if (!dashboardResponse.ok) throw new Error("No se pudo consultar el resumen operativo.");
        const summary = await dashboardResponse.json() as DashboardData;

        let recent: BackendAccessEvent[] = [];
        const accessResponse = await accessPromise;
        if (accessResponse && accessResponse.ok) {
          recent = (await accessResponse.json() as AccessDirectory).items;
        }
        if (active) {
          setDashboard(summary);
          setRecentAccess(recent);
        }
      } catch (error) {
        if (active) setDashboardError(error instanceof Error ? error.message : "Error al cargar Resumen.");
      } finally {
        if (active) setDashboardLoading(false);
      }
    };

    void loadDashboard();
    return () => { active = false; };
  }, [activePage, authState, currentUser, manualRefresh]);

  useEffect(() => {
    if (authState !== "signed_in" || activePage !== "Accesos" || !currentUser) return;
    let active = true;

    const loadAccess = async () => {
      setAccessLoading(true);
      setAccessError("");
      try {
        const params = new URLSearchParams({ page: String(accessPage), page_size: String(ACCESS_PAGE_SIZE) });
        if (accessQuery) params.set("search", accessQuery);
        if (accessFilter !== "Todos") params.set("state", ACCESS_STATE_PARAMS[accessFilter]);
        const response = await fetch(`/api/admin/access-events?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) {
          if (active) {
            setCurrentUser(null);
            setAuthState("signed_out");
          }
          return;
        }
        if (!response.ok) throw new Error("No se pudo consultar la bitácora de accesos.");
        const directory = await response.json() as AccessDirectory;
        if (active) setAccessDirectory(directory);
      } catch (error) {
        if (active) setAccessError(error instanceof Error ? error.message : "Error al cargar Accesos.");
      } finally {
        if (active) setAccessLoading(false);
      }
    };

    void loadAccess();
    return () => { active = false; };
  }, [accessFilter, accessPage, accessQuery, activePage, authState, currentUser, manualRefresh]);

  const showToast = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 3000);
  };

  const handleSessionExpired = () => {
    setCurrentUser(null);
    setAuthState("signed_out");
  };

  const submitLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoginBusy(true);
    setLoginError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      });
      const payload = await response.json();
      if (!response.ok) {
        setLoginError(payload.detail || "No se pudo iniciar sesión.");
        return;
      }
      setCurrentUser(payload.user as SessionUser);
      setAuthState("signed_in");
      setLoginPassword("");
    } catch {
      setLoginError("No se pudo conectar con el servicio de identidad.");
    } finally {
      setLoginBusy(false);
    }
  };

  const logout = async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      setCurrentUser(null);
      setAuthState("signed_out");
      setActivePage("Resumen");
    }
  };

  const refreshUnreadNotices = async () => {
    try {
      const response = await fetch("/api/admin/notifications/unread-count", { cache: "no-store" });
      if (response.status === 401) {
        setAuthState("signed_out");
        return;
      }
      const payload = await response.json().catch(() => ({})) as { unread?: number };
      setUnreadNotices(response.ok ? payload.unread ?? 0 : 0);
    } catch {
      setUnreadNotices(0);
    }
  };

  useEffect(() => {
    if (authState !== "signed_in") {
      setUnreadNotices(0);
      setNotices(null);
      setNoticesError("");
      return;
    }
    void refreshUnreadNotices();
  }, [authState]);

  const loadNotices = async () => {
    setNoticesLoading(true);
    setNoticesError("");
    try {
      const response = await fetch("/api/admin/notifications?page_size=12", { cache: "no-store" });
      if (response.status === 401) {
        setAuthState("signed_out");
        return;
      }
      const payload = await response.json().catch(() => ({})) as {
        items?: BackendNotice[];
        unread_total?: number;
        detail?: string;
      };
      if (!response.ok) {
        setNoticesError(payload.detail || "No se pudo cargar la bandeja.");
        return;
      }
      setNotices(payload.items ?? []);
      setUnreadNotices(payload.unread_total ?? 0);
    } catch {
      setNoticesError("No se pudo conectar con el backend.");
    } finally {
      setNoticesLoading(false);
    }
  };

  const toggleNotices = () => {
    const next = !notificationsOpen;
    setNotificationsOpen(next);
    if (next) void loadNotices();
  };

  const markNoticeRead = async (notice: BackendNotice) => {
    if (notice.read_at) return;
    const stamped = new Date().toISOString();
    try {
      const response = await fetch(`/api/admin/notifications/${encodeURIComponent(notice.id)}/read`, { method: "POST" });
      if (response.status === 401) {
        setAuthState("signed_out");
        return;
      }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        showToast(payload.detail || "No se pudo marcar el aviso.");
        return;
      }
      setNotices((current) => (current ?? []).map((item) => (item.id === notice.id ? { ...item, read_at: stamped } : item)));
      // The badge counts pending work, not readings, so the server decides what is left.
      void refreshUnreadNotices();
    } catch {
      showToast("No se pudo conectar con el backend.");
    }
  };

  const markAllNoticesRead = async () => {
    const stamped = new Date().toISOString();
    try {
      const response = await fetch("/api/admin/notifications/read-all", { method: "POST" });
      if (response.status === 401) {
        setAuthState("signed_out");
        return;
      }
      const payload = await response.json().catch(() => ({})) as { updated?: number; detail?: string };
      if (!response.ok) {
        showToast(payload.detail || "No se pudo limpiar la bandeja.");
        return;
      }
      setNotices((current) => (current ?? []).map((item) => (item.read_at ? item : { ...item, read_at: stamped })));
      void refreshUnreadNotices();
      showToast(payload.updated ? `${payload.updated} aviso(s) marcados como leídos.` : "No había avisos sin leer.");
    } catch {
      showToast("No se pudo conectar con el backend.");
    }
  };

  const selectPage = (page: PageName) => {
    setActivePage(page);
    setMobileNavOpen(false);
    setAccessSearch("");
  };

  const toggleMemberSort = (field: "name" | "plan" | "renewal") => {
    if (memberSort === field) {
      setMemberDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setMemberSort(field);
    setMemberDirection("asc");
  };

  const toggleMemberState = (next: "" | "active" | "expiring_soon" | "frozen" | "pending") => {
    setMemberState((current) => (current === next ? "" : next));
  };

  const handleManualCreated = () => {
    setManualOpen(false);
    setManualRefresh((current) => current + 1);
    showToast("Acceso manual registrado en la bitácora.");
  };

  const handleMemberCreated = (fullName: string) => {
    setNewMemberOpen(false);
    setMemberPage(1);
    setManualRefresh((current) => current + 1);
    showToast(`Alta registrada: ${fullName}. Asigna su plan desde la ficha del socio (sin cobro).`);
  };

  const handleMemberChanged = (message: string) => {
    setManualRefresh((current) => current + 1);
    showToast(message);
  };

  const pageTitles: Record<PageName, string> = {
    Resumen: "Resumen operativo",
    Accesos: "Control de accesos",
    Socios: "Socios",
    Personal: "Equipo y turnos",
    Clases: "Clases",
    Fisioterapia: "Fisioterapia",
    Rutinas: "Rutinas y progreso",
    Inventario: "Inventario",
    Mantenimiento: "Mantenimiento de equipo",
    Facturación: "Facturación electrónica",
    Conciliación: "Conciliación bancaria",
    Reportes: "Panel de analítica y reportes",
    Kiosco: "Kiosco de recepción",
  };

  const hasPermission = (permission: string) => currentUser?.permissions.includes(permission) ?? false;
  const visiblePrimaryNavigation = primaryNavigation.filter(({ label }) => requiredPermission[label].some(hasPermission));
  const visibleOperationsNavigation = operationsNavigation.filter(({ label }) => requiredPermission[label].some(hasPermission));

  if (authState === "checking") return <SessionLoading />;
  if (authState === "signed_out" || !currentUser) {
    return (
      <LoginView
        email={loginEmail}
        password={loginPassword}
        error={loginError}
        busy={loginBusy}
        onEmailChange={setLoginEmail}
        onPasswordChange={setLoginPassword}
        onSubmit={submitLogin}
      />
    );
  }

  return (
    <div className="app-shell">
      {mobileNavOpen && <button className="mobile-scrim" aria-label="Cerrar menú" onClick={() => setMobileNavOpen(false)} />}
      <aside className={`sidebar ${mobileNavOpen ? "sidebar-open" : ""}`}>
        <div className="brand-lockup">
          <img className="brand-mark" src="/brand/centro-fit-mark.png" alt="" />
          <div className="brand-copy"><strong>CENTRO FIT</strong><span>CLUB DEPORTIVO</span></div>
          <button className="icon-button sidebar-close" aria-label="Cerrar menú" onClick={() => setMobileNavOpen(false)}><X size={18} /></button>
        </div>

        <div className="club-selector">
          <img className="club-avatar" src="/brand/centro-fit-mark.png" alt="" />
          <span className="club-text"><strong>Centro Fit</strong><small>Sucursal principal</small></span>
          <ChevronDown size={15} />
        </div>

        <nav aria-label="Navegación principal">
          <p className="nav-heading">OPERACIÓN</p>
          {visiblePrimaryNavigation.map(({ label, icon: Icon }) => (
            <button key={label} className={`nav-item ${activePage === label ? "nav-active" : ""}`} onClick={() => selectPage(label)}>
              <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
              {label === "Accesos" && <span className="nav-count">7</span>}
            </button>
          ))}

          <p className="nav-heading nav-heading-spaced">ADMINISTRACIÓN</p>
          {visibleOperationsNavigation.map(({ label, icon: Icon }) => (
            <button key={label} className={`nav-item ${activePage === label ? "nav-active" : ""}`} onClick={() => selectPage(label)}>
              <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-spacer" />
        <div className="sidebar-status">
          <div className="status-icon"><Wifi size={16} /></div>
          <div><strong>Control local activo</strong><span>Última sincronización · ahora</span></div>
          <span className="live-dot" />
        </div>
        {hasPermission("settings.manage") && <button className="nav-item settings-link" onClick={() => showToast("La configuración estará disponible en una siguiente iteración.")}><Settings size={18} /><span>Configuración</span></button>}
        <div className="profile-row">
          <div className="profile-avatar">{currentUser.email.slice(0, 2).toUpperCase()}</div>
          <div className="profile-copy"><strong>{currentUser.email}</strong><span>{roleLabels[currentUser.roles[0]] ?? "Colaborador"}</span></div>
          <button className="icon-button profile-menu" aria-label="Cerrar sesión" title="Cerrar sesión" onClick={logout}><LogOut size={17} /></button>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Abrir menú" onClick={() => setMobileNavOpen(true)}><Menu size={21} /></button>
          <div className="breadcrumbs"><span>Centro Fit</span><span className="breadcrumb-separator">/</span><strong>{pageTitles[activePage]}</strong></div>
          <div className="topbar-actions">
            <div className="preview-pill"><span />Vista previa · datos de muestra</div>
            <div className="notification-wrap">
              <button className={`icon-button notification-button ${notificationsOpen ? "icon-button-selected" : ""}`} aria-label={unreadNotices > 0 ? `Notificaciones, ${unreadNotices} por atender` : "Notificaciones"} onClick={toggleNotices}>
                <Bell size={19} />{unreadNotices > 0 && <i />}
              </button>
              {notificationsOpen && (
                <div className="notification-popover">
                  <div className="notification-head">
                    <strong>Notificaciones</strong>
                    <span>{unreadNotices > 0 ? `${unreadNotices} por atender` : "Todo atendido"}</span>
                  </div>
                  {noticesLoading && <p className="notification-state">Cargando…</p>}
                  {!noticesLoading && noticesError && <p className="notification-state notification-failed">{noticesError}</p>}
                  {!noticesLoading && !noticesError && notices !== null && notices.length === 0 && (
                    <p className="notification-state">Sin avisos por ahora.</p>
                  )}
                  {!noticesLoading && !noticesError && (notices ?? []).map((notice) => (
                    <button key={notice.id} className={`notification-item ${notice.resolved_at ? "is-attended" : notice.read_at ? "is-read" : "is-new"}`} onClick={() => void markNoticeRead(notice)}>
                      <span className={`notification-dot ${notice.resolved_at ? "lime-dot" : "coral-dot"}`} />
                      <span className="notification-copy">
                        <strong>
                          {notice.title}
                          {notice.resolved_at && <i className="notification-chip">Atendido</i>}
                        </strong>
                        <span>{notice.body}</span>
                        <em>{formatNoticeMoment(notice.created_at)}</em>
                      </span>
                    </button>
                  ))}
                  <div className="notification-actions">
                    <button onClick={() => void markAllNoticesRead()}>Marcar todo leído</button>
                    <button onClick={() => setNotificationsOpen(false)}>Listo</button>
                  </div>
                </div>
              )}
            </div>
            <button className="help-button" onClick={() => showToast("Centro de ayuda en preparación.")}><CircleHelp size={18} /><span>Ayuda</span></button>
          </div>
        </header>

        <div className="page-content">
          <div className="page-heading-row">
            <div>
              <p className="eyebrow">{formatDate()}</p>
              <h1>{pageTitles[activePage]}</h1>
              <p className="page-subtitle">Operación clara para que el gimnasio nunca pierda el ritmo.</p>
            </div>
            <div className="heading-actions">
              <button className="button button-secondary" onClick={() => showToast("Reporte de muestra preparado.")}><CalendarDays size={16} /><span>Hoy</span><ChevronDown size={14} /></button>
              {hasPermission("access.manual_override") && <button className="button button-primary" onClick={() => setManualOpen(true)}><Plus size={17} /><span>Acceso manual</span></button>}
            </div>
          </div>

          {activePage === "Resumen" && <DashboardView dashboard={dashboard} recentEvents={recentAccess.map(accessEventToDisplay).slice(0, 5)} canViewAccess={hasPermission("access.read")} loading={dashboardLoading} error={dashboardError} onNavigate={selectPage} onManual={() => setManualOpen(true)} canManual={hasPermission("access.manual_override")} />}
          {activePage === "Accesos" && (
            <AccessView
              directory={accessDirectory}
              loading={accessLoading}
              error={accessError}
              search={accessSearch}
              onSearch={setAccessSearch}
              filter={accessFilter}
              onFilter={setAccessFilter}
              page={accessPage}
              onPageChange={setAccessPage}
              onManual={() => hasPermission("access.manual_override") && setManualOpen(true)}
              canManual={hasPermission("access.manual_override")}
            />
          )}
          {activePage === "Socios" && (
            <MembersView
              directory={memberDirectory}
              loading={membersLoading}
              error={membersError}
              search={memberSearch}
              onSearch={setMemberSearch}
              sort={memberSort}
              direction={memberDirection}
              state={memberState}
              plan={memberPlan}
              onSort={toggleMemberSort}
              onState={toggleMemberState}
              onPlan={setMemberPlan}
              page={memberPage}
              onPageChange={setMemberPage}
              onCreate={() => hasPermission("members.manage") && setNewMemberOpen(true)}
              onOpenMember={(member) => hasPermission("members.manage") && setActiveMember(member)}
            />
          )}
          {activePage === "Personal" && <StaffView onToast={showToast} currentUserId={currentUser.id} canViewStaff={hasPermission("staff.read")} canManageRoles={hasPermission("roles.manage")} canManageSessions={hasPermission("sessions.manage")} canManageStaff={hasPermission("staff.manage")} canViewAttendance={hasPermission("attendance.read")} canManageAttendance={hasPermission("attendance.manage")} canSelfAttendance={hasPermission("attendance.self")} employees={backendStaff} roles={backendRoles} permissionCatalog={permissionCatalog} users={backendUsers} sessions={backendSessions} shifts={backendShifts} myShifts={myShifts} myAttendanceState={myAttendanceState} myAttendancePolicy={myAttendancePolicy} loading={staffLoading} error={staffError} onIdentityChanged={() => setStaffRefresh((value) => value + 1)} />}
          {activePage === "Inventario" && <InventoryView permissions={currentUser.permissions} onUnauthorized={handleSessionExpired} onToast={showToast} />}
          {activePage === "Clases" && <ClassesView permissions={currentUser.permissions} onUnauthorized={handleSessionExpired} onToast={showToast} />}
          {activePage === "Fisioterapia" && <PhysioView permissions={currentUser.permissions} onUnauthorized={handleSessionExpired} onToast={showToast} />}
          {activePage === "Rutinas" && <RoutinesView permissions={currentUser.permissions} onUnauthorized={handleSessionExpired} onToast={showToast} onNotificationsChanged={() => { void refreshUnreadNotices(); if (notificationsOpen) void loadNotices(); }} />}
          {activePage === "Mantenimiento" && <MaintenanceView permissions={currentUser.permissions} onUnauthorized={handleSessionExpired} onToast={showToast} />}
          {activePage === "Facturación" && <BillingView permissions={currentUser.permissions} onUnauthorized={handleSessionExpired} onToast={showToast} />}
          {activePage === "Conciliación" && <ReconciliationView permissions={currentUser.permissions} onUnauthorized={handleSessionExpired} onToast={showToast} />}
          {activePage === "Reportes" && <ReportsView permissions={currentUser.permissions} onUnauthorized={handleSessionExpired} onToast={showToast} />}
          {activePage === "Kiosco" && <KioskView permissions={currentUser.permissions} onUnauthorized={handleSessionExpired} onToast={showToast} />}
        </div>
      </main>

      {manualOpen && hasPermission("access.manual_override") && <ManualAccessModal onClose={() => setManualOpen(false)} onCreated={handleManualCreated} />}
      {newMemberOpen && hasPermission("members.manage") && <NewMemberModal onClose={() => setNewMemberOpen(false)} onCreated={handleMemberCreated} />}
      {activeMember && hasPermission("members.manage") && <MemberModal member={activeMember} onClose={() => setActiveMember(null)} onChanged={handleMemberChanged} />}
      {toast && <div className="toast"><span className="toast-check"><Check size={14} /></span>{toast}</div>}
    </div>
  );
}

function DashboardView({ dashboard, recentEvents, canViewAccess, loading, error, onNavigate, onManual, canManual }: { dashboard: DashboardData | null; recentEvents: AccessEvent[]; canViewAccess: boolean; loading: boolean; error: string; onNavigate: (page: PageName) => void; onManual: () => void; canManual: boolean }) {
  const members = dashboard?.members;
  const access = dashboard?.access;
  const attentionCount = (members?.expiring_soon ?? 0) + (members?.pending ?? 0) + (canViewAccess ? access?.denied_today ?? 0 : 0);

  return (
    <>
      <section className="pulse-banner">
        <div className="pulse-banner-copy">
          <div className="pulse-live"><span className="live-dot" />OPERACIÓN EN CURSO</div>
          <h2>Todo en movimiento.</h2>
          <p>La entrada principal está activa. El equipo de recepción está en turno.</p>
        </div>
        <div className="pulse-illustration" aria-hidden="true">
          <div className="pulse-ring ring-one" /><div className="pulse-ring ring-two" />
          <Activity size={39} strokeWidth={1.35} />
          <span className="pulse-caption">RITMO <b>01</b></span>
        </div>
        <div className="banner-meta"><span>ESTADO DE RED</span><strong><i className="live-dot" /> Estable</strong><small>Última revisión 10:43</small></div>
      </section>

      <section className="metric-grid" aria-label="Indicadores del día">
        <Metric icon={Users} label="Socios activos" value={metricValue(members?.active, loading)} change="" detail={members ? `${members.total} socios en el club` : "sin datos"} trend="neutral" tone="lime" />
        {canViewAccess
          ? <Metric icon={DoorOpen} label="Accesos hoy" value={metricValue(access?.entries_today, loading)} change="" detail={access ? `${access.denied_today} denegados` : "sin datos"} trend={access && access.denied_today > 0 ? "alert" : "neutral"} tone="coral" />
          : <Metric icon={Activity} label="Membresías congeladas" value={metricValue(members?.frozen, loading)} change="" detail="en pausa" trend="neutral" tone="blue" />}
        <Metric icon={Clock3} label="Por vencer" value={metricValue(members?.expiring_soon, loading)} change="" detail="próximos 7 días" trend="alert" tone="yellow" />
        <Metric icon={ShieldAlert} label="Altas pendientes" value={metricValue(members?.pending, loading)} change="" detail="requieren seguimiento" trend="neutral" tone="blue" />
      </section>

      <div className="dashboard-grid">
        <section className="panel access-panel">
          <div className="panel-header">
            <div><p className="section-kicker">MOVIMIENTO EN TIEMPO REAL</p><h2>Últimos accesos</h2></div>
            <button className="text-button" onClick={() => onNavigate("Accesos")}>Ver todos <ArrowRight size={15} /></button>
          </div>
          {canViewAccess ? <AccessTable events={recentEvents} compact /> : <p className="role-empty">Tu perfil no tiene permiso para consultar la bitácora de accesos.</p>}
          <div className="panel-footer"><span><i className="live-dot" />{loading ? "Actualizando…" : "Bitácora del backend"}</span>{canManual && <button className="button button-small button-secondary" onClick={onManual}><Plus size={14} />Registrar entrada</button>}</div>
        </section>

        <section className="panel occupancy-panel">
          <div className="panel-header">
            <div><p className="section-kicker">CAPACIDAD DEL CLUB</p><h2>Aforo por zona</h2></div>
            <button className="icon-button small-icon" aria-label="Más opciones de aforo"><MoreHorizontal size={18} /></button>
          </div>
          <div className="occupancy-summary"><strong>82<span> / 120</span></strong><span className="occupancy-percent">68%</span></div>
          <div className="occupancy-track"><span style={{ width: "68%" }} /></div>
          <p className="occupancy-note"><span className="note-marker" />Dentro de la capacidad recomendada</p>
          <div className="zone-list">
            <Zone label="Zona de fuerza" value="38 / 50" percent={76} tone="tone-lime" />
            <Zone label="Cardio" value="21 / 35" percent={60} tone="tone-coral" />
            <Zone label="Salones" value="23 / 35" percent={66} tone="tone-blue" />
          </div>
          <button className="text-button occupancy-link" onClick={() => onNavigate("Accesos")}>Ver mapa de aforo <ArrowRight size={15} /></button>
        </section>
      </div>

      <div className="dashboard-grid lower-grid">
        <section className="panel traffic-panel">
          <div className="panel-header">
            <div><p className="section-kicker">ENTRADAS POR HORA</p><h2>Ritmo del día</h2></div>
            <span className="chart-legend"><i />Socios registrados</span>
          </div>
          <div className="traffic-chart" role="img" aria-label="Gráfica de accesos por hora">
            {hourlyTraffic.map((item) => <div className="chart-column" key={item.label}><div className={`chart-bar ${item.label === "18" ? "chart-bar-highlight" : ""}`} style={{ height: `${item.value}%` }} /><span>{item.label}</span></div>)}
          </div>
          <div className="chart-foot"><span>06:00</span><span>HORA LOCAL</span><span>20:00</span></div>
        </section>

        <section className="panel attention-panel">
          <div className="panel-header">
            <div><p className="section-kicker">PARA DAR SEGUIMIENTO</p><h2>Atención pendiente</h2></div>
            <span className="attention-count">{attentionCount}</span>
          </div>
          <button className="attention-row" onClick={() => onNavigate("Socios")}>
            <span className="attention-icon attention-yellow"><Clock3 size={17} /></span>
            <span className="attention-copy"><strong>Renovación próxima</strong><small>{members?.expiring_soon ?? 0} socios vencen en 7 días</small></span>
            <ArrowRight size={15} />
          </button>
          <button className="attention-row" onClick={() => onNavigate("Socios")}>
            <span className="attention-icon attention-blue"><Users size={17} /></span>
            <span className="attention-copy"><strong>Altas pendientes</strong><small>{members?.pending ?? 0} socios por completar</small></span>
            <ArrowRight size={15} />
          </button>
          {canViewAccess && (
            <button className="attention-row" onClick={() => onNavigate("Accesos")}>
              <span className="attention-icon attention-coral"><ShieldAlert size={17} /></span>
              <span className="attention-copy"><strong>Accesos denegados hoy</strong><small>{access?.denied_today ?? 0} intentos rechazados</small></span>
              <ArrowRight size={15} />
            </button>
          )}
          <button className="attention-link" onClick={() => onNavigate("Socios")}>Abrir directorio de socios <ArrowRight size={14} /></button>
        </section>
      </div>

      {error && <p className="role-empty" role="alert">{error}</p>}
      <footer className="page-footer"><span>Centro Fit · Panel operativo</span><span>ACCESOS Y SOCIOS DEL BACKEND · AFORO Y GRÁFICA DE MUESTRA</span></footer>
    </>
  );
}

function Metric({ icon: Icon, label, value, change, detail, trend, tone }: { icon: LucideIcon; label: string; value: string; change: string; detail: string; trend: "up" | "neutral" | "alert"; tone: string }) {
  return (
    <article className="metric">
      <div className="metric-top"><span className={`metric-icon ${tone}`}><Icon size={17} strokeWidth={1.8} /></span><span className={`metric-change ${trend}`}>{trend === "up" ? <ArrowUpRight size={13} /> : trend === "alert" ? <ArrowDownRight size={13} /> : null}{change}</span></div>
      <p>{label}</p><strong>{value}</strong><small>{detail}</small>
    </article>
  );
}

function Zone({ label, value, percent, tone }: { label: string; value: string; percent: number; tone: string }) {
  return <div className="zone-row"><div className="zone-label"><span>{label}</span><strong>{value}</strong></div><div className="zone-track"><span className={tone} style={{ width: `${percent}%` }} /></div></div>;
}

function AccessTable({ events, compact = false }: { events: AccessEvent[]; compact?: boolean }) {
  return (
    <div className={`table-scroll ${compact ? "compact-table" : ""}`}>
      <table className="data-table access-data-table">
        <thead><tr><th>SOCIO</th><th>HORA</th><th>LECTOR</th><th>RESULTADO</th><th aria-label="Detalle" /></tr></thead>
        <tbody>
          {events.map((event, index) => (
            <tr key={`${event.name}-${event.time}-${index}`}>
              <td><div className="person-cell"><span className={`person-avatar ${event.color}`}>{event.initials}</span><span><strong>{event.name}</strong><small>{event.plan}</small></span></div></td>
              <td className="time-cell">{event.time}</td>
              <td className="reader-cell">{event.reader}</td>
              <td><StatusBadge state={event.state} detail={event.reason} /></td>
              <td><button className="icon-button row-menu" aria-label={`Opciones de ${event.name}`}><MoreHorizontal size={17} /></button></td>
            </tr>
          ))}
          {events.length === 0 && <tr><td colSpan={5} className="empty-row">No hay accesos para estos filtros.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ state, detail }: { state: AccessState | string; detail?: string }) {
  const statusClass = state === "Autorizado" || state === "Activa" || state === "Activo" || state === "En turno" || state === "Programado" || state === "Presente"
    ? "status-good"
    : state === "Manual" || state === "Por vencer" || state === "Pago pendiente" || state === "Congelada" || state === "Tarde"
      ? "status-warn"
      : state === "Denegado" || state === "Vencida" || state === "Baja" || state === "Suspendida" || state === "Cancelada" || state === "Cancelado" || state === "Caducado"
        ? "status-bad"
        : "status-neutral";
  return <span className={`status-badge ${statusClass}`} title={detail}><i />{state}</span>;
}

function AccessView({ directory, loading, error, search, onSearch, filter, onFilter, page, onPageChange, onManual, canManual }: { directory: AccessDirectory | null; loading: boolean; error: string; search: string; onSearch: (value: string) => void; filter: "Todos" | AccessState; onFilter: (value: "Todos" | AccessState) => void; page: number; onPageChange: (page: number) => void; onManual: () => void; canManual: boolean }) {
  const events = (directory?.items ?? []).map(accessEventToDisplay);
  const summary = directory?.summary ?? { total: 0, authorized: 0, denied: 0, manual: 0 };
  const total = directory?.total ?? 0;
  const pages = directory?.pages ?? 0;

  return (
    <>
      <section className="access-summary-band">
        <div className="access-summary-main"><span className="summary-icon"><DoorOpen size={20} /></span><div><span>BITÁCORA DEL CLUB</span><strong>Decisiones de acceso registradas</strong></div><span className="live-dot" /></div>
        <div className="summary-divider" />
        <div className="summary-stat"><span>AUTORIZADOS</span><strong>{summary.authorized}</strong></div>
        <div className="summary-stat"><span>DENEGADOS</span><strong className="summary-alert">{summary.denied}</strong></div>
        <div className="summary-stat"><span>MANUALES</span><strong>{summary.manual}</strong></div>
      </section>

      <section className="panel full-panel">
        <div className="panel-header access-list-heading"><div><p className="section-kicker">BITÁCORA DEL BACKEND</p><h2>Movimientos registrados</h2></div>{canManual && <button className="button button-primary" onClick={onManual}><Plus size={17} />Acceso manual</button>}</div>
        <div className="table-toolbar">
          <label className="table-search"><Search size={17} /><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Buscar socio, correo o lector" /></label>
          <div className="filter-tabs" role="group" aria-label="Filtrar accesos">
            {(["Todos", "Autorizado", "Denegado", "Manual"] as const).map((item) => <button key={item} className={filter === item ? "filter-active" : ""} onClick={() => onFilter(item)}>{item}</button>)}
          </div>
        </div>
        {loading
          ? <p className="role-empty">Cargando bitácora…</p>
          : error
            ? <p className="role-empty" role="alert">{error}</p>
            : <AccessTable events={events} />}
        <div className="table-bottom">
          <span>{total} {total === 1 ? "movimiento" : "movimientos"} registrados</span>
          {pages > 1 && (
            <span className="member-pagination">
              <span>Página {page} de {pages}</span>
              <button type="button" aria-label="Página anterior" disabled={page <= 1} onClick={() => onPageChange(Math.max(1, page - 1))}>‹</button>
              <button type="button" aria-label="Página siguiente" disabled={page >= pages} onClick={() => onPageChange(Math.min(pages, page + 1))}>›</button>
            </span>
          )}
        </div>
      </section>

      <div className="access-bottom-grid">
        <section className="panel access-health-panel"><div className="panel-header"><div><p className="section-kicker">ESTADO DE DISPOSITIVOS</p><h2>Lectores y puertas</h2></div></div><div className="device-note"><Wifi size={15} />Los lectores físicos aún no están conectados; la bitácora refleja las decisiones registradas por el sistema.</div></section>
        <section className="panel occupancy-mini-panel"><div className="panel-header"><div><p className="section-kicker">AFORO GENERAL</p><h2>Ahora mismo</h2></div></div><p className="occupancy-note"><span className="note-marker" />Sin sensores de aforo conectados.</p></section>
      </div>
      <footer className="page-footer"><span>Centro Fit · Control de accesos</span><span>BITÁCORA DEL BACKEND · AFORO Y HARDWARE NO CONECTADOS</span></footer>
    </>
  );
}

function KioskView({ permissions, onUnauthorized, onToast }: { permissions: string[]; onUnauthorized: () => void; onToast: (message: string) => void }) {
  const canManage = permissions.includes("settings.manage");
  const [devices, setDevices] = useState<KioskDevice[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [creating, setCreating] = useState(false);
  const [newToken, setNewToken] = useState<string | null>(null);
  const [createdLabel, setCreatedLabel] = useState("");
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [rotatingId, setRotatingId] = useState<string | null>(null);
  const [confirmRotateId, setConfirmRotateId] = useState<string | null>(null);
  const [plans, setPlans] = useState<BackendPlan[] | null>(null);
  const [planDrafts, setPlanDrafts] = useState<Record<string, string>>({});
  const [savingPlanId, setSavingPlanId] = useState<string | null>(null);
  const [plansError, setPlansError] = useState("");
  const [accessSettings, setAccessSettings] = useState<AccessSettings | null>(null);
  const [antipassbackDraft, setAntipassbackDraft] = useState("");
  const [savingAntipassback, setSavingAntipassback] = useState(false);
  const [maxOccupancyDraft, setMaxOccupancyDraft] = useState("");
  const [occupancyMinutesDraft, setOccupancyMinutesDraft] = useState("120");
  const [savingOccupancy, setSavingOccupancy] = useState(false);
  const [accessSettingsError, setAccessSettingsError] = useState("");
  const [schedulePlan, setSchedulePlan] = useState<BackendPlan | null>(null);
  const [scheduleRows, setScheduleRows] = useState<ScheduleDraftRow[]>([]);
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [scheduleError, setScheduleError] = useState("");

  const loadPlans = async () => {
    setPlansError("");
    try {
      const response = await fetch("/api/admin/plans", { cache: "no-store" });
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      const payload = await response.json().catch(() => ({})) as BackendPlan[] | { detail?: string };
      if (!response.ok || !Array.isArray(payload)) {
        throw new Error((payload as { detail?: string }).detail || "No se pudieron cargar los planes.");
      }
      setPlans(payload);
      setPlanDrafts(Object.fromEntries(
        payload.map((plan) => [plan.id, plan.daily_entry_limit == null ? "" : String(plan.daily_entry_limit)]),
      ));
    } catch (loadError) {
      setPlansError(loadError instanceof Error ? loadError.message : "No se pudieron cargar los planes.");
    }
  };

  const loadDevices = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/admin/kiosk/devices", { cache: "no-store" });
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      const payload = await response.json().catch(() => ({})) as { items?: KioskDevice[]; detail?: string };
      if (!response.ok) throw new Error(payload.detail || "No se pudieron cargar los kioscos.");
      setDevices(payload.items ?? []);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "No se pudieron cargar los kioscos.");
    } finally {
      setLoading(false);
    }
  };

  const applyAccessSettings = (payload: AccessSettings) => {
    setAccessSettings(payload);
    setAntipassbackDraft(String(payload.antipassback_seconds));
    setMaxOccupancyDraft(payload.max_occupancy == null ? "" : String(payload.max_occupancy));
    setOccupancyMinutesDraft(String(Math.round(payload.occupancy_window_seconds / 60)));
  };

  const loadAccessSettings = async () => {
    setAccessSettingsError("");
    try {
      const response = await fetch("/api/admin/access/settings", { cache: "no-store" });
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      const payload = await response.json().catch(() => ({})) as AccessSettings & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "No se pudo cargar la política de acceso.");
      applyAccessSettings(payload);
    } catch (loadError) {
      setAccessSettingsError(loadError instanceof Error ? loadError.message : "No se pudo cargar la política de acceso.");
    }
  };

  useEffect(() => {
    if (canManage) {
      void loadDevices();
      void loadPlans();
      void loadAccessSettings();
    }
  }, []);

  const createDevice = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const label = newLabel.trim();
    if (!label || creating) return;
    setCreating(true);
    setError("");
    try {
      const response = await fetch("/api/admin/kiosk/devices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label }),
      });
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      const payload = await response.json().catch(() => ({})) as KioskDeviceCreated & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "No se pudo crear el kiosco.");
      setDevices((current) => [payload, ...(current ?? [])]);
      setNewToken(payload.token);
      setCreatedLabel(payload.label);
      setNewLabel("");
      onToast(`Kiosco ${payload.label} creado. Copia el token ahora.`);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "No se pudo crear el kiosco.");
    } finally {
      setCreating(false);
    }
  };

  const revokeDevice = async (device: KioskDevice) => {
    if (!window.confirm(`¿Revocar «${device.label}»? Dejará de validar códigos hasta que configures uno nuevo.`)) {
      return;
    }
    setRevokingId(device.id);
    setError("");
    try {
      const response = await fetch(`/api/admin/kiosk/devices/${encodeURIComponent(device.id)}/revoke`, { method: "POST" });
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      const payload = await response.json().catch(() => ({})) as KioskDevice & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "No se pudo revocar el kiosco.");
      setDevices((current) => current?.map((item) => (item.id === device.id ? payload : item)) ?? current);
      onToast(`Kiosco ${device.label} revocado.`);
    } catch (revokeError) {
      setError(revokeError instanceof Error ? revokeError.message : "No se pudo revocar el kiosco.");
    } finally {
      setRevokingId(null);
    }
  };

  const rotateDevice = async (device: KioskDevice) => {
    setConfirmRotateId(null);
    setRotatingId(device.id);
    setError("");
    try {
      const response = await fetch(`/api/admin/kiosk/devices/${encodeURIComponent(device.id)}/rotate-token`, { method: "POST" });
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      const payload = await response.json().catch(() => ({})) as KioskDeviceCreated & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "No se pudo rotar el token.");
      setDevices((current) => current?.map((item) => (item.id === device.id ? payload : item)) ?? current);
      setNewToken(payload.token);
      setCreatedLabel(payload.label);
      onToast(`Token de ${device.label} rotado. Captúralo en el kiosco ahora.`);
    } catch (rotateError) {
      setError(rotateError instanceof Error ? rotateError.message : "No se pudo rotar el token.");
    } finally {
      setRotatingId(null);
    }
  };

  const copyToken = async () => {
    if (!newToken) return;
    try {
      await navigator.clipboard.writeText(newToken);
      onToast("Token copiado al portapapeles.");
    } catch {
      onToast("No se pudo copiar automáticamente; selecciona el token y cópialo.");
    }
  };

  const savePlanLimit = async (plan: BackendPlan) => {
    const raw = (planDrafts[plan.id] ?? "").trim();
    const limit = raw === "" ? null : Number(raw);
    if (limit !== null && (!Number.isInteger(limit) || limit < 1)) {
      onToast("El límite debe ser un entero mayor o igual a 1, o quedar vacío.");
      return;
    }
    setSavingPlanId(plan.id);
    try {
      const response = await fetch(`/api/admin/plans/${encodeURIComponent(plan.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ daily_entry_limit: limit }),
      });
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      const payload = await response.json().catch(() => ({})) as BackendPlan & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "No se pudo guardar el límite.");
      setPlans((current) => current?.map((item) => (item.id === plan.id ? payload : item)) ?? current);
      setPlanDrafts((current) => ({
        ...current,
        [plan.id]: payload.daily_entry_limit == null ? "" : String(payload.daily_entry_limit),
      }));
      onToast(payload.daily_entry_limit == null
        ? `Límite diario de ${plan.name} retirado.`
        : `${plan.name}: ${payload.daily_entry_limit} ${payload.daily_entry_limit === 1 ? "entrada" : "entradas"} por día.`);
    } catch (saveError) {
      onToast(saveError instanceof Error ? saveError.message : "No se pudo guardar el límite.");
    } finally {
      setSavingPlanId(null);
    }
  };

  const saveAntipassback = async () => {
    if (accessSettings == null) return;
    const raw = antipassbackDraft.trim();
    const seconds = Number(raw);
    if (!Number.isInteger(seconds) || seconds < 0 || seconds > 3600) {
      onToast("La ventana debe ser un entero entre 0 y 3600 segundos.");
      return;
    }
    setSavingAntipassback(true);
    try {
      const response = await fetch("/api/admin/access/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          antipassback_seconds: seconds,
          max_occupancy: accessSettings.max_occupancy,
          occupancy_window_seconds: accessSettings.occupancy_window_seconds,
        }),
      });
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      const payload = await response.json().catch(() => ({})) as AccessSettings & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "No se pudo guardar el control de duplicados.");
      applyAccessSettings(payload);
      onToast(payload.antipassback_seconds === 0
        ? "Control de duplicados desactivado."
        : `Control de duplicados activo: ${payload.antipassback_seconds} segundos.`);
    } catch (saveError) {
      onToast(saveError instanceof Error ? saveError.message : "No se pudo guardar el control de duplicados.");
    } finally {
      setSavingAntipassback(false);
    }
  };

  const saveOccupancy = async () => {
    if (accessSettings == null) return;
    const raw = maxOccupancyDraft.trim();
    const max = raw === "" ? null : Number(raw);
    if (max !== null && (!Number.isInteger(max) || max < 1 || max > 10000)) {
      onToast("El aforo debe ser un entero entre 1 y 10000, o quedar vacío para no limitar.");
      return;
    }
    const minutes = Number(occupancyMinutesDraft.trim());
    if (!Number.isInteger(minutes) || minutes < 5 || minutes > 1440) {
      onToast("El tiempo de estancia debe ser un entero entre 5 y 1440 minutos.");
      return;
    }
    setSavingOccupancy(true);
    try {
      const response = await fetch("/api/admin/access/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          antipassback_seconds: accessSettings.antipassback_seconds,
          max_occupancy: max,
          occupancy_window_seconds: minutes * 60,
        }),
      });
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      const payload = await response.json().catch(() => ({})) as AccessSettings & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "No se pudo guardar el aforo.");
      applyAccessSettings(payload);
      onToast(payload.max_occupancy == null
        ? "Aforo desactivado: el kiosco no limita la ocupación."
        : `Aforo del club: ${payload.max_occupancy} socios; cada entrada cuenta ${Math.round(payload.occupancy_window_seconds / 60)} minutos.`);
    } catch (saveError) {
      onToast(saveError instanceof Error ? saveError.message : "No se pudo guardar el aforo.");
    } finally {
      setSavingOccupancy(false);
    }
  };

  const openSchedule = (plan: BackendPlan) => {
    setSchedulePlan(plan);
    setScheduleError("");
    setScheduleRows(plan.access_windows.map((window, index) => ({
      key: `${index}-${newClientReference()}`,
      weekday: window.weekday,
      starts_at: window.starts_at.slice(0, 5),
      ends_at: window.ends_at.slice(0, 5),
    })));
  };

  const closeSchedule = () => {
    setSchedulePlan(null);
    setScheduleRows([]);
    setScheduleError("");
  };

  const addScheduleRow = () => {
    const last = scheduleRows[scheduleRows.length - 1];
    setScheduleRows((current) => [
      ...current,
      {
        key: newClientReference(),
        weekday: last?.weekday ?? 0,
        starts_at: last?.ends_at ?? "06:00",
        ends_at: "22:00",
      },
    ]);
  };

  const saveSchedule = async () => {
    if (!schedulePlan) return;
    if (scheduleRows.some((row) => !row.starts_at || !row.ends_at)) {
      setScheduleError("Cada ventana necesita hora de inicio y de fin.");
      return;
    }
    if (scheduleRows.some((row) => row.starts_at === row.ends_at)) {
      setScheduleError("La hora de inicio y la de fin no pueden ser iguales; quita la ventana para un acceso libre.");
      return;
    }
    setSavingSchedule(true);
    setScheduleError("");
    try {
      const response = await fetch(`/api/admin/plans/${encodeURIComponent(schedulePlan.id)}/access-windows`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          windows: scheduleRows.map((row) => ({
            weekday: row.weekday,
            starts_at: `${row.starts_at}:00`,
            ends_at: `${row.ends_at}:00`,
          })),
        }),
      });
      if (response.status === 401) {
        onUnauthorized();
        return;
      }
      const payload = await response.json().catch(() => ({})) as BackendPlan & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || "No se pudo guardar el horario.");
      setPlans((current) => current?.map((item) => (item.id === payload.id ? payload : item)) ?? current);
      onToast(payload.access_windows.length === 0
        ? `${payload.name}: acceso libre todo el día.`
        : `${payload.name}: ${payload.access_windows.length} ${payload.access_windows.length === 1 ? "ventana de acceso" : "ventanas de acceso"}.`);
      closeSchedule();
    } catch (saveError) {
      setScheduleError(saveError instanceof Error ? saveError.message : "No se pudo guardar el horario.");
    } finally {
      setSavingSchedule(false);
    }
  };

  if (!canManage) {
    return (
      <section className="panel full-panel">
        <p className="panel-hint">Solo el dueño puede administrar los kioscos de recepción.</p>
      </section>
    );
  }

  const activeCount = (devices ?? []).filter((device) => device.status === "active").length;

  return (
    <div className="kiosk-stack">
      <section className="panel full-panel">
        <div className="panel-header access-list-heading">
          <div>
            <p className="section-kicker">ACCESO EN RECEPCIÓN</p>
            <h2>Kioscos autorizados</h2>
          </div>
          <span className="role-count">{activeCount}</span>
        </div>
        <p className="panel-hint">
          Cada tablet de recepción valida el código de seis dígitos que muestra la app del socio.
          El token se muestra una sola vez al crear el dispositivo o al rotarlo; guárdalo en la
          pantalla de configuración del kiosco y revócalo si el equipo se retira. Los tokens
          caducan a los 90 días: rota el token antes de que venza.
        </p>
        {error && <div className="login-error" role="alert">{error}</div>}
        <form className="inline-form" onSubmit={createDevice}>
          <label className="form-field inline-grow">
            <span>Nombre del kiosco</span>
            <input
              value={newLabel}
              onChange={(event) => setNewLabel(event.target.value)}
              placeholder="Ej. Recepción principal"
              maxLength={80}
              required
            />
          </label>
          <button type="submit" className="button button-primary" disabled={creating || !newLabel.trim()}>
            <Plus size={16} />{creating ? "Creando…" : "Crear kiosco"}
          </button>
        </form>
      </section>

      {newToken && (
        <section className="panel full-panel kiosk-token-panel" role="status">
          <div className="panel-header">
            <div>
              <p className="section-kicker">TOKEN DE INSTALACIÓN</p>
              <h2>Guárdalo ahora: no se vuelve a mostrar</h2>
            </div>
          </div>
          <p className="panel-hint">
            Captúralo en la pantalla de configuración del kiosco «{createdLabel}». Si lo pierdes,
            rota el token del dispositivo: el anterior deja de funcionar.
          </p>
          <div className="kiosk-token-row">
            <code className="kiosk-token">{newToken}</code>
            <button type="button" className="button button-secondary" onClick={() => void copyToken()}>Copiar</button>
            <button type="button" className="button button-secondary" onClick={() => setNewToken(null)}>Listo</button>
          </div>
        </section>
      )}

      <section className="panel full-panel">
        {confirmRotateId && (() => {
          const target = (devices ?? []).find((device) => device.id === confirmRotateId);
          if (!target) return null;
          return (
            <div className="kiosk-rotate-confirm" role="alert">
              <p>
                ¿Rotar el token de «{target.label}»? El token actual dejará de funcionar de
                inmediato y la tablet volverá a su pantalla de configuración.
              </p>
              <div className="pos-row-actions">
                <button type="button" className="button button-primary" disabled={rotatingId === target.id} onClick={() => void rotateDevice(target)}>
                  {rotatingId === target.id ? "Rotando…" : "Confirmar rotación"}
                </button>
                <button type="button" className="button button-secondary" disabled={rotatingId === target.id} onClick={() => setConfirmRotateId(null)}>
                  Cancelar
                </button>
              </div>
            </div>
          );
        })()}
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>KIOSCO</th>
                <th>ESTADO</th>
                <th>ALTA</th>
                <th>TOKEN VENCE</th>
                <th>ÚLTIMA ACTIVIDAD</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {loading && devices === null ? <tr><td colSpan={6} className="empty-row">Cargando kioscos…</td></tr>
                : devices === null ? <tr><td colSpan={6} className="empty-row">No se pudieron cargar los kioscos.</td></tr>
                : devices.length === 0 ? <tr><td colSpan={6} className="empty-row">Aún no hay kioscos registrados.</td></tr>
                : devices.map((device) => {
                  const busy = revokingId === device.id || rotatingId === device.id;
                  const expiry = kioskTokenExpiry(device.token_expires_at);
                  const state = device.status === "revoked"
                    ? "Revocado"
                    : expiry.expired ? "Caducado" : expiry.soon ? "Por vencer" : "Activo";
                  return (
                    <tr key={device.id}>
                      <td>
                        <div className="person-cell">
                          <span className="pos-row-icon"><MonitorSmartphone size={15} /></span>
                          <span>
                            <strong>{device.label}</strong>
                            <small>{device.id.slice(0, 8)}</small>
                          </span>
                        </div>
                      </td>
                      <td><StatusBadge state={state} /></td>
                      <td className="time-cell">{formatSessionTime(device.created_at)}</td>
                      <td className="time-cell">{expiry.label}</td>
                      <td className="time-cell">{device.last_seen_at ? formatSessionTime(device.last_seen_at) : "Sin uso"}</td>
                      <td>
                        {device.status === "active" && (
                          <div className="pos-row-actions">
                            <button type="button" className="button button-secondary" disabled={busy} onClick={() => setConfirmRotateId(device.id)}>
                              Rotar token
                            </button>
                            <button type="button" className="button button-secondary" disabled={busy} onClick={() => void revokeDevice(device)}>
                              {revokingId === device.id ? "Revocando…" : "Revocar"}
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
        <div className="table-bottom">
          <span>{(devices ?? []).length} {(devices ?? []).length === 1 ? "kiosco registrado" : "kioscos registrados"}</span>
          <span>Token SHA-256 · intentos limitados por dispositivo</span>
        </div>
      </section>

      <section className="panel full-panel">
        <div className="panel-header access-list-heading">
          <div>
            <p className="section-kicker">POLÍTICA DE ACCESO</p>
            <h2>Límite diario de entradas</h2>
          </div>
          <span className="role-count">{(plans ?? []).filter((plan) => plan.daily_entry_limit != null).length}</span>
        </div>
        <p className="panel-hint">
          El kiosco cuenta las entradas autorizadas del día del club, incluidas las que recepción
          registra a mano, y rechaza el código cuando el socio ya alcanzó el límite de su plan.
          Deja el campo vacío para un plan sin límite. Una entrada manual siempre se permite y
          solo suma al conteo.
        </p>
        {plansError && <div className="login-error" role="alert">{plansError}</div>}
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>PLAN</th>
                <th>DURACIÓN</th>
                <th>ENTRADAS POR DÍA</th>
                <th>ESTADO</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {plans === null ? <tr><td colSpan={5} className="empty-row">{plansError ? "No se pudieron cargar los planes." : "Cargando planes…"}</td></tr>
                : plans.length === 0 ? <tr><td colSpan={5} className="empty-row">No hay planes activos.</td></tr>
                : plans.map((plan) => {
                  const saving = savingPlanId === plan.id;
                  const draft = planDrafts[plan.id] ?? "";
                  const unchanged = draft === (plan.daily_entry_limit == null ? "" : String(plan.daily_entry_limit));
                  return (
                    <tr key={plan.id}>
                      <td><strong>{plan.name}</strong></td>
                      <td>{plan.duration_days} días</td>
                      <td>
                        <input
                          className="kiosk-limit-input"
                          type="number"
                          min={1}
                          step={1}
                          inputMode="numeric"
                          placeholder="Sin límite"
                          value={draft}
                          disabled={saving}
                          aria-label={`Entradas por día del plan ${plan.name}`}
                          onChange={(event) => setPlanDrafts((current) => ({ ...current, [plan.id]: event.target.value }))}
                        />
                      </td>
                      <td>{plan.daily_entry_limit == null ? "Sin límite" : `${plan.daily_entry_limit} al día`}</td>
                      <td>
                        <button type="button" className="button button-secondary" disabled={saving || unchanged} onClick={() => void savePlanLimit(plan)}>
                          {saving ? "Guardando…" : "Guardar"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel full-panel">
        <div className="panel-header access-list-heading">
          <div>
            <p className="section-kicker">POLÍTICA DE ACCESO</p>
            <h2>Horario de acceso</h2>
          </div>
          <span className="role-count">{(plans ?? []).filter((plan) => plan.access_windows.length > 0).length}</span>
        </div>
        <p className="panel-hint">
          El kiosco rechaza el código fuera de las ventanas del plan con «Estás fuera del horario
          permitido.». Un plan sin ventanas queda abierto todo el día, así que configurarlas es lo
          que cambia el comportamiento. Los días van de lunes a domingo y las horas se interpretan en
          el huso horario del club; una ventana cuya hora de fin es menor que la de inicio cruza la
          medianoche.
        </p>
        {plansError && <div className="login-error" role="alert">{plansError}</div>}
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>PLAN</th>
                <th>VENTANAS</th>
                <th>ESTADO</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {plans === null ? <tr><td colSpan={4} className="empty-row">{plansError ? "No se pudieron cargar los planes." : "Cargando planes…"}</td></tr>
                : plans.length === 0 ? <tr><td colSpan={4} className="empty-row">No hay planes activos.</td></tr>
                : plans.map((plan) => (
                  <tr key={plan.id}>
                    <td><strong>{plan.name}</strong></td>
                    <td className="kiosk-schedule-summary">{planScheduleSummary(plan.access_windows)}</td>
                    <td>
                      {plan.access_windows.length === 0
                        ? "Sin restricción"
                        : `${plan.access_windows.length} ${plan.access_windows.length === 1 ? "ventana" : "ventanas"}`}
                    </td>
                    <td>
                      <button type="button" className="button button-secondary" disabled={savingSchedule} onClick={() => openSchedule(plan)}>
                        Editar horario
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        <div className="table-bottom">
          <span>Horas del club · hasta 28 ventanas por plan</span>
          <span>Una ventana se aplica al día que empieza</span>
        </div>
      </section>

      <section className="panel full-panel">
        <div className="panel-header access-list-heading">
          <div>
            <p className="section-kicker">POLÍTICA DE ACCESO</p>
            <h2>Control de duplicados</h2>
          </div>
          <span className="role-count">{accessSettings == null ? "…" : accessSettings.antipassback_seconds === 0 ? "Off" : `${accessSettings.antipassback_seconds}s`}</span>
        </div>
        <p className="panel-hint">
          Bloquea un segundo código del mismo socio dentro de la ventana contada desde su última
          entrada autorizada, incluidas las entradas manuales de recepción. Usa <strong>0</strong>
          para desactivarlo. La entrada manual de recepción nunca se bloquea; solo cuenta para la
          ventana del kiosco.
        </p>
        {accessSettingsError && <div className="login-error" role="alert">{accessSettingsError}</div>}
        <div className="kiosk-antipassback-row">
          <label htmlFor="antipassback-seconds">Ventana en segundos</label>
          <input
            id="antipassback-seconds"
            className="kiosk-limit-input"
            type="number"
            min={0}
            max={3600}
            step={5}
            inputMode="numeric"
            value={antipassbackDraft}
            disabled={savingAntipassback || accessSettings == null}
            onChange={(event) => setAntipassbackDraft(event.target.value)}
          />
          <span className="kiosk-antipassback-state">
            {accessSettings == null
              ? "Cargando…"
              : accessSettings.antipassback_seconds === 0
                ? "Desactivado: se permiten entradas seguidas."
                : `Activo: espera ${accessSettings.antipassback_seconds} segundos entre entradas del mismo socio.`}
          </span>
          <button
            type="button"
            className="button button-secondary"
            disabled={savingAntipassback || accessSettings == null || antipassbackDraft === String(accessSettings.antipassback_seconds)}
            onClick={() => void saveAntipassback()}
          >
            {savingAntipassback ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </section>

      <section className="panel full-panel">
        <div className="panel-header access-list-heading">
          <div>
            <p className="section-kicker">POLÍTICA DE ACCESO</p>
            <h2>Aforo del club</h2>
          </div>
          <span className="role-count">
            {accessSettings == null
              ? "…"
              : accessSettings.max_occupancy == null
                ? "Off"
                : `${accessSettings.max_occupancy} socios`}
          </span>
        </div>
        <p className="panel-hint">
          El kiosco niega la entrada cuando la ocupación estimada alcanza el aforo. Cuenta como
          «dentro» a cada socio cuya última entrada autorizada —del kiosco o de recepción— cae
          dentro del tiempo de estancia; si vuelve a entrar, su visita se renueva. Deja el aforo
          vacío para no limitarlo. La estimación no sustituye un registro de salidas: quien se
          queda más tiempo se cuenta como que ya salió.
        </p>
        <div className="kiosk-occupancy-row">
          <label htmlFor="max-occupancy">Aforo máximo</label>
          <input
            id="max-occupancy"
            className="kiosk-limit-input"
            type="number"
            min={1}
            max={10000}
            step={1}
            inputMode="numeric"
            placeholder="Sin límite"
            value={maxOccupancyDraft}
            disabled={savingOccupancy || accessSettings == null}
            onChange={(event) => setMaxOccupancyDraft(event.target.value)}
          />
          <span className="kiosk-antipassback-state">
            {accessSettings == null
              ? "Cargando…"
              : accessSettings.max_occupancy == null
                ? "Desactivado: no se limita la ocupación."
                : `Activo: hasta ${accessSettings.max_occupancy} socios dentro del club.`}
          </span>
        </div>
        <div className="kiosk-occupancy-row">
          <label htmlFor="occupancy-minutes">Tiempo de estancia (minutos)</label>
          <input
            id="occupancy-minutes"
            className="kiosk-limit-input"
            type="number"
            min={5}
            max={1440}
            step={5}
            inputMode="numeric"
            value={occupancyMinutesDraft}
            disabled={savingOccupancy || accessSettings == null}
            onChange={(event) => setOccupancyMinutesDraft(event.target.value)}
          />
          <span className="kiosk-antipassback-state">
            {accessSettings == null
              ? "Cargando…"
              : `Cada entrada cuenta ${Math.round(accessSettings.occupancy_window_seconds / 60)} minutos.`}
          </span>
          <button
            type="button"
            className="button button-secondary"
            disabled={
              savingOccupancy
              || accessSettings == null
              || (maxOccupancyDraft === (accessSettings.max_occupancy == null ? "" : String(accessSettings.max_occupancy))
                && occupancyMinutesDraft === String(Math.round(accessSettings.occupancy_window_seconds / 60)))
            }
            onClick={() => void saveOccupancy()}
          >
            {savingOccupancy ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </section>

      <section className="panel full-panel">
        <div className="panel-header">
          <div>
            <p className="section-kicker">CÓMO FUNCIONA</p>
            <h2>Flujo de entrada del socio</h2>
          </div>
        </div>
        <p className="panel-hint">
          El socio abre «Acceso habilitado» en su app y muestra el código vigente. Recepción lo
          captura en el kiosco: el sistema valida la membresía con el mismo motor de accesos y
          registra la entrada o el motivo del rechazo en la bitácora. El código caduca a los cinco
          minutos y solo se puede usar una vez.
        </p>
      </section>

      {schedulePlan && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => { if (event.target === event.currentTarget && !savingSchedule) closeSchedule(); }}
        >
          <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="plan-schedule-title">
            <div className="modal-header">
              <span className="modal-icon"><Clock3 size={19} /></span>
              <button type="button" className="icon-button" aria-label="Cerrar" disabled={savingSchedule} onClick={closeSchedule}><X size={19} /></button>
            </div>
            <p className="section-kicker">HORARIO DE ACCESO</p>
            <h2 id="plan-schedule-title">{schedulePlan.name}</h2>
            <p className="modal-subtitle">
              Sin ventanas el plan queda abierto todo el día. Una ventana que termina antes de
              empezar cruza la medianoche y sigue aplicando al día en que empezó.
            </p>
            <div className="kiosk-schedule-rows">
              {scheduleRows.length === 0
                ? <p className="kiosk-schedule-empty">Este plan no tiene ventanas: el kiosco permite la entrada a cualquier hora.</p>
                : scheduleRows.map((row) => (
                  <div className="kiosk-schedule-row" key={row.key}>
                    <select
                      className="kiosk-schedule-select"
                      value={row.weekday}
                      disabled={savingSchedule}
                      aria-label="Día de la ventana"
                      onChange={(event) => setScheduleRows((current) => current.map((item) => item.key === row.key ? { ...item, weekday: Number(event.target.value) } : item))}
                    >
                      {scheduleWeekdayLabels.map((label, index) => <option key={label} value={index}>{label}</option>)}
                    </select>
                    <input
                      type="time"
                      className="kiosk-schedule-time"
                      value={row.starts_at}
                      disabled={savingSchedule}
                      aria-label="Hora de inicio de la ventana"
                      onChange={(event) => setScheduleRows((current) => current.map((item) => item.key === row.key ? { ...item, starts_at: event.target.value } : item))}
                    />
                    <span className="kiosk-schedule-separator">a</span>
                    <input
                      type="time"
                      className="kiosk-schedule-time"
                      value={row.ends_at}
                      disabled={savingSchedule}
                      aria-label="Hora de fin de la ventana"
                      onChange={(event) => setScheduleRows((current) => current.map((item) => item.key === row.key ? { ...item, ends_at: event.target.value } : item))}
                    />
                    <button
                      type="button"
                      className="icon-button"
                      aria-label="Quitar ventana"
                      disabled={savingSchedule}
                      onClick={() => setScheduleRows((current) => current.filter((item) => item.key !== row.key))}
                    >
                      <Trash2 size={17} />
                    </button>
                  </div>
                ))}
            </div>
            <div className="kiosk-schedule-actions">
              <button type="button" className="button button-secondary" disabled={savingSchedule || scheduleRows.length >= 28} onClick={addScheduleRow}>
                <Plus size={16} />Agregar ventana
              </button>
              <button type="button" className="button button-secondary" disabled={savingSchedule || scheduleRows.length === 0} onClick={() => setScheduleRows([])}>
                Quitar todas
              </button>
            </div>
            {scheduleError && <div className="login-error" role="alert">{scheduleError}</div>}
            <div className="modal-actions">
              <button type="button" className="button button-secondary" disabled={savingSchedule} onClick={closeSchedule}>Cancelar</button>
              <button type="button" className="button button-primary" disabled={savingSchedule} onClick={() => void saveSchedule()}>
                <Check size={16} />{savingSchedule ? "Guardando…" : "Guardar horario"}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function memberDisplayStatus(member: BackendMember): string {
  if (!member.membership_status) return "Sin membresía";
  if (member.membership_status === "active" && member.membership_ends_at) {
    const endsAt = new Date(member.membership_ends_at).getTime();
    const sevenDays = 7 * 24 * 60 * 60 * 1000;
    if (!Number.isNaN(endsAt) && endsAt - Date.now() <= sevenDays) return "Por vencer";
  }
  return membershipStatusLabels[member.membership_status] ?? member.membership_status;
}

function formatRenewalDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

function formatSessionTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function kioskTokenExpiry(value: string | null): { label: string; expired: boolean; soon: boolean } {
  if (!value) return { label: "Sin caducidad", expired: false, soon: false };
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return { label: "Sin caducidad", expired: false, soon: false };
  const days = Math.ceil((date.getTime() - Date.now()) / 86_400_000);
  if (days <= 0) return { label: `Caducó el ${formatRenewalDate(value)}`, expired: true, soon: false };
  if (days <= 15) return { label: `Vence en ${days} ${days === 1 ? "día" : "días"}`, expired: false, soon: true };
  return { label: formatRenewalDate(value), expired: false, soon: false };
}

function shiftDayLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const today = new Date();
  const sameDay = date.getFullYear() === today.getFullYear() && date.getMonth() === today.getMonth() && date.getDate() === today.getDate();
  if (sameDay) return "Hoy";
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short" }).format(date);
}

function shiftClock(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("es-MX", { hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

type SelfMark = { action: "check_in" | "check_out" | null; hint: string };

function selfMarkFor(shift: BackendShift, now: number, earlyGraceMinutes: number): SelfMark {
  if (shift.status !== "scheduled") return { action: null, hint: "Turno cancelado" };
  const start = new Date(shift.starts_at).getTime();
  const end = new Date(shift.ends_at).getTime();
  if (!shift.attendance) {
    if (now < start - earlyGraceMinutes * 60 * 1000) return { action: null, hint: `Abre ${earlyGraceMinutes} min antes` };
    if (now > end) return { action: null, hint: "Turno cerrado · recepción puede registrarlo" };
    return { action: "check_in", hint: "Puedes marcar tu entrada" };
  }
  if (!shift.attendance.check_out_at) return { action: "check_out", hint: "Puedes marcar tu salida" };
  return { action: null, hint: "Jornada completa" };
}

function attendanceLabel(attendance: BackendAttendance | null): string {
  if (!attendance) return "Sin registro";
  const suffix = (source: string | null) => source === "manual" ? " (manual)" : source === "correction" ? " (corregido)" : "";
  const entry = `${shiftClock(attendance.check_in_at)}${suffix(attendance.check_in_source)}`;
  if (!attendance.check_out_at) return `${entry} · en turno`;
  return `${entry} → ${shiftClock(attendance.check_out_at)}${suffix(attendance.check_out_source)}`;
}

type MemberStateFilter = "" | "active" | "expiring_soon" | "frozen" | "pending";

function MembersView({ directory, loading, error, search, onSearch, sort, direction, state, plan, onSort, onState, onPlan, page, onPageChange, onCreate, onOpenMember }: { directory: MemberDirectory | null; loading: boolean; error: string; search: string; onSearch: (value: string) => void; sort: "name" | "plan" | "renewal"; direction: "asc" | "desc"; state: MemberStateFilter; plan: string; onSort: (field: "name" | "plan" | "renewal") => void; onState: (value: MemberStateFilter) => void; onPlan: (value: string) => void; page: number; onPageChange: (page: number) => void; onCreate: () => void; onOpenMember: (member: BackendMember) => void }) {
  const members = directory?.items ?? [];
  const summary = directory?.summary ?? { active: 0, expiring_soon: 0, frozen: 0, pending: 0 };
  const planOptions = directory?.plans ?? [];
  const total = directory?.total ?? 0;
  const pages = directory?.pages ?? 0;
  const hasFilters = Boolean(search) || Boolean(state) || Boolean(plan);

  const clearFilters = () => { onSearch(""); onState(""); onPlan(""); };

  const sortableHeader = (field: "name" | "plan" | "renewal", label: string) => (
    <th className="sortable-header">
      <button type="button" onClick={() => onSort(field)} aria-label={`Ordenar por ${label.toLowerCase()}`}>
        {label}
        {sort === field && <span className="sort-indicator">{direction === "asc" ? "▲" : "▼"}</span>}
      </button>
    </th>
  );

  return (
    <>
      <section className="member-stat-row" role="group" aria-label="Filtrar socios por estado">
        <button type="button" className={state === "active" ? "member-stat-active" : ""} onClick={() => onState(state === "active" ? "" : "active")}><span>SOCIOS ACTIVOS</span><strong>{summary.active}</strong><small>membresías vigentes</small></button>
        <button type="button" className={state === "expiring_soon" ? "member-stat-active" : ""} onClick={() => onState(state === "expiring_soon" ? "" : "expiring_soon")}><span>POR VENCER</span><strong className="stat-orange">{summary.expiring_soon}</strong><small>próximos 7 días</small></button>
        <button type="button" className={state === "frozen" ? "member-stat-active" : ""} onClick={() => onState(state === "frozen" ? "" : "frozen")}><span>EN PAUSA</span><strong>{summary.frozen}</strong><small>membresías congeladas</small></button>
        <button type="button" className={state === "pending" ? "member-stat-active" : ""} onClick={() => onState(state === "pending" ? "" : "pending")}><span>ALTAS PENDIENTES</span><strong>{summary.pending}</strong><small>requieren seguimiento</small></button>
      </section>
      <section className="panel full-panel">
        <div className="panel-header access-list-heading"><div><p className="section-kicker">DIRECTORIO</p><h2>Socios del club</h2></div><button className="button button-primary" onClick={onCreate}><Plus size={17} />Nuevo socio</button></div>
        <div className="table-toolbar"><label className="table-search"><Search size={17} /><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Buscar por nombre, correo, teléfono o plan" /></label>{planOptions.length > 0 && <label className="table-select"><span>Plan</span><select value={plan} onChange={(event) => onPlan(event.target.value)}><option value="">Todos los planes</option>{planOptions.map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}</select></label>}{hasFilters ? <button className="button button-secondary" onClick={clearFilters}>Limpiar filtros</button> : <span className="table-hint">Ordena por columna y filtra por estado o plan</span>}</div>
        <div className="table-scroll"><table className="data-table"><thead><tr>{sortableHeader("name", "SOCIO")}{sortableHeader("plan", "MEMBRESÍA")}<th>ESTADO</th>{sortableHeader("renewal", "RENOVACIÓN")}<th /></tr></thead><tbody>
          {loading ? <tr><td colSpan={5} className="empty-row">Cargando directorio…</td></tr>
            : error ? <tr><td colSpan={5} className="empty-row">{error}</td></tr>
            : members.length === 0 ? <tr><td colSpan={5} className="empty-row">{hasFilters ? "No hay socios que coincidan con el filtro." : "No se encontraron socios."}</td></tr>
            : members.map((member) => {
                const fullName = `${member.first_name} ${member.last_name}`;
                const initials = `${member.first_name[0] ?? ""}${member.last_name[0] ?? ""}`.toUpperCase();
                return <tr key={member.id}><td><div className="person-cell"><span className={`person-avatar ${memberAvatarColor(member.id)}`}>{initials}</span><span><strong>{fullName}</strong><small>{member.email ?? member.phone ?? "Sin contacto"}</small></span></div></td><td>{member.plan_name ?? "Sin plan"}</td><td><StatusBadge state={memberDisplayStatus(member)} /></td><td className="time-cell">{formatRenewalDate(member.membership_ends_at)}</td><td><button className="icon-button row-menu" aria-label={`Opciones de ${fullName}`} onClick={() => onOpenMember(member)}><MoreHorizontal size={17} /></button></td></tr>;
              })}
        </tbody></table></div>
        <div className="table-bottom">
          <span>{total} {total === 1 ? "socio" : "socios"} en el directorio</span>
          {pages > 1 && (
            <span className="member-pagination">
              <span>Página {page} de {pages}</span>
              <button type="button" aria-label="Página anterior" disabled={page <= 1} onClick={() => onPageChange(Math.max(1, page - 1))}>‹</button>
              <button type="button" aria-label="Página siguiente" disabled={page >= pages} onClick={() => onPageChange(Math.min(pages, page + 1))}>›</button>
            </span>
          )}
        </div>
      </section>
      <footer className="page-footer"><span>Centro Fit · Directorio de socios</span><span>DATOS DEL BACKEND · PAGOS NO CONECTADOS</span></footer>
    </>
  );
}

function StaffView({ onToast, currentUserId, canViewStaff, canManageRoles, canManageSessions, canManageStaff, canViewAttendance, canManageAttendance, canSelfAttendance, employees, roles, permissionCatalog, users, sessions, shifts, myShifts, myAttendanceState, myAttendancePolicy, loading, error, onIdentityChanged }: { onToast: (message: string) => void; currentUserId: string; canViewStaff: boolean; canManageRoles: boolean; canManageSessions: boolean; canManageStaff: boolean; canViewAttendance: boolean; canManageAttendance: boolean; canSelfAttendance: boolean; employees: BackendEmployee[] | null; roles: BackendRole[] | null; permissionCatalog: PermissionCatalogEntry[] | null; users: BackendUser[] | null; sessions: BackendSession[] | null; shifts: BackendShift[] | null; myShifts: BackendShift[] | null; myAttendanceState: "hidden" | "loading" | "ready" | "unlinked" | "error"; myAttendancePolicy: AttendancePolicy; loading: boolean; error: string; onIdentityChanged: () => void }) {
  const [activeTab, setActiveTab] = useState<"equipo" | "jornada" | "roles" | "usuarios" | "sesiones">(canViewStaff ? "equipo" : "jornada");
  const [selectedRoleCode, setSelectedRoleCode] = useState("reception");
  const [busyUserId, setBusyUserId] = useState<string | null>(null);
  const [busySessionId, setBusySessionId] = useState<string | null>(null);
  const [busyPermission, setBusyPermission] = useState<string | null>(null);
  const [newEmployeeOpen, setNewEmployeeOpen] = useState(false);
  const [newShiftOpen, setNewShiftOpen] = useState(false);
  const [manualShift, setManualShift] = useState<BackendShift | null>(null);
  const [correctionShift, setCorrectionShift] = useState<BackendShift | null>(null);
  const [logShift, setLogShift] = useState<BackendShift | null>(null);
  const [voidShift, setVoidShift] = useState<BackendShift | null>(null);
  const [policy, setPolicy] = useState<AttendancePolicy | null>(null);
  const [policyGrace, setPolicyGrace] = useState("");
  const [policyTolerance, setPolicyTolerance] = useState("");
  const [policyBusy, setPolicyBusy] = useState(false);
  const [busyMarkShiftId, setBusyMarkShiftId] = useState<string | null>(null);
  const [requestShift, setRequestShift] = useState<BackendShift | null>(null);
  const [decisionRequest, setDecisionRequest] = useState<AttendanceRequest | null>(null);
  const [policyHistoryOpen, setPolicyHistoryOpen] = useState(false);
  const [requestsRefresh, setRequestsRefresh] = useState(0);
  const [myRequests, setMyRequests] = useState<AttendanceRequest[] | null>(null);
  const [myRequestsError, setMyRequestsError] = useState("");
  const [pendingRequests, setPendingRequests] = useState<AttendanceRequest[] | null>(null);
  const [requestsError, setRequestsError] = useState("");
  const [annulmentDays, setAnnulmentDays] = useState(30);
  const [annulmentReport, setAnnulmentReport] = useState<AttendanceAnnulmentReport | null>(null);
  const [annulmentError, setAnnulmentError] = useState("");
  const refreshStaffing = () => { setRequestsRefresh((value) => value + 1); onIdentityChanged(); };
  const pendingMarks = useRef(new Map<string, string>());
  const [clockNow, setClockNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setClockNow(Date.now()), 15000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!canManageAttendance) return;
    let active = true;
    void (async () => {
      try {
        const response = await fetch("/api/admin/staff/settings", { cache: "no-store" });
        if (!response.ok) return;
        const settings = await response.json() as AttendancePolicy;
        if (!active) return;
        setPolicy(settings);
        setPolicyGrace(String(settings.check_in_early_grace_minutes));
        setPolicyTolerance(String(settings.lateness_tolerance_minutes));
      } catch {
        // The card stays read-only until the settings endpoint responds.
      }
    })();
    return () => { active = false; };
  }, [canManageAttendance]);
  useEffect(() => {
    if (!canSelfAttendance) return;
    let active = true;
    void (async () => {
      try {
        const response = await fetch("/api/staff/attendance/requests", { cache: "no-store" });
        if (!active) return;
        if (!response.ok) {
          setMyRequestsError("No se pudieron cargar tus solicitudes.");
          return;
        }
        const payload = await response.json() as { items: AttendanceRequest[] };
        setMyRequests(payload.items);
        setMyRequestsError("");
      } catch {
        if (active) setMyRequestsError("No se pudieron cargar tus solicitudes.");
      }
    })();
    return () => { active = false; };
  }, [canSelfAttendance, requestsRefresh]);
  useEffect(() => {
    if (!canViewAttendance) return;
    let active = true;
    void (async () => {
      try {
        const response = await fetch("/api/admin/staff/attendance/requests?status=pending", { cache: "no-store" });
        if (!active) return;
        if (!response.ok) {
          setRequestsError("No se pudieron cargar las solicitudes del equipo.");
          return;
        }
        const payload = await response.json() as { items: AttendanceRequest[] };
        setPendingRequests(payload.items);
        setRequestsError("");
      } catch {
        if (active) setRequestsError("No se pudieron cargar las solicitudes del equipo.");
      }
    })();
    return () => { active = false; };
  }, [canViewAttendance, requestsRefresh]);
  useEffect(() => {
    if (!canViewAttendance) return;
    let active = true;
    void (async () => {
      try {
        const response = await fetch(`/api/admin/staff/attendance/annulments?days=${annulmentDays}`, { cache: "no-store" });
        if (!active) return;
        if (!response.ok) {
          setAnnulmentError("No se pudo cargar el reporte de anulaciones.");
          return;
        }
        const report = await response.json() as AttendanceAnnulmentReport;
        setAnnulmentReport(report);
        setAnnulmentError("");
      } catch {
        if (active) setAnnulmentError("No se pudo cargar el reporte de anulaciones.");
      }
    })();
    return () => { active = false; };
  }, [canViewAttendance, annulmentDays, requestsRefresh]);
  const saveAttendancePolicy = async () => {
    const grace = Number(policyGrace);
    const tolerance = Number(policyTolerance);
    if (!Number.isInteger(grace) || grace < 0 || grace > 240 || !Number.isInteger(tolerance) || tolerance < 0 || tolerance > 240) {
      onToast("Los minutos deben ser enteros entre 0 y 240.");
      return;
    }
    setPolicyBusy(true);
    try {
      const response = await fetch("/api/admin/staff/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ check_in_early_grace_minutes: grace, lateness_tolerance_minutes: tolerance }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        onToast(payload.detail || "No se pudo guardar la política de asistencia.");
        return;
      }
      const settings = await response.json() as AttendancePolicy;
      setPolicy(settings);
      setPolicyGrace(String(settings.check_in_early_grace_minutes));
      setPolicyTolerance(String(settings.lateness_tolerance_minutes));
      onToast("Política de asistencia guardada.");
      refreshStaffing();
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setPolicyBusy(false);
    }
  };
  const availableRoles = roles ?? [];
  const selectedRole = availableRoles.find((role) => role.code === selectedRoleCode) ?? availableRoles[0] ?? null;
  const employeeList = employees ?? [];
  const userList = users ?? [];
  const sessionList = sessions ?? [];
  const shiftList = shifts ?? [];
  const nowMs = Date.now();
  const scheduledShifts = shiftList.filter((shift) => shift.status === "scheduled");
  const upcomingShifts = scheduledShifts
    .filter((shift) => new Date(shift.ends_at).getTime() >= nowMs)
    .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime());
  const attendanceCount = shiftList.filter((shift) => shift.attendance).length;
  const employeeById = new Map(employeeList.map((employee) => [employee.id, employee]));
  const nextShiftFor = (employeeId: string): BackendShift | null =>
    upcomingShifts.find((shift) => shift.employee_id === employeeId) ?? null;
  const myShiftList = myShifts ?? [];
  const selfMarkAt = (shift: BackendShift) => selfMarkFor(shift, clockNow, myAttendancePolicy.check_in_early_grace_minutes);
  const myCurrentShift = myShiftList.find((shift) => selfMarkAt(shift).action !== null) ?? null;
  const pendingRequestFor = (attendanceId: string) =>
    (myRequests ?? []).find((request) => request.attendance_id === attendanceId && request.status === "pending") ?? null;
  const myShiftForAttendance = (attendanceId: string) =>
    myShiftList.find((shift) => shift.attendance?.id === attendanceId) ?? null;
  const teamShiftForAttendance = (attendanceId: string) =>
    shiftList.find((shift) => shift.attendance?.id === attendanceId) ?? null;
  const pendingRequestCount = (myRequests ?? []).filter((request) => request.status === "pending").length;

  const markAttendance = async (shift: BackendShift, eventType: "check_in" | "check_out") => {
    const key = `${shift.id}:${eventType}`;
    const requestId = pendingMarks.current.get(key) ?? crypto.randomUUID();
    pendingMarks.current.set(key, requestId);
    setBusyMarkShiftId(shift.id);
    try {
      const response = await fetch(`/api/staff/attendance/${eventType === "check_in" ? "clock-in" : "clock-out"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shift_id: shift.id, request_id: requestId }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        onToast(response.status === 409 ? "Ese turno ya tiene esa marca registrada." : payload.detail || "No se pudo registrar la marca.");
        return;
      }
      pendingMarks.current.delete(key);
      const attendance = await response.json() as BackendAttendance;
      if (eventType === "check_in") {
        onToast(attendance.status === "late"
          ? `Entrada registrada a las ${shiftClock(attendance.check_in_at)} (tarde).`
          : `Entrada registrada a las ${shiftClock(attendance.check_in_at)}.`);
      } else {
        onToast(`Salida registrada a las ${shiftClock(attendance.check_out_at ?? attendance.check_in_at)}.`);
      }
      refreshStaffing();
    } catch {
      onToast("No se pudo conectar con el backend. Reintenta: la marca no se duplicará.");
    } finally {
      setBusyMarkShiftId(null);
    }
  };
  const curatedCodes = new Set(permissionRows.map((permission) => permission.code));
  const catalogExtras = (permissionCatalog ?? [])
    .filter((entry) => !curatedCodes.has(entry.code))
    .map((entry) => ({ group: permissionGroupFor(entry.code), label: entry.label, code: entry.code }));
  const knownCodes = new Set([...curatedCodes, ...catalogExtras.map((row) => row.code)]);
  const extraPermissionRows = (selectedRole?.permissions ?? [])
    .filter((code) => !knownCodes.has(code))
    .sort()
    .map((code) => ({ group: "Otros", label: code, code }));
  const rowsByGroup = new Map<string, { group: string; label: string; code: string }[]>();
  for (const row of [...permissionRows, ...catalogExtras, ...extraPermissionRows]) {
    rowsByGroup.set(row.group, [...(rowsByGroup.get(row.group) ?? []), row]);
  }
  const matrixRows = [...rowsByGroup.values()].flat();

  const changeUserRole = async (user: BackendUser, method: "POST" | "DELETE", roleCode: string) => {
    setBusyUserId(user.id);
    try {
      const response = method === "POST"
        ? await fetch(`/api/admin/users/${user.id}/roles`, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role_code: roleCode }) })
        : await fetch(`/api/admin/users/${user.id}/roles/${roleCode}`, { method });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        onToast(payload.detail || "No se pudo actualizar el rol.");
        return;
      }
      onToast(method === "POST" ? `Rol asignado a ${user.email}.` : `Rol retirado a ${user.email}.`);
      refreshStaffing();
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusyUserId(null);
    }
  };

  const changeUserStatus = async (user: BackendUser) => {
    const nextStatus = user.status === "active" ? "disabled" : "active";
    setBusyUserId(user.id);
    try {
      const response = await fetch(`/api/admin/users/${user.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        onToast(payload.detail || "No se pudo cambiar el estado de la cuenta.");
        return;
      }
      onToast(
        nextStatus === "disabled"
          ? `Cuenta de ${user.email} deshabilitada; sus sesiones abiertas se cerraron.`
          : `Cuenta de ${user.email} habilitada.`,
      );
      refreshStaffing();
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusyUserId(null);
    }
  };

  const togglePermission = async (role: BackendRole, permissionCode: string, allowed: boolean) => {
    setBusyPermission(permissionCode);
    try {
      const response = allowed
        ? await fetch(`/api/admin/roles/${encodeURIComponent(role.code)}/permissions/${encodeURIComponent(permissionCode)}`, { method: "DELETE" })
        : await fetch(`/api/admin/roles/${encodeURIComponent(role.code)}/permissions`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ permission_code: permissionCode }),
          });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        onToast(payload.detail || "No se pudo actualizar el permiso.");
        return;
      }
      onToast(allowed ? `Permiso ${permissionCode} retirado de ${role.name}.` : `Permiso ${permissionCode} otorgado a ${role.name}.`);
      refreshStaffing();
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusyPermission(null);
    }
  };

  const revokeSession = async (session: BackendSession) => {
    setBusySessionId(session.id);
    try {
      const response = await fetch(`/api/admin/sessions/${session.id}`, { method: "DELETE" });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        onToast(payload.detail || "No se pudo revocar la sesión.");
        return;
      }
      onToast(session.is_current ? "Cerraste tu propia sesión." : `Sesión de ${session.email} revocada.`);
      refreshStaffing();
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusySessionId(null);
    }
  };

  return (
    <>
      <div className="staff-tabs" role="tablist" aria-label="Secciones de personal">
        {canSelfAttendance && <button role="tab" aria-selected={activeTab === "jornada"} className={activeTab === "jornada" ? "staff-tab-active" : ""} onClick={() => setActiveTab("jornada")}>Mi jornada</button>}
        {canViewStaff && <button role="tab" aria-selected={activeTab === "equipo"} className={activeTab === "equipo" ? "staff-tab-active" : ""} onClick={() => setActiveTab("equipo")}>Equipo</button>}
        {canManageRoles && <button role="tab" aria-selected={activeTab === "roles"} className={activeTab === "roles" ? "staff-tab-active" : ""} onClick={() => setActiveTab("roles")}>Roles y permisos</button>}
        {canManageRoles && <button role="tab" aria-selected={activeTab === "usuarios"} className={activeTab === "usuarios" ? "staff-tab-active" : ""} onClick={() => setActiveTab("usuarios")}>Usuarios</button>}
        {canManageSessions && <button role="tab" aria-selected={activeTab === "sesiones"} className={activeTab === "sesiones" ? "staff-tab-active" : ""} onClick={() => setActiveTab("sesiones")}>Sesiones</button>}
        <span className="staff-tabs-note"><ShieldCheck size={14} />Permisos validados en backend</span>
      </div>

      {activeTab === "jornada" ? (
        <>
          <section className="panel full-panel">
            <div className="panel-header access-list-heading">
              <div>
                <p className="section-kicker">MI JORNADA</p>
                <h2>{new Intl.DateTimeFormat("es-MX", { weekday: "long", day: "numeric", month: "long" }).format(new Date(clockNow))}</h2>
              </div>
              <span className="role-count">{new Intl.DateTimeFormat("es-MX", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(clockNow))}</span>
            </div>
            {myAttendanceState === "unlinked" ? (
              <p className="panel-hint" role="status">Tu cuenta no está enlazada a un expediente de colaborador, así que no hay turnos que marcar. Pide a quien administra el personal que cree tu cuenta desde tu colaborador.</p>
            ) : myAttendanceState === "error" ? (
              <p className="panel-hint" role="alert">No se pudo consultar tu jornada. Recarga la página o pide a recepción que registre tu marca.</p>
            ) : myAttendanceState === "loading" ? (
              <p className="panel-hint">Cargando tu jornada…</p>
            ) : myCurrentShift ? (
              <div className="staff-jornada-now">
                <div>
                  <strong>{myCurrentShift.attendance
                    ? (myCurrentShift.attendance.check_out_at
                      ? `Jornada completa · ${shiftClock(myCurrentShift.attendance.check_in_at)}–${shiftClock(myCurrentShift.attendance.check_out_at)}`
                      : `En turno desde las ${shiftClock(myCurrentShift.attendance.check_in_at)}`)
                    : `Turno de ${shiftClock(myCurrentShift.starts_at)} a ${shiftClock(myCurrentShift.ends_at)}`}</strong>
                  <p className="panel-hint">{selfMarkAt(myCurrentShift).hint}</p>
                </div>
                {(() => {
                  const mark = selfMarkAt(myCurrentShift);
                  return (
                    <div className="staff-row-actions">
                      {mark.action ? <button className="button button-primary" disabled={busyMarkShiftId === myCurrentShift.id} onClick={() => void markAttendance(myCurrentShift, mark.action as "check_in" | "check_out")}>{mark.action === "check_in" ? "Marcar entrada" : "Marcar salida"}</button> : null}
                      {myCurrentShift.attendance && !pendingRequestFor(myCurrentShift.attendance.id) ? <button className="button button-secondary" onClick={() => setRequestShift(myCurrentShift)}>Solicitar cambio</button> : null}
                    </div>
                  );
                })()}
              </div>
            ) : (
              <p className="panel-hint" role="status">No tienes un turno abierto ahora. Tu próximo turno aparece en la lista de abajo.</p>
            )}
          </section>
          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">TURNOS PROPIOS</p><h2>Últimos y próximos 14 días</h2></div></div>
            <div className="table-scroll"><table className="data-table"><thead><tr><th>DÍA</th><th>HORARIO</th><th>ESTADO</th><th>MARCA</th><th /></tr></thead><tbody>
              {myAttendanceState === "unlinked" ? <tr><td colSpan={5} className="empty-row">Sin expediente de colaborador.</td></tr>
                : myShiftList.length === 0 ? <tr><td colSpan={5} className="empty-row">{myAttendanceState === "loading" ? "Cargando turnos…" : "No tienes turnos programados en este periodo."}</td></tr>
                : myShiftList.map((shift) => {
                  const mark = selfMarkAt(shift);
                  const state = shift.status === "cancelled"
                    ? "Cancelado"
                    : shift.attendance
                      ? (shift.attendance.status === "late" ? "Tarde" : "Presente")
                      : "Programado";
                  const pending = shift.attendance ? pendingRequestFor(shift.attendance.id) : null;
                  return <tr key={shift.id}><td>{shiftDayLabel(shift.starts_at)}</td><td className="time-cell">{shiftClock(shift.starts_at)}–{shiftClock(shift.ends_at)}</td><td><StatusBadge state={state} /></td><td className="time-cell">{attendanceLabel(shift.attendance)}</td><td><div className="staff-row-actions">{mark.action ? <button className="button button-secondary" disabled={busyMarkShiftId === shift.id} onClick={() => void markAttendance(shift, mark.action as "check_in" | "check_out")}>{mark.action === "check_in" ? "Marcar entrada" : "Marcar salida"}</button> : null}{shift.attendance && !pending ? <button className="button button-secondary" onClick={() => setRequestShift(shift)}>Solicitar cambio</button> : null}{pending ? <span className="table-hint">Solicitud pendiente</span> : !mark.action && !shift.attendance ? <span className="table-hint">{mark.hint}</span> : null}</div></td></tr>;
                })}
            </tbody></table></div>
            <div className="table-bottom"><span>{myShiftList.length} turnos en el periodo</span><span>Puedes marcar desde {myAttendancePolicy.check_in_early_grace_minutes} minutos antes del inicio{myAttendancePolicy.lateness_tolerance_minutes > 0 ? ` · la tolerancia de retardo es de ${myAttendancePolicy.lateness_tolerance_minutes} min` : ""}</span></div>
          </section>
          {canSelfAttendance && myAttendanceState !== "unlinked" && (
            <section className="panel full-panel">
              <div className="panel-header access-list-heading"><div><p className="section-kicker">MIS SOLICITUDES</p><h2>Cambios pedidos a supervisión</h2></div><span className="role-count">{pendingRequestCount}</span></div>
              <p className="panel-hint">Si una marca quedó mal, pide desde tu turno que se corrija la hora o que se anule. Un supervisor la revisa y recibirás un aviso con la decisión y su motivo; mientras esperas, el turno conserva la marca actual.</p>
              <div className="table-scroll"><table className="data-table"><thead><tr><th>TURNO</th><th>MARCA</th><th>CAMBIO</th><th>ESTADO</th><th>DECISIÓN</th></tr></thead><tbody>
                {myRequestsError ? <tr><td colSpan={5} className="empty-row">{myRequestsError}</td></tr>
                  : myRequests === null ? <tr><td colSpan={5} className="empty-row">Cargando tus solicitudes…</td></tr>
                  : myRequests.length === 0 ? <tr><td colSpan={5} className="empty-row">No has pedido cambios. Usa «Solicitar cambio» en un turno con marca.</td></tr>
                  : myRequests.map((request) => {
                    const shift = myShiftForAttendance(request.attendance_id);
                    return <tr key={request.id}><td>{shift ? `${shiftDayLabel(shift.starts_at)} · ${shiftClock(shift.starts_at)}–${shiftClock(shift.ends_at)}` : "Turno"}</td><td>{attendanceMarkLabel(request.mark)}</td><td className="time-cell">{request.action === "void" ? "Anular la marca" : request.proposed_at ? `Cambiar a ${shiftClock(request.proposed_at)}` : "Corregir la hora"}</td><td><StatusBadge state={ATTENDANCE_REQUEST_STATUS_LABELS[request.status]} /></td><td><div className="staff-request-decision">{request.status === "pending" ? <span className="table-hint">En revisión</span> : <><span className="time-cell">{formatSessionTime(request.decided_at)}</span>{request.decision_note ? <small>{request.decision_note}</small> : null}</>}</div></td></tr>;
                  })}
              </tbody></table></div>
              <div className="table-bottom"><span>Las solicitudes quedan con su motivo y la decisión del supervisor</span><span>{myRequests?.filter((request) => request.status !== "pending").length ?? 0} resueltas</span></div>
            </section>
          )}
        </>
      ) : activeTab === "equipo" ? (
        <>
          <section className="member-stat-row staff-stat-row"><div><span>EMPLEADOS ACTIVOS</span><strong>{employeeList.filter((employee) => employee.status === "active").length}</strong><small>directorio del backend</small></div><div><span>TURNOS</span><strong>{canViewAttendance ? upcomingShifts.length : "—"}</strong><small>{canViewAttendance ? "próximos programados" : "acceso restringido"}</small></div><div><span>ASISTENCIA</span><strong>{canViewAttendance ? attendanceCount : "—"}</strong><small>{canViewAttendance ? "registros de entrada" : "acceso restringido"}</small></div><div><span>ROLES BASE</span><strong>{canManageRoles ? availableRoles.length : "—"}</strong><small>{canManageRoles ? "catálogo RBAC" : "acceso restringido"}</small></div></section>
          {canManageAttendance && <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">POLÍTICA DE ASISTENCIA</p><h2>Tolerancias del club</h2></div><span className="role-count">{policy ? `${policy.check_in_early_grace_minutes}/${policy.lateness_tolerance_minutes}` : "—"}</span></div>
            <p className="panel-hint">La apertura anticipada define cuántos minutos antes del inicio se habilita la entrada; la tolerancia define cuántos minutos después del inicio siguen contando como presente. Aplica al marcaje del colaborador, a las correcciones y a los registros manuales.</p>
            <div className="kiosk-occupancy-row">
              <label htmlFor="attendance-grace">Apertura anticipada (minutos)</label>
              <input id="attendance-grace" className="kiosk-limit-input" type="number" min={0} max={240} step={1} inputMode="numeric" value={policyGrace} disabled={policyBusy || policy === null} onChange={(event) => setPolicyGrace(event.target.value)} />
              <span className="kiosk-antipassback-state">{policy === null ? "Cargando la política…" : `La entrada se abre ${policy.check_in_early_grace_minutes} min antes del inicio.`}</span>
            </div>
            <div className="kiosk-occupancy-row">
              <label htmlFor="attendance-tolerance">Tolerancia de retardo (minutos)</label>
              <input id="attendance-tolerance" className="kiosk-limit-input" type="number" min={0} max={240} step={1} inputMode="numeric" value={policyTolerance} disabled={policyBusy || policy === null} onChange={(event) => setPolicyTolerance(event.target.value)} />
              <span className="kiosk-antipassback-state">{policy === null ? "" : policy.lateness_tolerance_minutes === 0 ? "Sin tolerancia: cualquier marca después del inicio es retardo." : `Hasta ${policy.lateness_tolerance_minutes} min tarde se considera presente.`}</span>
              <button type="button" className="button button-secondary" disabled={policyBusy || policy === null || (policyGrace === String(policy.check_in_early_grace_minutes) && policyTolerance === String(policy.lateness_tolerance_minutes))} onClick={() => void saveAttendancePolicy()}>{policyBusy ? "Guardando…" : "Guardar"}</button>
            </div>
            <div className="kiosk-occupancy-row">
              <span className="kiosk-antipassback-state">{policy?.updated_at ? `Última modificación: ${formatSessionTime(policy.updated_at)}` : "Sin cambios registrados todavía."}</span>
              <button type="button" className="button button-secondary" onClick={() => setPolicyHistoryOpen(true)}><History size={16} />Historial de cambios</button>
            </div>
          </section>}
          {canViewAttendance && <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">SOLICITUDES DEL EQUIPO</p><h2>Cambios de marca por revisar</h2></div><span className="role-count">{pendingRequests?.length ?? 0}</span></div>
            <p className="panel-hint">Cada colaborador puede pedir que se corrija la hora de una marca o que se anule. Aprobar aplica el cambio y deja el motivo en la bitácora del turno; rechazar exige explicar por qué. Nadie decide su propia solicitud.</p>
            <div className="table-scroll"><table className="data-table"><thead><tr><th>COLABORADOR</th><th>TURNO</th><th>MARCA</th><th>CAMBIO PROPUESTO</th><th>MOTIVO</th><th /></tr></thead><tbody>
              {requestsError ? <tr><td colSpan={6} className="empty-row">{requestsError}</td></tr>
                : pendingRequests === null ? <tr><td colSpan={6} className="empty-row">Cargando solicitudes…</td></tr>
                : pendingRequests.length === 0 ? <tr><td colSpan={6} className="empty-row">No hay solicitudes pendientes.</td></tr>
                : pendingRequests.map((request) => {
                  const shift = teamShiftForAttendance(request.attendance_id);
                  const mine = request.requested_by === currentUserId;
                  return <tr key={request.id}><td><div className="person-cell"><span className="person-avatar peach">{(request.employee_name ?? "C").slice(0, 1).toUpperCase()}</span><span><strong>{request.employee_name ?? "Colaborador"}</strong><small>{formatSessionTime(request.created_at)}</small></span></div></td><td>{shift ? <span className="time-cell">{shiftDayLabel(shift.starts_at)} · {shiftClock(shift.starts_at)}–{shiftClock(shift.ends_at)}</span> : "Turno"}</td><td>{attendanceMarkLabel(request.mark)}<small className="staff-request-current">{request.mark === "check_in" ? `Actual: ${shiftClock(request.current_check_in_at)}` : request.current_check_out_at ? `Actual: ${shiftClock(request.current_check_out_at)}` : "Sin marca"}</small></td><td className="time-cell">{request.action === "void" ? "Anular la marca" : request.proposed_at ? `Cambiar a ${shiftClock(request.proposed_at)}` : "Corregir la hora"}</td><td>{request.justification}</td><td>{mine ? <span className="table-hint">Tu solicitud</span> : canManageAttendance ? <button className="button button-secondary" onClick={() => setDecisionRequest(request)}>Revisar</button> : <span className="table-hint">Solo lectura</span>}</td></tr>;
                })}
            </tbody></table></div>
            <div className="table-bottom"><span>{pendingRequests?.length ?? 0} solicitudes esperando decisión</span><span>El solicitante recibe un aviso con la decisión</span></div>
          </section>}
          <section className="panel full-panel"><div className="panel-header access-list-heading"><div><p className="section-kicker">DIRECTORIO DE PERSONAL</p><h2>Colaboradores</h2></div>{canManageStaff && <button className="button button-secondary" onClick={() => setNewEmployeeOpen(true)}><Plus size={16} />Nuevo colaborador</button>}</div><div className="table-scroll"><table className="data-table"><thead><tr><th>COLABORADOR</th><th>PUESTO</th><th>HORARIO</th><th>ESTADO</th><th /></tr></thead><tbody>{loading ? <tr><td colSpan={5} className="empty-row">Cargando directorio…</td></tr> : error ? <tr><td colSpan={5} className="empty-row">{error}</td></tr> : employeeList.length === 0 ? <tr><td colSpan={5} className="empty-row">No hay colaboradores registrados.</td></tr> : employeeList.map((employee, index) => { const fullName = `${employee.first_name} ${employee.last_name}`; const initials = `${employee.first_name[0] ?? ""}${employee.last_name[0] ?? ""}`.toUpperCase(); const state = employee.status === "active" ? "Activo" : employee.status === "inactive" ? "Inactivo" : "Baja"; const color = ["mint", "peach", "lavender", "blue", "yellow"][index % 5]; return <tr key={employee.id}><td><div className="person-cell"><span className={`person-avatar ${color}`}>{initials}</span><span><strong>{fullName}</strong><small>{employee.email ?? employee.employee_number}</small></span></div></td><td>{employee.job_title}</td><td className="time-cell">{(() => { const shift = nextShiftFor(employee.id); return shift ? `${shiftDayLabel(shift.starts_at)} · ${shiftClock(shift.starts_at)}–${shiftClock(shift.ends_at)}` : "Sin turno"; })()}</td><td><StatusBadge state={state} /></td><td><button className="icon-button row-menu" aria-label={`Opciones de ${fullName}`}><MoreHorizontal size={17} /></button></td></tr>; })}</tbody></table></div><div className="table-bottom"><span>{employeeList.length} colaboradores registrados</span><span>Horario según los turnos del backend</span></div></section>
          {canViewAttendance && <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">TURNOS DEL PERSONAL</p><h2>Turnos programados</h2></div>{canManageAttendance && <button className="button button-secondary" onClick={() => setNewShiftOpen(true)}><Plus size={16} />Programar turno</button>}</div>
            <p className="panel-hint">Cada colaborador marca su entrada y salida en «Mi jornada». Desde aquí, quienes tienen el permiso de corregir asistencias registran una marca faltante, corrigen una ya registrada o anulan una que no debió existir; toda corrección o anulación exige un motivo y conserva la marca anterior en la bitácora del turno.</p>
            <div className="table-scroll"><table className="data-table"><thead><tr><th>COLABORADOR</th><th>DÍA</th><th>HORARIO</th><th>ESTADO</th><th>ASISTENCIA</th><th /></tr></thead><tbody>{shiftList.length === 0 ? <tr><td colSpan={6} className="empty-row">No hay turnos programados.</td></tr> : shiftList.map((shift) => { const employee = employeeById.get(shift.employee_id); const fullName = employee ? `${employee.first_name} ${employee.last_name}` : "Colaborador"; const attendance = shift.attendance; const canRegister = canManageAttendance && shift.status === "scheduled" && (!attendance || !attendance.check_out_at); const canCorrect = canManageAttendance && shift.status === "scheduled" && attendance !== null; const canViewLog = canViewAttendance && attendance !== null; const canVoid = canManageAttendance && shift.status === "scheduled" && attendance !== null; return <tr key={shift.id}><td><div className="person-cell"><span className="person-avatar mint">{fullName.slice(0, 1).toUpperCase()}</span><span><strong>{fullName}</strong><small>{employee?.employee_number ?? "—"}</small></span></div></td><td>{shiftDayLabel(shift.starts_at)}</td><td className="time-cell">{shiftClock(shift.starts_at)}–{shiftClock(shift.ends_at)}</td><td><StatusBadge state={shift.status === "scheduled" ? "Programado" : "Cancelado"} /></td><td className="time-cell">{attendanceLabel(attendance)}</td><td><div className="staff-row-actions">{canRegister ? <button className="button button-secondary" onClick={() => setManualShift(shift)}>{!attendance ? "Registrar entrada" : "Registrar salida"}</button> : null}{canCorrect ? <button className="button button-secondary" onClick={() => setCorrectionShift(shift)}>Corregir</button> : null}{canViewLog ? <button className="button button-secondary" onClick={() => setLogShift(shift)}>Bitácora</button> : null}{canVoid ? <button className="button button-secondary" onClick={() => setVoidShift(shift)}>Anular</button> : null}</div></td></tr>; })}</tbody></table></div>
            <div className="table-bottom"><span>{scheduledShifts.length} turnos programados</span><span>{attendanceCount} asistencias registradas</span></div>
          </section>}
          {canViewAttendance && <section className="panel full-panel">
            <div className="panel-header access-list-heading">
              <div><p className="section-kicker">ANULACIONES</p><h2>Marcas anuladas y quién las anuló</h2></div>
              <label className="table-select"><span>Periodo</span><select value={annulmentDays} onChange={(event) => setAnnulmentDays(Number(event.target.value))}><option value={7}>Últimos 7 días</option><option value={30}>Últimos 30 días</option><option value={90}>Últimos 90 días</option></select></label>
            </div>
            <p className="panel-hint">Anular no borra la marca: la conserva en la bitácora con el motivo y la cuenta responsable. Este reporte cuenta cuántas anulaciones hizo cada operador en el periodo elegido.</p>
            {annulmentError ? <div className="login-error" role="alert">{annulmentError}</div> : annulmentReport === null ? <p className="panel-hint">Cargando el reporte…</p> : <>
              <div className="annulment-operators">{annulmentReport.by_operator.length === 0 ? <span className="role-chip-empty">Sin anulaciones en el periodo.</span> : annulmentReport.by_operator.map((operator) => <span key={operator.actor_id} className="annulment-operator"><strong>{operator.actor_name ?? operator.actor_email}</strong><span>{operator.total} {operator.total === 1 ? "anulación" : "anulaciones"} · {operator.check_ins} entrada(s) · {operator.check_outs} salida(s)</span></span>)}</div>
              <div className="table-scroll"><table className="data-table"><thead><tr><th>FECHA</th><th>COLABORADOR</th><th>MARCA</th><th>RESPONSABLE</th><th>MOTIVO</th></tr></thead><tbody>
                {annulmentReport.items.length === 0 ? <tr><td colSpan={5} className="empty-row">Sin anulaciones registradas en este periodo.</td></tr>
                  : annulmentReport.items.map((item) => <tr key={item.event_id}><td className="time-cell">{formatSessionTime(item.occurred_at)}</td><td>{item.employee_name}</td><td>{ATTENDANCE_EVENT_LABELS[item.event_type] ?? item.event_type}</td><td>{item.actor_name ?? item.actor_email}</td><td>{item.reason ?? "—"}</td></tr>)}
              </tbody></table></div>
              <div className="table-bottom"><span>{annulmentReport.total} anulaciones en {annulmentDays} días</span><span>{annulmentReport.by_operator.length} operadores con anulaciones</span></div>
            </>}
          </section>}
        </>
      ) : activeTab === "roles" ? (
        <div className="role-management-grid">
          <section className="panel role-list-panel">
            <div className="panel-header"><div><p className="section-kicker">PERFILES DEL BACKEND</p><h2>Roles base</h2></div><span className="role-count">{availableRoles.length}</span></div>
            {loading ? <p className="role-empty">Cargando roles…</p> : error ? <p className="role-empty">{error}</p> : availableRoles.length === 0 ? <p className="role-empty">No hay roles disponibles.</p> : <div className="role-list">{availableRoles.map((role) => <button key={role.code} className={`role-list-item ${selectedRoleCode === role.code ? "role-selected" : ""}`} onClick={() => setSelectedRoleCode(role.code)}><span className="role-initial">{role.name.slice(0, 1)}</span><span className="role-list-copy"><strong>{role.name}</strong><small>{role.code}</small></span><span className="role-permission-count">{role.permissions.length}</span></button>)}</div>}
            <div className="role-list-note"><ShieldCheck size={15} /><span>La verificación se ejecuta en cada ruta del backend.</span></div>
          </section>
          <section className="panel role-detail-panel">
            {selectedRole ? <><div className="role-detail-header"><div><p className="section-kicker">MATRIZ DE AUTORIZACIÓN</p><h2>{selectedRole.name}</h2><p>{selectedRole.description}</p></div>{selectedRole.code === "owner" ? <span className="role-protected-badge"><ShieldCheck size={14} />Rol protegido</span> : <span className="role-edit-hint">{canManageRoles ? "Toca un permiso para otorgarlo o retirarlo" : "Solo lectura"}</span>}</div>
              <div className="permission-table-head"><span>ÁREA Y ACCIÓN</span><span>PERMISO</span><span>ESTADO</span></div>
              <div className="permission-rows">{matrixRows.map((permission, index) => { const allowed = selectedRole.permissions.includes(permission.code); const previous = matrixRows[index - 1]; const editable = canManageRoles && selectedRole.code !== "owner"; const busy = busyPermission === permission.code; return <div key={permission.code}><div className={`permission-group-label ${!previous || previous.group !== permission.group ? "permission-group-visible" : ""}`}>{!previous || previous.group !== permission.group ? permission.group : ""}</div><div className="permission-row"><span>{permission.label}</span><code>{permission.code}</code>{editable ? <button type="button" className={`permission-state permission-toggle ${allowed ? "permission-allowed" : "permission-denied"}`} disabled={busy} aria-label={`${allowed ? "Retirar" : "Otorgar"} ${permission.code} a ${selectedRole.name}`} onClick={() => void togglePermission(selectedRole, permission.code, allowed)}>{busy ? "…" : allowed ? <><Check size={13} />Permitido</> : "Sin acceso"}</button> : <span className={`permission-state ${allowed ? "permission-allowed" : "permission-denied"}`}>{allowed ? <><Check size={13} />Permitido</> : "Sin acceso"}</span>}</div></div>; })}</div>
              <div className="role-detail-footer"><span><span className="live-dot" />Backend · {selectedRole.permissions.length} permisos efectivos</span><span>{selectedRole.code === "owner" ? "Permisos fijos del dueño" : "Los cambios se aplican al instante"}</span></div></> : <p className="role-empty">Selecciona un rol para consultar sus permisos.</p>}
          </section>
        </div>
      ) : activeTab === "usuarios" ? (
        <section className="panel full-panel">
          <div className="panel-header access-list-heading"><div><p className="section-kicker">CUENTAS DE ACCESO</p><h2>Usuarios y roles</h2></div><span className="role-count">{userList.length}</span></div>
          <p className="panel-hint">Asigna o retira roles por cuenta, y habilita o deshabilita el acceso. Deshabilitar cierra las sesiones abiertas de inmediato; el backend impide dejar al club sin ningún dueño y registra responsable y fecha.</p>
          <div className="table-scroll"><table className="data-table"><thead><tr><th>USUARIO</th><th>ESTADO</th><th>ROLES ASIGNADOS</th><th>ASIGNAR ROL</th><th /></tr></thead><tbody>{loading ? <tr><td colSpan={5} className="empty-row">Cargando cuentas…</td></tr> : error ? <tr><td colSpan={5} className="empty-row">{error}</td></tr> : userList.length === 0 ? <tr><td colSpan={5} className="empty-row">No hay cuentas registradas.</td></tr> : userList.map((user) => { const missingRoles = availableRoles.filter((role) => !user.roles.includes(role.code)); const busy = busyUserId === user.id; return <tr key={user.id}><td><div className="person-cell"><span className="person-avatar blue">{user.email.slice(0, 1).toUpperCase()}</span><span><strong>{user.email}</strong><small>{user.employee_name ?? "Sin colaborador vinculado"}</small></span></div></td><td><StatusBadge state={user.status === "active" ? "Activo" : "Deshabilitado"} /></td><td><div className="role-chip-row">{user.roles.length === 0 ? <span className="role-chip-empty">Sin roles</span> : user.roles.map((code) => { const label = availableRoles.find((role) => role.code === code)?.name ?? code; return <span key={code} className="role-chip">{label}<button type="button" aria-label={`Retirar ${label} de ${user.email}`} disabled={busy} onClick={() => void changeUserRole(user, "DELETE", code)}><X size={12} /></button></span>; })}</div></td><td>{missingRoles.length === 0 ? <span className="role-chip-empty">Todos asignados</span> : <select className="role-assign" value="" disabled={busy} onChange={(event) => { if (event.target.value) void changeUserRole(user, "POST", event.target.value); }}><option value="">Seleccionar…</option>{missingRoles.map((role) => <option key={role.code} value={role.code}>{role.name}</option>)}</select>}</td><td><button className="button button-secondary" disabled={busy} onClick={() => void changeUserStatus(user)}>{user.status === "active" ? "Deshabilitar" : "Habilitar"}</button></td></tr>; })}</tbody></table></div>
          <div className="table-bottom"><span>{userList.length} cuentas registradas</span><span>Cambios auditados con responsable y fecha</span></div>
        </section>
      ) : (
        <section className="panel full-panel">
          <div className="panel-header access-list-heading"><div><p className="section-kicker">SESIONES ACTIVAS</p><h2>Accesos al panel</h2></div><span className="role-count">{sessionList.length}</span></div>
          <p className="panel-hint">Sesiones con token vigente. Revocar una cierra el acceso de esa cuenta de inmediato y queda registrado con el responsable.</p>
          <div className="table-scroll"><table className="data-table"><thead><tr><th>USUARIO</th><th>INICIADA</th><th>ÚLTIMA ACTIVIDAD</th><th>EXPIRA</th><th /></tr></thead><tbody>{loading ? <tr><td colSpan={5} className="empty-row">Cargando sesiones…</td></tr> : error ? <tr><td colSpan={5} className="empty-row">{error}</td></tr> : sessionList.length === 0 ? <tr><td colSpan={5} className="empty-row">No hay sesiones activas.</td></tr> : sessionList.map((session) => { const busy = busySessionId === session.id; return <tr key={session.id}><td><div className="person-cell"><span className="person-avatar mint">{session.email.slice(0, 1).toUpperCase()}</span><span><strong>{session.email}{session.is_current ? <span className="session-current">Esta sesión</span> : null}</strong><small>{session.employee_name ?? "Sin colaborador vinculado"}</small></span></div></td><td className="time-cell">{formatSessionTime(session.created_at)}</td><td className="time-cell">{formatSessionTime(session.last_seen_at)}</td><td className="time-cell">{formatSessionTime(session.expires_at)}</td><td><button className="button button-secondary" disabled={busy} onClick={() => void revokeSession(session)}>{busy ? "Revocando…" : session.is_current ? "Cerrar mi sesión" : "Revocar"}</button></td></tr>; })}</tbody></table></div>
          <div className="table-bottom"><span>{sessionList.length} sesiones activas</span><span>Tokens Bearer · expiración 8 horas</span></div>
        </section>
      )}
      {newEmployeeOpen && canManageStaff && <NewEmployeeModal canCreateAccount={canManageRoles} roles={availableRoles} onClose={() => setNewEmployeeOpen(false)} onCreated={(message) => { onToast(message); onIdentityChanged(); }} />}
      {newShiftOpen && canManageAttendance && <ScheduleShiftModal employees={employeeList} onClose={() => setNewShiftOpen(false)} onCreated={(message) => { onToast(message); onIdentityChanged(); }} />}
      {manualShift && canManageAttendance && <ManualAttendanceModal shift={manualShift} employee={employeeById.get(manualShift.employee_id) ?? null} onClose={() => setManualShift(null)} onCreated={(message) => { onToast(message); onIdentityChanged(); }} />}
      {correctionShift && canManageAttendance && <AttendanceCorrectionModal shift={correctionShift} employee={employeeById.get(correctionShift.employee_id) ?? null} onClose={() => setCorrectionShift(null)} onSaved={(message) => { onToast(message); onIdentityChanged(); }} />}
      {logShift && canViewAttendance && logShift.attendance && <AttendanceLogModal attendance={logShift.attendance} employee={employeeById.get(logShift.employee_id) ?? null} shift={logShift} onClose={() => setLogShift(null)} />}
      {voidShift && canManageAttendance && voidShift.attendance && <AttendanceVoidModal shift={voidShift} attendance={voidShift.attendance} employee={employeeById.get(voidShift.employee_id) ?? null} onClose={() => setVoidShift(null)} onSaved={(message) => { onToast(message); onIdentityChanged(); }} />}
      {requestShift && requestShift.attendance && canSelfAttendance && <AttendanceRequestModal shift={requestShift} attendance={requestShift.attendance} onClose={() => setRequestShift(null)} onCreated={(message) => { onToast(message); refreshStaffing(); }} />}
      {decisionRequest && canManageAttendance && <AttendanceRequestDecisionModal request={decisionRequest} shift={teamShiftForAttendance(decisionRequest.attendance_id)} onClose={() => setDecisionRequest(null)} onDecided={(message) => { onToast(message); refreshStaffing(); }} />}
      {policyHistoryOpen && canManageAttendance && <PolicyHistoryModal onClose={() => setPolicyHistoryOpen(false)} />}
      <footer className="page-footer"><span>Centro Fit · Personal</span><span>DATOS DEL BACKEND · NÓMINA FUERA DE ESTA VISTA</span></footer>
    </>
  );
}

function SessionLoading() {
  return <main className="session-loading"><div className="session-spinner" /><span>Validando sesión segura…</span></main>;
}

function LoginView({ email, password, error, busy, onEmailChange, onPasswordChange, onSubmit }: { email: string; password: string; error: string; busy: boolean; onEmailChange: (value: string) => void; onPasswordChange: (value: string) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  return (
    <main className="login-page">
      <section className="login-visual">
        <div className="login-brand"><img className="login-brand-logo" src="/brand/centro-fit-logo.png" alt="Centro Fit" /></div>
        <div className="login-visual-copy"><p className="eyebrow">PANEL DE OPERACIÓN</p><h1>Un club en movimiento.<br /><em>Una operación clara.</em></h1><p>Control de acceso, socios y equipo en un solo lugar.</p></div>
        <div className="login-visual-art" aria-hidden="true"><span className="login-art-line line-a" /><span className="login-art-line line-b" /><span className="login-art-ring" /><span className="login-art-number">01</span><Activity size={34} /></div>
        <div className="login-visual-footer"><span>CENTRO FIT · SUCURSAL PRINCIPAL</span><span>OPERACIÓN LOCAL</span></div>
      </section>
      <section className="login-form-side">
        <div className="login-form-shell">
          <span className="login-form-mark"><Fingerprint size={19} /></span>
          <p className="section-kicker">IDENTIDAD Y ACCESO</p>
          <h2>Iniciar sesión</h2>
          <p className="login-form-subtitle">Usa tu cuenta de colaborador para entrar al panel.</p>
          <form className="login-form" onSubmit={onSubmit}>
            <label className="form-field"><span>Correo electrónico</span><input type="email" name="email" autoComplete="username" value={email} onChange={(event) => onEmailChange(event.target.value)} placeholder="nombre@correo.com" required /></label>
            <label className="form-field"><span>Contraseña</span><input type="password" name="password" autoComplete="current-password" value={password} onChange={(event) => onPasswordChange(event.target.value)} placeholder="••••••••••••" required /></label>
            {error && <div className="login-error" role="alert">{error}</div>}
            <button type="submit" className="button button-primary login-submit" disabled={busy}>{busy ? "Validando…" : "Entrar al panel"}<ArrowRight size={16} /></button>
          </form>
          <div className="login-security-note"><ShieldCheck size={16} /><span>Sesión cifrada y validada por el servidor. No compartas tu contraseña.</span></div>
          <div className="login-form-footer">¿Necesitas ayuda para entrar? <button type="button">Contacta a tu gerente</button></div>
        </div>
      </section>
    </main>
  );
}

function InventoryView({ permissions, onUnauthorized, onToast }: { permissions: string[]; onUnauthorized: () => void; onToast: (message: string) => void }) {
  const canManageCatalog = permissions.includes("inventory.manage");
  const canSell = permissions.includes("sales.manage");
  const canReadSales = permissions.includes("sales.read");
  const canManageCredit = permissions.includes("sales.credit");
  const canRefundServices = permissions.includes("sales.service_refund");
  const showSalesActions = canSell || canRefundServices;
  const canReadInventory = permissions.includes("inventory.read") || canManageCatalog;

  const [tab, setTab] = useState<"venta" | "catalogo" | "caja" | "devoluciones" | "compras" | "cuentas">("venta");

  const [catalog, setCatalog] = useState<ProductDirectory | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState("");
  const [productSearch, setProductSearch] = useState("");
  const [productQuery, setProductQuery] = useState("");
  const [productCategory, setProductCategory] = useState("");
  const [productState, setProductState] = useState<"" | ProductState>("");
  const [productPage, setProductPage] = useState(1);
  const [productsRefresh, setProductsRefresh] = useState(0);

  const [posProducts, setPosProducts] = useState<BackendProduct[]>([]);
  const [posLoading, setPosLoading] = useState(false);
  const [posSearch, setPosSearch] = useState("");
  const [posQuery, setPosQuery] = useState("");
  const [posRefresh, setPosRefresh] = useState(0);

  const [sales, setSales] = useState<SaleDirectory | null>(null);
  const [salesLoading, setSalesLoading] = useState(false);
  const [salesError, setSalesError] = useState("");
  const [salesPage, setSalesPage] = useState(1);
  const [salesRefresh, setSalesRefresh] = useState(0);

  const [cashSession, setCashSession] = useState<CashSession | null>(null);
  const [cashHistory, setCashHistory] = useState<CashSession[]>([]);
  const [cashLoading, setCashLoading] = useState(false);
  const [cashError, setCashError] = useState("");
  const [cashRefresh, setCashRefresh] = useState(0);

  const [cart, setCart] = useState<CartLine[]>([]);
  const [paymentMethod, setPaymentMethod] = useState<"cash" | "card" | "transfer" | "account">("cash");
  const [saleNote, setSaleNote] = useState("");
  const [saleError, setSaleError] = useState("");
  const [saleBusy, setSaleBusy] = useState(false);
  const [memberSearch, setMemberSearch] = useState("");
  const [memberResults, setMemberResults] = useState<BackendMember[]>([]);
  const [memberSearching, setMemberSearching] = useState(false);
  const [selectedMember, setSelectedMember] = useState<BackendMember | null>(null);

  const [productModal, setProductModal] = useState<{ product: BackendProduct | null } | null>(null);
  const [stockModal, setStockModal] = useState<BackendProduct | null>(null);
  const [openCashOpen, setOpenCashOpen] = useState(false);
  const [closeCashOpen, setCloseCashOpen] = useState(false);

  const [returns, setReturns] = useState<SaleReturnDirectory | null>(null);
  const [returnsLoading, setReturnsLoading] = useState(false);
  const [returnsError, setReturnsError] = useState("");
  const [returnsPage, setReturnsPage] = useState(1);
  const [returnsRefresh, setReturnsRefresh] = useState(0);
  const [returnSale, setReturnSale] = useState<BackendSale | null>(null);
  const [serviceRefundSale, setServiceRefundSale] = useState<BackendSale | null>(null);

  const [suppliers, setSuppliers] = useState<SupplierDirectory | null>(null);
  const [suppliersLoading, setSuppliersLoading] = useState(false);
  const [suppliersError, setSuppliersError] = useState("");
  const [supplierSearch, setSupplierSearch] = useState("");
  const [supplierQuery, setSupplierQuery] = useState("");
  const [suppliersPage, setSuppliersPage] = useState(1);
  const [suppliersRefresh, setSuppliersRefresh] = useState(0);
  const [supplierModal, setSupplierModal] = useState<{ supplier: BackendSupplier | null } | null>(null);

  const [orders, setOrders] = useState<PurchaseOrderDirectory | null>(null);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [ordersError, setOrdersError] = useState("");
  const [ordersPage, setOrdersPage] = useState(1);
  const [ordersStatus, setOrdersStatus] = useState<"" | PurchaseOrderStatus>("");
  const [ordersRefresh, setOrdersRefresh] = useState(0);
  const [orderModalOpen, setOrderModalOpen] = useState(false);
  const [receiveOrder, setReceiveOrder] = useState<BackendPurchaseOrder | null>(null);

  const [accounts, setAccounts] = useState<MemberAccountDirectory | null>(null);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [accountsError, setAccountsError] = useState("");
  const [accountsPage, setAccountsPage] = useState(1);
  const [accountSearch, setAccountSearch] = useState("");
  const [accountQuery, setAccountQuery] = useState("");
  const [accountsRefresh, setAccountsRefresh] = useState(0);
  const [accountOverLimit, setAccountOverLimit] = useState(false);
  const [accountMember, setAccountMember] = useState<MemberAccountSummary | null>(null);
  const [creditLookupOpen, setCreditLookupOpen] = useState(false);
  const [reminderOpen, setReminderOpen] = useState(false);
  const [selectedMemberAccount, setSelectedMemberAccount] = useState<MemberAccountSummary | null>(null);

  const [offlineQueue, setOfflineQueue] = useState<OfflineSaleEntry[]>([]);
  const [offlineReady, setOfflineReady] = useState(false);
  const [isOffline, setIsOffline] = useState(false);
  const [syncBusy, setSyncBusy] = useState(false);
  const [offlineError, setOfflineError] = useState("");
  const offlineSyncRef = useRef<() => void>(() => {});

  useEffect(() => {
    const stored = readStoredJson<OfflineSaleEntry[]>(OFFLINE_QUEUE_KEY);
    if (Array.isArray(stored)) setOfflineQueue(stored);
    setIsOffline(typeof navigator !== "undefined" && !navigator.onLine);
    setOfflineReady(true);
  }, []);

  useEffect(() => {
    if (!offlineReady) return;
    writeStoredJson(OFFLINE_QUEUE_KEY, offlineQueue);
  }, [offlineQueue, offlineReady]);

  useEffect(() => {
    if (!offlineReady) return;
    const goOffline = () => setIsOffline(true);
    const goOnline = () => {
      setIsOffline(false);
      setOfflineError("");
      offlineSyncRef.current();
    };
    window.addEventListener("offline", goOffline);
    window.addEventListener("online", goOnline);
    return () => {
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("online", goOnline);
    };
  }, [offlineReady]);

  useEffect(() => {
    if (isOffline && paymentMethod === "account") setPaymentMethod("cash");
  }, [isOffline, paymentMethod]);

  useEffect(() => {
    const handle = window.setTimeout(() => setProductQuery(productSearch.trim()), 300);
    return () => window.clearTimeout(handle);
  }, [productSearch]);

  useEffect(() => {
    const handle = window.setTimeout(() => setPosQuery(posSearch.trim()), 250);
    return () => window.clearTimeout(handle);
  }, [posSearch]);

  useEffect(() => { setProductPage(1); }, [productQuery, productCategory, productState]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setCatalogLoading(true);
      setCatalogError("");
      try {
        const params = new URLSearchParams({ page: String(productPage), page_size: String(PRODUCTS_PAGE_SIZE) });
        if (productQuery) params.set("search", productQuery);
        if (productCategory) params.set("category", productCategory);
        if (productState) params.set("state", productState);
        const response = await fetch(`/api/admin/products?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("No se pudo consultar el catálogo.");
        const directory = await response.json() as ProductDirectory;
        if (active) setCatalog(directory);
      } catch (error) {
        if (active) setCatalogError(error instanceof Error ? error.message : "Error al cargar el catálogo.");
      } finally {
        if (active) setCatalogLoading(false);
      }
    };
    void load();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productCategory, productPage, productQuery, productState, productsRefresh]);

  useEffect(() => {
    let active = true;
    const useCachedCatalog = () => {
      const cached = readStoredJson<BackendProduct[]>(OFFLINE_PRODUCTS_KEY);
      if (cached === null) {
        if (active) setPosProducts([]);
        return;
      }
      const term = posQuery.trim().toLowerCase();
      const filtered = cached.filter((item) => {
        if (!item.is_active) return false;
        if (!term) return true;
        return `${item.name} ${item.sku} ${item.barcode ?? ""}`.toLowerCase().includes(term);
      });
      if (active) setPosProducts(filtered);
    };
    const load = async () => {
      setPosLoading(true);
      try {
        const params = new URLSearchParams({ page_size: "100" });
        if (posQuery) params.set("search", posQuery);
        const response = await fetch(`/api/admin/products?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) {
          if (isUnavailableStatus(response.status)) {
            if (active) setIsOffline(true);
            useCachedCatalog();
            return;
          }
          throw new Error("No se pudo consultar el catálogo.");
        }
        const directory = await response.json() as ProductDirectory;
        if (!posQuery) writeStoredJson(OFFLINE_PRODUCTS_KEY, directory.items);
        if (active) {
          setPosProducts(directory.items.filter((item) => item.is_active));
          setIsOffline(false);
        }
      } catch {
        useCachedCatalog();
        if (active) setIsOffline(true);
      } finally {
        if (active) setPosLoading(false);
      }
    };
    void load();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [posQuery, posRefresh]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setSalesLoading(true);
      setSalesError("");
      try {
        const response = await fetch(`/api/admin/sales?page=${salesPage}&page_size=${SALES_PAGE_SIZE}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("No se pudo consultar las ventas.");
        const directory = await response.json() as SaleDirectory;
        if (active) setSales(directory);
      } catch (error) {
        if (active) setSalesError(error instanceof Error ? error.message : "Error al cargar ventas.");
      } finally {
        if (active) setSalesLoading(false);
      }
    };
    void load();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [salesPage, salesRefresh]);

  useEffect(() => {
    if (!canReadSales) return;
    let active = true;
    const load = async () => {
      setReturnsLoading(true);
      setReturnsError("");
      try {
        const response = await fetch(`/api/admin/sales/returns?page=${returnsPage}&page_size=${RETURNS_PAGE_SIZE}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("No se pudieron consultar las devoluciones.");
        const directory = await response.json() as SaleReturnDirectory;
        if (active) setReturns(directory);
      } catch (error) {
        if (active) setReturnsError(error instanceof Error ? error.message : "Error al cargar devoluciones.");
      } finally {
        if (active) setReturnsLoading(false);
      }
    };
    void load();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canReadSales, returnsPage, returnsRefresh]);

  useEffect(() => {
    const handle = window.setTimeout(() => setSupplierQuery(supplierSearch.trim()), 300);
    return () => window.clearTimeout(handle);
  }, [supplierSearch]);

  useEffect(() => { setSuppliersPage(1); }, [supplierQuery]);

  useEffect(() => {
    if (tab !== "compras" || !canReadInventory) return;
    let active = true;
    const load = async () => {
      setSuppliersLoading(true);
      setSuppliersError("");
      try {
        const params = new URLSearchParams({ page: String(suppliersPage), page_size: String(SUPPLIERS_PAGE_SIZE) });
        if (supplierQuery) params.set("search", supplierQuery);
        const response = await fetch(`/api/admin/suppliers?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("No se pudo consultar los proveedores.");
        const directory = await response.json() as SupplierDirectory;
        if (active) setSuppliers(directory);
      } catch (error) {
        if (active) setSuppliersError(error instanceof Error ? error.message : "Error al cargar proveedores.");
      } finally {
        if (active) setSuppliersLoading(false);
      }
    };
    void load();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, canReadInventory, suppliersPage, supplierQuery, suppliersRefresh]);

  useEffect(() => { setOrdersPage(1); }, [ordersStatus]);

  useEffect(() => {
    if (tab !== "compras" || !canReadInventory) return;
    let active = true;
    const load = async () => {
      setOrdersLoading(true);
      setOrdersError("");
      try {
        const params = new URLSearchParams({ page: String(ordersPage), page_size: String(PURCHASE_ORDERS_PAGE_SIZE) });
        if (ordersStatus) params.set("status", ordersStatus);
        const response = await fetch(`/api/admin/purchase-orders?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("No se pudieron consultar las órdenes de compra.");
        const directory = await response.json() as PurchaseOrderDirectory;
        if (active) setOrders(directory);
      } catch (error) {
        if (active) setOrdersError(error instanceof Error ? error.message : "Error al cargar órdenes de compra.");
      } finally {
        if (active) setOrdersLoading(false);
      }
    };
    void load();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, canReadInventory, ordersPage, ordersStatus, ordersRefresh]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setCashLoading(true);
      setCashError("");
      try {
        const [currentResponse, historyResponse] = await Promise.all([
          fetch("/api/admin/cash-sessions/current", { cache: "no-store" }),
          fetch("/api/admin/cash-sessions?limit=12", { cache: "no-store" }),
        ]);
        if (currentResponse.status === 401 || historyResponse.status === 401) { onUnauthorized(); return; }
        if (!currentResponse.ok || !historyResponse.ok) throw new Error("No se pudo consultar el turno de caja.");
        const current = await currentResponse.json() as CashSession | null;
        const history = await historyResponse.json() as CashSession[];
        if (active) {
          setCashSession(current);
          setCashHistory(history);
          writeStoredJson(OFFLINE_SESSION_KEY, current);
          setIsOffline(false);
        }
      } catch (error) {
        const cached = readStoredJson<CashSession>(OFFLINE_SESSION_KEY);
        if (active) {
          if (cached) {
            setCashSession(cached);
            setCashError("Mostrando el último turno guardado en este navegador.");
          } else {
            setCashError(error instanceof Error ? error.message : "Error al cargar la caja.");
          }
          setIsOffline(true);
        }
      } finally {
        if (active) setCashLoading(false);
      }
    };
    void load();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cashRefresh]);

  useEffect(() => {
    const term = memberSearch.trim();
    if (selectedMember || term.length < 2) {
      setMemberResults([]);
      return;
    }
    let active = true;
    const handle = window.setTimeout(async () => {
      setMemberSearching(true);
      try {
        const response = await fetch(`/api/admin/members?search=${encodeURIComponent(term)}&page_size=5`, { cache: "no-store" });
        if (response.ok) {
          const directory = await response.json() as MemberDirectory;
          if (active) setMemberResults(directory.items);
        } else if (active) {
          setMemberResults([]);
        }
      } catch {
        if (active) setMemberResults([]);
      } finally {
        if (active) setMemberSearching(false);
      }
    }, 250);
    return () => { active = false; window.clearTimeout(handle); };
  }, [memberSearch, selectedMember]);

  useEffect(() => {
    const handle = window.setTimeout(() => setAccountQuery(accountSearch.trim()), 300);
    return () => window.clearTimeout(handle);
  }, [accountSearch]);

  useEffect(() => { setAccountsPage(1); }, [accountQuery]);

  useEffect(() => {
    if (tab !== "cuentas" || !canReadSales) return;
    let active = true;
    const load = async () => {
      setAccountsLoading(true);
      setAccountsError("");
      try {
        const params = new URLSearchParams({ page: String(accountsPage), page_size: "10" });
        if (accountQuery) params.set("search", accountQuery);
        if (accountOverLimit) params.set("over_limit", "true");
        const response = await fetch(`/api/admin/member-accounts?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("No se pudieron consultar las cuentas por cobrar.");
        const directory = await response.json() as MemberAccountDirectory;
        if (active) setAccounts(directory);
      } catch (error) {
        if (active) setAccountsError(error instanceof Error ? error.message : "Error al cargar las cuentas por cobrar.");
      } finally {
        if (active) setAccountsLoading(false);
      }
    };
    void load();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, canReadSales, accountsPage, accountQuery, accountsRefresh, accountOverLimit]);

  useEffect(() => {
    if (!selectedMember) { setSelectedMemberAccount(null); return; }
    let active = true;
    const load = async () => {
      try {
        const response = await fetch(`/api/admin/member-accounts/${selectedMember.id}`, { cache: "no-store" });
        if (!response.ok) { if (active) setSelectedMemberAccount(null); return; }
        const statement = await response.json() as MemberAccountStatement;
        if (active) setSelectedMemberAccount(statement.summary);
      } catch {
        if (active) setSelectedMemberAccount(null);
      }
    };
    void load();
    return () => { active = false; };
  }, [selectedMember]);

  const addToCart = (product: BackendProduct) => {
    if (product.stock <= 0) return;
    setSaleError("");
    setCart((current) => {
      const existing = current.find((line) => line.product_id === product.id);
      if (existing) {
        if (existing.quantity >= product.stock) return current;
        return current.map((line) => line.product_id === product.id ? { ...line, quantity: line.quantity + 1 } : line);
      }
      return [...current, { product_id: product.id, name: product.name, sku: product.sku, unit_price_cents: product.price_cents, quantity: 1 }];
    });
  };

  const changeQuantity = (productId: string, next: number) => {
    setCart((current) => current.flatMap((line) => line.product_id === productId
      ? (next <= 0 ? [] : [{ ...line, quantity: next }])
      : [line]));
  };

  const removeLine = (productId: string) => {
    setCart((current) => current.filter((line) => line.product_id !== productId));
  };

  const cartTotal = cart.reduce((sum, line) => sum + line.unit_price_cents * line.quantity, 0);

  const selectedCreditAvailable = selectedMemberAccount?.credit_available_cents ?? null;
  const accountCreditExceeded =
    paymentMethod === "account" &&
    selectedCreditAvailable !== null &&
    cartTotal > selectedCreditAvailable;

  const queueOfflineSale = (message: string) => {
    if (paymentMethod === "account") {
      setSaleError("La venta a cuenta del socio requiere conexión. Cambia la forma de pago o espera a recuperar la red.");
      return;
    }
    const entry: OfflineSaleEntry = {
      client_reference: newClientReference(),
      sold_at: new Date().toISOString(),
      items: cart.map((line) => ({ product_id: line.product_id, quantity: line.quantity })),
      payment_method: paymentMethod,
      member_id: selectedMember ? selectedMember.id : null,
      note: saleNote.trim() || null,
      total_cents: cartTotal,
      summary: cart.map((line) => `${line.quantity}× ${line.name}`).join(", "),
    };
    setOfflineQueue((current) => [...current, entry]);
    setPosProducts((current) => adjustProductStock(current, entry.items, -1));
    const cached = readStoredJson<BackendProduct[]>(OFFLINE_PRODUCTS_KEY);
    if (cached) writeStoredJson(OFFLINE_PRODUCTS_KEY, adjustProductStock(cached, entry.items, -1));
    setCart([]);
    setSaleNote("");
    setSelectedMember(null);
    setMemberSearch("");
    setPaymentMethod("cash");
    setSaleError("");
    setIsOffline(true);
    onToast(message);
  };

  const discardOfflineSale = (reference: string) => {
    if (typeof window !== "undefined" && !window.confirm("¿Descartar esta venta sin sincronizar? No se registrará en el sistema.")) {
      return;
    }
    setOfflineQueue((current) => current.filter((entry) => entry.client_reference !== reference));
    setOfflineError("");
    setPosRefresh((value) => value + 1);
    onToast("Venta sin conexión descartada.");
  };

  const syncOfflineSales = async () => {
    if (!canSell || syncBusy || offlineQueue.length === 0) return;
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      setIsOffline(true);
      setOfflineError("Sigue sin conexión. Las ventas se enviarán cuando vuelva la red.");
      return;
    }
    setSyncBusy(true);
    setOfflineError("");
    try {
      const response = await fetch("/api/admin/sales/offline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sales: offlineQueue.map((entry) => ({
            client_reference: entry.client_reference,
            sold_at: entry.sold_at,
            items: entry.items,
            payment_method: entry.payment_method,
            member_id: entry.member_id,
            note: entry.note,
          })),
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        if (isUnavailableStatus(response.status)) {
          setIsOffline(true);
          setOfflineError("No se pudo conectar con el backend. Intenta de nuevo al recuperar la red.");
          return;
        }
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        setOfflineError(payload.detail || "No se pudieron sincronizar las ventas.");
        return;
      }
      const payload = await response.json() as OfflineSaleSync;
      setOfflineQueue((current) => current.flatMap((entry) => {
        const result = payload.results.find((item) => item.client_reference === entry.client_reference);
        if (!result) return [entry];
        if (result.status === "rejected") return [{ ...entry, error: result.error ?? "Rechazada por el servidor." }];
        return [];
      }));
      setIsOffline(false);
      setPosRefresh((value) => value + 1);
      setProductsRefresh((value) => value + 1);
      setSalesRefresh((value) => value + 1);
      setCashRefresh((value) => value + 1);
      setAccountsRefresh((value) => value + 1);
      const parts = [`${payload.created} ${payload.created === 1 ? "venta registrada" : "ventas registradas"}`];
      if (payload.duplicates > 0) parts.push(`${payload.duplicates} ya existían`);
      if (payload.rejected > 0) parts.push(`${payload.rejected} por revisar`);
      onToast(`Sincronización: ${parts.join(", ")}.`);
    } catch {
      setIsOffline(true);
      setOfflineError("No se pudo conectar con el backend. Intenta de nuevo al recuperar la red.");
    } finally {
      setSyncBusy(false);
    }
  };

  useEffect(() => {
    offlineSyncRef.current = () => { void syncOfflineSales(); };
  });

  useEffect(() => {
    if (!offlineReady || !canSell) return;
    if (typeof navigator !== "undefined" && navigator.onLine && offlineQueue.length > 0) {
      void syncOfflineSales();
    }
    // Only when the local queue is first available or the role loads: later
    // retries are manual or triggered by the "online" event.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offlineReady, canSell]);

  const requestCloseCash = () => {
    if (offlineQueue.length > 0) {
      onToast("Sincroniza las ventas sin conexión antes de cerrar el turno.");
      return;
    }
    setCloseCashOpen(true);
  };

  const submitSale = async () => {
    if (cart.length === 0) {
      setSaleError("Agrega al menos un producto a la venta.");
      return;
    }
    if (paymentMethod === "account" && !selectedMember) {
      setSaleError("Selecciona al socio para cargar la venta a su cuenta.");
      return;
    }
    if (paymentMethod === "account" && accountCreditExceeded) {
      setSaleError(`La venta excede el crédito disponible del socio (${formatMoney(Math.max(selectedCreditAvailable ?? 0, 0))}).`);
      return;
    }
    if (paymentMethod === "account" && isOffline) {
      setSaleError("La venta a cuenta del socio requiere conexión. Cambia la forma de pago o espera a recuperar la red.");
      return;
    }
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      queueOfflineSale("Sin conexión: venta guardada en este navegador. Se enviará al reconectar.");
      return;
    }
    setSaleBusy(true);
    setSaleError("");
    try {
      const response = await fetch("/api/admin/sales", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          items: cart.map((line) => ({ product_id: line.product_id, quantity: line.quantity })),
          payment_method: paymentMethod,
          member_id: selectedMember ? selectedMember.id : null,
          note: saleNote.trim() || null,
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (isUnavailableStatus(response.status)) {
        queueOfflineSale("Sin conexión: venta guardada en este navegador. Se enviará al reconectar.");
        return;
      }
      const payload = await response.json().catch(() => ({})) as { detail?: string; folio?: string };
      if (!response.ok) {
        setSaleError(payload.detail || "No se pudo registrar la venta.");
        return;
      }
      setIsOffline(false);
      setCart([]);
      setSaleNote("");
      setSelectedMember(null);
      setMemberSearch("");
      setPaymentMethod("cash");
      setPosRefresh((value) => value + 1);
      setProductsRefresh((value) => value + 1);
      setSalesRefresh((value) => value + 1);
      setCashRefresh((value) => value + 1);
      if (paymentMethod === "account") setAccountsRefresh((value) => value + 1);
      onToast(`Venta ${payload.folio ?? ""} registrada.`);
    } catch {
      queueOfflineSale("Sin conexión: venta guardada en este navegador. Se enviará al reconectar.");
    } finally {
      setSaleBusy(false);
    }
  };

  const handleProductSaved = (message: string) => {
    setProductModal(null);
    setProductsRefresh((value) => value + 1);
    setPosRefresh((value) => value + 1);
    onToast(message);
  };

  const handleStockSaved = (message: string) => {
    setStockModal(null);
    setProductsRefresh((value) => value + 1);
    setPosRefresh((value) => value + 1);
    onToast(message);
  };

  const handleCashOpened = (message: string) => {
    setOpenCashOpen(false);
    setCashRefresh((value) => value + 1);
    setSalesRefresh((value) => value + 1);
    onToast(message);
  };

  const handleCashClosed = (message: string) => {
    setCloseCashOpen(false);
    setCashRefresh((value) => value + 1);
    onToast(message);
  };

  const handleReturnSaved = (message: string) => {
    setReturnSale(null);
    setSalesRefresh((value) => value + 1);
    setReturnsRefresh((value) => value + 1);
    setPosRefresh((value) => value + 1);
    setProductsRefresh((value) => value + 1);
    setCashRefresh((value) => value + 1);
    setAccountsRefresh((value) => value + 1);
    onToast(message);
  };

  const handleAccountSaved = (message: string) => {
    setAccountsRefresh((value) => value + 1);
    setCashRefresh((value) => value + 1);
    onToast(message);
  };

  const openReturn = (sale: BackendSale) => {
    if (!cashSession) {
      onToast("Abre el turno de caja para registrar devoluciones.");
      return;
    }
    setReturnSale(sale);
  };

  const handleServiceRefundSaved = (message: string) => {
    setServiceRefundSale(null);
    setSalesRefresh((value) => value + 1);
    setReturnsRefresh((value) => value + 1);
    setPosRefresh((value) => value + 1);
    setCashRefresh((value) => value + 1);
    setAccountsRefresh((value) => value + 1);
    onToast(message);
  };

  const handleSupplierSaved = (message: string) => {
    setSupplierModal(null);
    setSuppliersRefresh((value) => value + 1);
    onToast(message);
  };

  const handleOrderSaved = (message: string) => {
    setOrderModalOpen(false);
    setReceiveOrder(null);
    setOrdersRefresh((value) => value + 1);
    setProductsRefresh((value) => value + 1);
    setPosRefresh((value) => value + 1);
    onToast(message);
  };

  const changeOrderState = async (order: BackendPurchaseOrder, action: "send" | "cancel") => {
    try {
      const response = await fetch(`/api/admin/purchase-orders/${order.id}/${action}`, { method: "POST" });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo actualizar la orden."); return; }
      setOrdersRefresh((value) => value + 1);
      onToast(action === "send" ? `Orden ${order.folio} enviada al proveedor.` : `Orden ${order.folio} cancelada.`);
    } catch {
      onToast("No se pudo conectar con el backend.");
    }
  };

  const summary = catalog?.summary ?? { total: 0, active: 0, low_stock: 0, out_of_stock: 0, inactive: 0 };
  const catalogueItems = catalog?.items ?? [];
  const catalogueTotal = catalog?.total ?? 0;
  const cataloguePages = catalog?.pages ?? 0;
  const categories = catalog?.categories ?? [];
  const hasCatalogueFilters = Boolean(productQuery) || Boolean(productCategory) || Boolean(productState);
  const saleSummary = sales?.summary ?? { count: 0, total_cents: 0, cash_cents: 0, card_cents: 0, transfer_cents: 0, account_cents: 0, refunds_cents: 0, refunded_count: 0 };
  const saleItems = sales?.items ?? [];
  const returnSummary = returns?.summary ?? { count: 0, total_refund_cents: 0, cash_refund_cents: 0, card_refund_cents: 0, transfer_refund_cents: 0, account_refund_cents: 0 };
  const returnItems = returns?.items ?? [];
  const supplierItems = suppliers?.items ?? [];
  const supplierTotal = suppliers?.total ?? 0;
  const supplierPages = suppliers?.pages ?? 0;
  const orderSummary = orders?.summary ?? { count: 0, created: 0, sent: 0, received: 0, cancelled: 0, total_cents: 0 };
  const orderItems = orders?.items ?? [];
  const accountItems = accounts?.items ?? [];

  const tabButton = (value: "venta" | "catalogo" | "caja" | "devoluciones" | "compras" | "cuentas", label: string) => (
    <button type="button" className={tab === value ? "staff-tab-active" : ""} onClick={() => setTab(value)}>{label}</button>
  );

  return (
    <>
      <section className="access-summary-band pos-cash-band">
        <div className="access-summary-main">
          <span className="summary-icon"><Banknote size={18} /></span>
          <div>
            <span>TURNO DE CAJA</span>
            <strong>{cashLoading ? "Consultando…" : cashSession ? `Abierto por ${cashSession.opened_by_email ?? "—"}` : "Sin turno abierto"}</strong>
          </div>
        </div>
        <div className="summary-divider" />
        <div className="summary-stat"><span>VENTAS POS</span><strong>{cashSession?.sales_count ?? 0}</strong></div>
        <div className="summary-stat"><span>TOTAL POS</span><strong>{formatMoney(cashSession?.total_sales_cents ?? 0)}</strong></div>
        <div className="summary-stat"><span>EFECTIVO ESPERADO</span><strong>{formatMoney(cashSession?.expected_cash_cents ?? 0)}</strong></div>
        {canSell && (cashSession
          ? <button className="button button-secondary" onClick={requestCloseCash} disabled={offlineQueue.length > 0} title={offlineQueue.length > 0 ? "Sincroniza las ventas sin conexión antes de cerrar el turno" : undefined}><Receipt size={16} />Cerrar turno</button>
          : <button className="button button-primary" onClick={() => setOpenCashOpen(true)}><Plus size={16} />Abrir turno</button>)}
      </section>

      <div className="staff-tabs pos-tabs">
        {tabButton("venta", "Punto de venta")}
        {tabButton("catalogo", "Catálogo")}
        {tabButton("caja", "Caja y cortes")}
        {canReadSales && tabButton("devoluciones", "Devoluciones")}
        {canReadSales && tabButton("cuentas", "Cuentas por cobrar")}
        {canReadInventory && tabButton("compras", "Compras")}
        <span className="staff-tabs-note"><ShieldCheck size={14} />Pagos con terminal real no conectados</span>
      </div>

      {(isOffline || offlineQueue.length > 0) && (
        <section className="panel full-panel pos-offline-panel" role="status">
          <div className="pos-offline-head">
            <div>
              <span className={`status-badge ${isOffline ? "status-bad" : "status-warn"}`}><i />{isOffline ? "Sin conexión" : "Pendiente de sincronizar"}</span>
              <strong>{offlineQueue.length === 0 ? " El catálogo y el turno se muestran desde la caché local." : ` ${offlineQueue.length} ${offlineQueue.length === 1 ? "venta guardada" : "ventas guardadas"} en este navegador.`}</strong>
              <p className="panel-hint">Las ventas sin conexión se envían al recuperar la red. No cierres el turno hasta sincronizarlas.</p>
            </div>
            <button className="button button-primary" onClick={() => void syncOfflineSales()} disabled={syncBusy || offlineQueue.length === 0}><RotateCcw size={16} />{syncBusy ? "Sincronizando…" : "Sincronizar"}</button>
          </div>
          {offlineError && <div className="login-error" role="alert">{offlineError}</div>}
          {offlineQueue.length > 0 && (
            <ul className="pos-offline-list">
              {offlineQueue.map((entry) => (
                <li key={entry.client_reference}>
                  <span><strong>{formatMoney(entry.total_cents)}</strong> · {entry.summary}</span>
                  <small>{formatSaleTime(entry.sold_at)} · {paymentMethodLabels[entry.payment_method] ?? entry.payment_method}</small>
                  {entry.error && <small className="pos-offline-error">{entry.error}</small>}
                  <button type="button" className="text-button" onClick={() => discardOfflineSale(entry.client_reference)}>Descartar</button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {tab === "venta" && (
        !canSell ? (
          <section className="panel full-panel"><p className="panel-hint">Tu rol no puede registrar ventas. Consulta el catálogo o los cortes en las otras pestañas.</p></section>
        ) : !cashSession ? (
          <section className="panel full-panel pos-locked">
            <span className="placeholder-icon"><Banknote size={20} /></span>
            <h2>Abre el turno de caja para vender</h2>
            <p className="panel-hint">Las ventas se asocian al turno abierto para poder conciliar el efectivo al cierre.</p>
            <button className="button button-primary" onClick={() => setOpenCashOpen(true)}><Plus size={16} />Abrir turno</button>
          </section>
        ) : (
          <div className="pos-sell-grid">
            <section className="panel pos-products-panel">
              <div className="panel-header"><div><p className="section-kicker">CATÁLOGO</p><h2>Productos</h2></div></div>
              <label className="table-search pos-search"><Search size={16} /><input value={posSearch} onChange={(event) => setPosSearch(event.target.value)} placeholder="Buscar por nombre, SKU o código de barras" /></label>
              <div className="pos-product-list">
                {posLoading ? <p className="panel-hint">Cargando productos…</p>
                  : posProducts.length === 0 ? <p className="panel-hint">{posQuery ? "Sin coincidencias." : "Aún no hay productos activos."}</p>
                  : posProducts.map((product) => {
                    const inCart = cart.find((line) => line.product_id === product.id);
                    const disabled = product.stock <= 0 || (inCart?.quantity ?? 0) >= product.stock;
                    return (
                      <button key={product.id} type="button" className="pos-product" disabled={disabled} onClick={() => addToCart(product)}>
                        <span className="pos-product-icon"><Package size={16} /></span>
                        <span className="pos-product-copy"><strong>{product.name}</strong><small>{product.sku} · {formatMoney(product.price_cents)}</small></span>
                        <span className={`status-badge ${productStateBadges[product.state]}`}><i />{product.stock} disp.</span>
                      </button>
                    );
                  })}
              </div>
            </section>

            <section className="panel pos-cart-panel">
              <div className="panel-header"><div><p className="section-kicker">TICKET</p><h2>Venta actual</h2></div><span className="pos-count"><ShoppingCart size={15} />{cart.reduce((sum, line) => sum + line.quantity, 0)}</span></div>
              <div className="pos-cart-lines">
                {cart.length === 0 ? <p className="panel-hint">Selecciona productos del catálogo para armar la venta.</p>
                  : cart.map((line) => (
                    <div key={line.product_id} className="pos-cart-line">
                      <span className="pos-cart-copy"><strong>{line.name}</strong><small>{formatMoney(line.unit_price_cents)} c/u</small></span>
                      <span className="pos-qty">
                        <button type="button" className="icon-button" aria-label="Quitar uno" onClick={() => changeQuantity(line.product_id, line.quantity - 1)}><Minus size={14} /></button>
                        <span>{line.quantity}</span>
                        <button type="button" className="icon-button" aria-label="Agregar uno" onClick={() => changeQuantity(line.product_id, line.quantity + 1)}><Plus size={14} /></button>
                      </span>
                      <span className="pos-line-total">{formatMoney(line.unit_price_cents * line.quantity)}</span>
                      <button type="button" className="icon-button pos-remove" aria-label={`Quitar ${line.name}`} onClick={() => removeLine(line.product_id)}><Trash2 size={14} /></button>
                    </div>
                  ))}
              </div>

              <div className="pos-cart-footer">
                <div className="form-row">
                  <label className="form-field"><span>Forma de pago</span><select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value as "cash" | "card" | "transfer" | "account")}><option value="cash">Efectivo</option><option value="card">Tarjeta</option><option value="transfer">Transferencia</option><option value="account" disabled={isOffline}>Cuenta del socio</option></select></label>
                  <label className="form-field"><span>Nota (opcional)</span><input value={saleNote} onChange={(event) => setSaleNote(event.target.value)} placeholder="Referencia o comentario" maxLength={200} /></label>
                </div>
                {selectedMember ? (
                  <div className="manual-member pos-member">
                    <div className="person-cell"><span className="person-avatar mint">{`${selectedMember.first_name[0] ?? ""}${selectedMember.last_name[0] ?? ""}`.toUpperCase()}</span><span><strong>{selectedMember.first_name} {selectedMember.last_name}</strong><small>{selectedMember.email ?? selectedMember.phone ?? "Socio"}{selectedMemberAccount ? ` · Saldo ${formatMoney(selectedMemberAccount.balance_cents)}` : ""}{selectedMemberAccount?.credit_limit_cents != null ? ` · Crédito ${formatMoney(Math.max(selectedMemberAccount.credit_available_cents ?? 0, 0))}` : ""}</small></span></div>
                    <button type="button" className="button button-secondary button-small" onClick={() => { setSelectedMember(null); setMemberSearch(""); }}>Quitar</button>
                  </div>
                ) : (
                  <label className="form-field pos-member-search"><span>Asociar a un socio (opcional)</span><input value={memberSearch} onChange={(event) => setMemberSearch(event.target.value)} placeholder="Buscar por nombre o correo" autoComplete="off" /></label>
                )}
                {paymentMethod === "account" && !selectedMember && <p className="manual-hint">Selecciona al socio para cargar esta venta a su cuenta.</p>}
                {paymentMethod === "account" && selectedMemberAccount?.credit_limit_cents != null && (
                  <p className={`manual-hint ${accountCreditExceeded ? "stat-orange" : ""}`}>
                    {accountCreditExceeded
                      ? `La venta (${formatMoney(cartTotal)}) excede el crédito disponible (${formatMoney(Math.max(selectedMemberAccount.credit_available_cents ?? 0, 0))}).`
                      : `Crédito disponible: ${formatMoney(Math.max(selectedMemberAccount.credit_available_cents ?? 0, 0))}.`}
                  </p>
                )}
                {isOffline && <p className="manual-hint">Sin conexión: la venta se guarda en este navegador y se sincroniza al reconectar. La cuenta del socio y las devoluciones requieren conexión.</p>}
                {!selectedMember && memberSearching && <p className="manual-hint">Buscando socios…</p>}
                {!selectedMember && memberResults.length > 0 && (
                  <ul className="manual-results pos-member-results">
                    {memberResults.map((member) => (
                      <li key={member.id}><button type="button" onClick={() => { setSelectedMember(member); setMemberResults([]); }}><span className="person-cell"><span className="person-avatar blue">{`${member.first_name[0] ?? ""}${member.last_name[0] ?? ""}`.toUpperCase()}</span><span><strong>{member.first_name} {member.last_name}</strong><small>{member.email ?? member.phone ?? "Socio"}</small></span></span></button></li>
                    ))}
                  </ul>
                )}
                {saleError && <div className="login-error" role="alert">{saleError}</div>}
                <div className="pos-total"><span>Total</span><strong>{formatMoney(cartTotal)}</strong></div>
                <button className="button button-primary pos-charge" onClick={submitSale} disabled={saleBusy || cart.length === 0 || (paymentMethod === "account" && (!selectedMember || isOffline || accountCreditExceeded))}><Check size={16} />{saleBusy ? "Registrando…" : isOffline ? "Guardar sin conexión" : paymentMethod === "account" ? "Cargar a cuenta" : "Cobrar"}</button>
              </div>
            </section>
          </div>
        )
      )}

      {tab === "catalogo" && (
        <>
          <section className="pos-stat-row" role="group" aria-label="Filtrar productos por estado">
            <button type="button" className={productState === "" ? "pos-stat-active" : ""} onClick={() => setProductState("")}><span>TOTAL</span><strong>{summary.total}</strong><small>productos</small></button>
            <button type="button" className={productState === "active" ? "pos-stat-active" : ""} onClick={() => setProductState(productState === "active" ? "" : "active")}><span>DISPONIBLES</span><strong>{summary.active}</strong><small>sobre el mínimo</small></button>
            <button type="button" className={productState === "low" ? "pos-stat-active" : ""} onClick={() => setProductState(productState === "low" ? "" : "low")}><span>STOCK BAJO</span><strong className="stat-orange">{summary.low_stock}</strong><small>por reabastecer</small></button>
            <button type="button" className={productState === "out" ? "pos-stat-active" : ""} onClick={() => setProductState(productState === "out" ? "" : "out")}><span>SIN STOCK</span><strong className="stat-orange">{summary.out_of_stock}</strong><small>agotados</small></button>
            <button type="button" className={productState === "inactive" ? "pos-stat-active" : ""} onClick={() => setProductState(productState === "inactive" ? "" : "inactive")}><span>INACTIVOS</span><strong>{summary.inactive}</strong><small>fuera de venta</small></button>
          </section>

          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">INVENTARIO</p><h2>Catálogo de productos</h2></div>{canManageCatalog && <button className="button button-primary" onClick={() => setProductModal({ product: null })}><Plus size={17} />Nuevo producto</button>}</div>
            <div className="table-toolbar">
              <label className="table-search"><Search size={17} /><input value={productSearch} onChange={(event) => setProductSearch(event.target.value)} placeholder="Buscar por nombre, SKU, código o categoría" /></label>
              {categories.length > 0 && <label className="table-select"><span>Categoría</span><select value={productCategory} onChange={(event) => setProductCategory(event.target.value)}><option value="">Todas</option>{categories.map((category) => <option key={category} value={category}>{category}</option>)}</select></label>}
              {hasCatalogueFilters ? <button className="button button-secondary" onClick={() => { setProductSearch(""); setProductCategory(""); setProductState(""); }}>Limpiar filtros</button> : <span className="table-hint">Consulta existencias y ajusta el inventario</span>}
            </div>
            <div className="table-scroll"><table className="data-table"><thead><tr><th>PRODUCTO</th><th>CATEGORÍA</th><th>PRECIO</th><th>EXISTENCIA</th><th>ESTADO</th>{canManageCatalog && <th />}</tr></thead><tbody>
              {catalogLoading ? <tr><td colSpan={canManageCatalog ? 6 : 5} className="empty-row">Cargando catálogo…</td></tr>
                : catalogError ? <tr><td colSpan={canManageCatalog ? 6 : 5} className="empty-row">{catalogError}</td></tr>
                : catalogueItems.length === 0 ? <tr><td colSpan={canManageCatalog ? 6 : 5} className="empty-row">{hasCatalogueFilters ? "No hay productos que coincidan con el filtro." : "Aún no hay productos registrados."}</td></tr>
                : catalogueItems.map((product) => (
                  <tr key={product.id}>
                    <td><div className="person-cell"><span className="pos-row-icon"><Package size={15} /></span><span><strong>{product.name}</strong><small>{product.sku}{product.barcode ? ` · ${product.barcode}` : ""}</small></span></div></td>
                    <td>{product.category}</td>
                    <td className="time-cell">{formatMoney(product.price_cents)}</td>
                    <td className="time-cell">{product.stock} <small className="pos-min">mín. {product.stock_min}</small></td>
                    <td><span className={`status-badge ${productStateBadges[product.state]}`}><i />{productStateLabels[product.state]}</span></td>
                    {canManageCatalog && <td><div className="pos-row-actions"><button type="button" className="text-button" onClick={() => setStockModal(product)}>Movimiento</button><button type="button" className="icon-button row-menu" aria-label={`Editar ${product.name}`} onClick={() => setProductModal({ product })}><MoreHorizontal size={17} /></button></div></td>}
                  </tr>
                ))}
            </tbody></table></div>
            <div className="table-bottom">
              <span>{catalogueTotal} {catalogueTotal === 1 ? "producto" : "productos"} en el catálogo</span>
              {cataloguePages > 1 && (
                <span className="member-pagination"><span>Página {productPage} de {cataloguePages}</span><button type="button" aria-label="Página anterior" disabled={productPage <= 1} onClick={() => setProductPage(Math.max(1, productPage - 1))}>‹</button><button type="button" aria-label="Página siguiente" disabled={productPage >= cataloguePages} onClick={() => setProductPage(Math.min(cataloguePages, productPage + 1))}>›</button></span>
              )}
            </div>
          </section>
        </>
      )}

      {tab === "caja" && (
        <>
          <section className="panel full-panel pos-cash-panel">
            <div className="panel-header access-list-heading">
              <div><p className="section-kicker">TURNO</p><h2>{cashSession ? "Turno abierto" : "Sin turno abierto"}</h2></div>
              {canSell && (cashSession
                ? <button className="button button-secondary" onClick={requestCloseCash} disabled={offlineQueue.length > 0} title={offlineQueue.length > 0 ? "Sincroniza las ventas sin conexión antes de cerrar el turno" : undefined}><Receipt size={16} />Cerrar turno</button>
                : <button className="button button-primary" onClick={() => setOpenCashOpen(true)}><Plus size={16} />Abrir turno</button>)}
            </div>
            {cashLoading ? <p className="panel-hint">Consultando turno…</p>
              : cashError ? <p className="panel-hint">{cashError}</p>
              : cashSession ? (
                <div className="pos-cash-grid">
                  <div className="summary-stat"><span>ABIERTO</span><strong className="pos-cash-time">{formatSaleTime(cashSession.opened_at)}</strong><small>por {cashSession.opened_by_email ?? "—"}</small></div>
                  <div className="summary-stat"><span>FONDO INICIAL</span><strong>{formatMoney(cashSession.opening_cash_cents)}</strong></div>
                  <div className="summary-stat"><span>EFECTIVO POS</span><strong>{formatMoney(cashSession.cash_sales_cents)}</strong></div>
                  <div className="summary-stat"><span>TARJETA POS</span><strong>{formatMoney(cashSession.card_sales_cents)}</strong></div>
                  <div className="summary-stat"><span>TRANSFERENCIA POS</span><strong>{formatMoney(cashSession.transfer_sales_cents)}</strong></div>
                  <div className="summary-stat"><span>VENTAS A CUENTA</span><strong>{formatMoney(cashSession.account_sales_cents)}</strong><small>no entran a la caja</small></div>
                  <div className="summary-stat"><span>COBROS DE CUENTA</span><strong>{formatMoney(cashSession.account_payments_cents)}</strong><small>{cashSession.account_payments_count} · efectivo {formatMoney(cashSession.cash_account_payments_cents)}</small></div>
                  <div className="summary-stat"><span>MEMBRESÍAS</span><strong>{formatMoney(cashSession.membership_payments_cents)}</strong><small>{cashSession.membership_payments_count} cobros · efectivo {formatMoney(cashSession.cash_membership_payments_cents)} · no efectivo {formatMoney(cashSession.membership_payments_cents - cashSession.cash_membership_payments_cents)}</small></div>
                  <div className="summary-stat"><span>DEVOLUCIONES</span><strong>{formatMoney(cashSession.total_refunds_cents)}</strong><small>{cashSession.refunds_count} · efectivo {formatMoney(cashSession.cash_refunds_cents)} · cuenta {formatMoney(cashSession.account_refunds_cents)}</small></div>
                  <div className="summary-stat"><span>EFECTIVO ESPERADO</span><strong className="stat-orange">{formatMoney(cashSession.expected_cash_cents)}</strong></div>
                </div>
              ) : <p className="panel-hint">Abre el turno para comenzar a registrar ventas y conciliar el efectivo al cierre.</p>}
          </section>

          <section className="panel full-panel pos-history-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">CORTES</p><h2>Últimos turnos</h2></div></div>
            <div className="table-scroll"><table className="data-table"><thead><tr><th>APERTURA</th><th>RESPONSABLE</th><th>VENTAS POS</th><th>TOTAL POS</th><th>ESPERADO</th><th>CONTADO</th><th>DIFERENCIA</th><th>ESTADO</th></tr></thead><tbody>
              {cashHistory.length === 0 ? <tr><td colSpan={8} className="empty-row">Aún no hay cortes registrados.</td></tr>
                : cashHistory.map((item) => (
                  <tr key={item.id}>
                    <td className="time-cell">{formatSaleTime(item.opened_at)}</td>
                    <td>{item.opened_by_email ?? "—"}</td>
                    <td className="time-cell">{item.sales_count}</td>
                    <td className="time-cell">{formatMoney(item.total_sales_cents)}</td>
                    <td className="time-cell">{formatMoney(item.expected_cash_cents)}</td>
                    <td className="time-cell">{item.counted_cash_cents === null ? "—" : formatMoney(item.counted_cash_cents)}</td>
                    <td className="time-cell">{item.difference_cents === null ? "—" : formatMoney(item.difference_cents)}</td>
                    <td><StatusBadge state={item.status === "open" ? "Abierto" : "Cerrado"} /></td>
                  </tr>
                ))}
            </tbody></table></div>
          </section>
        </>
      )}

      {tab === "venta" && (
        <section className="panel full-panel pos-sales-panel">
          <div className="panel-header access-list-heading">
            <div><p className="section-kicker">HISTORIAL</p><h2>Ventas recientes</h2></div>
            <span className="table-hint">{saleSummary.count} ventas · {formatMoney(saleSummary.total_cents)}{saleSummary.refunds_cents > 0 ? ` · devuelto ${formatMoney(saleSummary.refunds_cents)}` : ""}</span>
          </div>
          <div className="table-scroll"><table className="data-table"><thead><tr><th>FOLIO</th><th>HORA</th><th>PRODUCTOS</th><th>PAGO</th><th>SOCIO</th><th>TOTAL</th><th>ESTADO</th>{showSalesActions && <th />}</tr></thead><tbody>
            {salesLoading ? <tr><td colSpan={showSalesActions ? 8 : 7} className="empty-row">Cargando ventas…</td></tr>
              : salesError ? <tr><td colSpan={showSalesActions ? 8 : 7} className="empty-row">{salesError}</td></tr>
              : saleItems.length === 0 ? <tr><td colSpan={showSalesActions ? 8 : 7} className="empty-row">Todavía no hay ventas registradas.</td></tr>
              : saleItems.map((sale) => {
                const returnable = canSell && sale.lines.some((line) => line.product_id !== null && line.returnable_quantity > 0);
                const refundableService = canRefundServices && sale.lines.some((line) => line.product_id === null && line.returnable_quantity > 0);
                const onlyServices = sale.lines.every((line) => line.product_id === null);
                return (
                  <tr key={sale.id}>
                    <td className="time-cell">{sale.folio}{sale.origin === "offline" && <span className="status-badge status-warn pos-origin-badge"><i />Offline</span>}</td>
                    <td className="time-cell">{formatSaleTime(sale.sold_at)}</td>
                    <td>{onlyServices ? "Servicio de clase" : `${sale.lines.reduce((sum, line) => sum + line.quantity, 0)} artículos`}</td>
                    <td>{paymentMethodLabels[sale.payment_method] ?? sale.payment_method}</td>
                    <td>{sale.member_name ?? "Público general"}</td>
                    <td className="time-cell">{formatMoney(sale.total_cents)}{sale.refunded_cents > 0 && <small className="pos-min">devuelto {formatMoney(sale.refunded_cents)}</small>}</td>
                    <td><span className={`status-badge ${saleStatusBadges[sale.status] ?? "status-neutral"}`}><i />{saleStatusLabels[sale.status] ?? sale.status}</span></td>
                    {showSalesActions && <td><div className="pos-row-actions">{returnable ? <button type="button" className="text-button" onClick={() => openReturn(sale)}>Devolver</button> : refundableService ? <button type="button" className="text-button" onClick={() => setServiceRefundSale(sale)}>Reembolsar</button> : <span className="table-hint">—</span>}</div></td>}
                  </tr>
                );
              })}
          </tbody></table></div>
          {sales && sales.pages > 1 && (
            <div className="table-bottom"><span>{sales.total} ventas registradas</span><span className="member-pagination"><span>Página {sales.page} de {sales.pages}</span><button type="button" aria-label="Página anterior" disabled={salesPage <= 1} onClick={() => setSalesPage(Math.max(1, salesPage - 1))}>‹</button><button type="button" aria-label="Página siguiente" disabled={salesPage >= sales.pages} onClick={() => setSalesPage(Math.min(sales.pages, salesPage + 1))}>›</button></span></div>
          )}
        </section>
      )}

      {tab === "devoluciones" && canReadSales && (
        <>
          <section className="panel full-panel pos-cash-panel">
            <div className="panel-header access-list-heading">
              <div><p className="section-kicker">RESUMEN</p><h2>Devoluciones acumuladas</h2></div>
              <span className="table-hint">Histórico de todos los turnos</span>
            </div>
            {returnsLoading && !returns ? <p className="panel-hint">Consultando devoluciones…</p> : (
              <div className="pos-cash-grid">
                <div className="summary-stat"><span>DEVOLUCIONES</span><strong>{returnSummary.count}</strong><small>registradas</small></div>
                <div className="summary-stat"><span>TOTAL DEVUELTO</span><strong>{formatMoney(returnSummary.total_refund_cents)}</strong></div>
                <div className="summary-stat"><span>EFECTIVO</span><strong>{formatMoney(returnSummary.cash_refund_cents)}</strong><small>baja el efectivo del turno</small></div>
                <div className="summary-stat"><span>TARJETA</span><strong>{formatMoney(returnSummary.card_refund_cents)}</strong><small>reverso declarado</small></div>
                <div className="summary-stat"><span>TRANSFERENCIA</span><strong>{formatMoney(returnSummary.transfer_refund_cents)}</strong><small>reverso declarado</small></div>
              </div>
            )}
            {!cashSession && <p className="panel-hint">Abre un turno de caja desde «Caja y cortes» para registrar devoluciones. Después usa «Devolver» en cualquier venta con unidades disponibles.</p>}
          </section>

          <section className="panel full-panel pos-history-panel">
            <div className="panel-header access-list-heading">
              <div><p className="section-kicker">DEVOLUCIONES</p><h2>Reembolsos y mermas</h2></div>
              <span className="table-hint">{returns ? `${returns.total} ${returns.total === 1 ? "devolución" : "devoluciones"}` : ""}</span>
            </div>
            <div className="table-scroll"><table className="data-table"><thead><tr><th>FOLIO</th><th>VENTA</th><th>HORA</th><th>ARTÍCULOS</th><th>DETALLE</th><th>MÉTODO</th><th>MOTIVO</th><th>RESPONSABLE</th><th>TOTAL</th></tr></thead><tbody>
              {returnsLoading ? <tr><td colSpan={9} className="empty-row">Cargando devoluciones…</td></tr>
                : returnsError ? <tr><td colSpan={9} className="empty-row">{returnsError}</td></tr>
                : returnItems.length === 0 ? <tr><td colSpan={9} className="empty-row">Aún no hay devoluciones. Usa «Devolver» en una venta reciente.</td></tr>
                : returnItems.map((item) => (
                  <tr key={item.id}>
                    <td className="time-cell">{item.folio}</td>
                    <td className="time-cell">{item.sale_folio}</td>
                    <td className="time-cell">{formatSaleTime(item.returned_at)}</td>
                    <td>{item.lines.reduce((sum, line) => sum + line.quantity, 0)} artículos</td>
                    <td>{item.lines.map((line) => `${line.quantity}× ${line.product_name}${line.disposition === "write_off" ? " (merma)" : ""}`).join(", ")}</td>
                    <td>{paymentMethodLabels[item.refund_method] ?? item.refund_method}</td>
                    <td>{item.reason}</td>
                    <td>{item.actor_email ?? "—"}</td>
                    <td className="time-cell">{formatMoney(item.total_refund_cents)}</td>
                  </tr>
                ))}
            </tbody></table></div>
            {returns && returns.pages > 1 && (
              <div className="table-bottom"><span>{returns.total} devoluciones registradas</span><span className="member-pagination"><span>Página {returns.page} de {returns.pages}</span><button type="button" aria-label="Página anterior" disabled={returnsPage <= 1} onClick={() => setReturnsPage(Math.max(1, returnsPage - 1))}>‹</button><button type="button" aria-label="Página siguiente" disabled={returnsPage >= returns.pages} onClick={() => setReturnsPage(Math.min(returns.pages, returnsPage + 1))}>›</button></span></div>
            )}
          </section>
        </>
      )}

      {tab === "cuentas" && canReadSales && (
        <>
          <section className="panel full-panel pos-cash-panel">
            <div className="panel-header access-list-heading">
              <div><p className="section-kicker">CUENTAS POR COBRAR</p><h2>Saldo de socios</h2></div>
              <div className="pos-header-actions">
                <span className="table-hint">Corte al {formatDateOnly(accounts?.as_of ?? null)} · pagos y devoluciones se aplican al cargo más antiguo</span>
                {canSell && <button className="button button-secondary" onClick={() => setReminderOpen(true)}><Bell size={17} />Recordatorios</button>}
                {canManageCredit && <button className="button button-primary" onClick={() => setCreditLookupOpen(true)}><Wallet size={17} />Asignar límite</button>}
              </div>
            </div>
            <div className="pos-cash-grid">
              <div className="summary-stat"><span>TOTAL POR COBRAR</span><strong className="stat-orange">{formatMoney(accounts?.total_receivable_cents ?? 0)}</strong><small>saldo pendiente</small></div>
              <div className="summary-stat"><span>SOCIOS CON SALDO</span><strong>{accounts?.members_with_balance ?? 0}</strong><small>cuentas activas</small></div>
              <div className="summary-stat"><span>SALDO A FAVOR</span><strong>{formatMoney(accounts?.total_credit_cents ?? 0)}</strong><small>por devoluciones</small></div>
            </div>
            <div className="pos-aging-grid" role="group" aria-label="Antigüedad de saldos">
              <div className="summary-stat"><span>0–30 DÍAS</span><strong>{formatMoney(accounts?.aging.current_cents ?? 0)}</strong><small>corriente</small></div>
              <div className="summary-stat"><span>31–60 DÍAS</span><strong>{formatMoney(accounts?.aging.days_31_60_cents ?? 0)}</strong><small>por vencer</small></div>
              <div className="summary-stat"><span>61–90 DÍAS</span><strong>{formatMoney(accounts?.aging.days_61_90_cents ?? 0)}</strong><small>atrasado</small></div>
              <div className="summary-stat"><span>+90 DÍAS</span><strong className="stat-orange">{formatMoney(accounts?.aging.over_90_cents ?? 0)}</strong><small>antigüedad crítica</small></div>
              <div className="summary-stat"><span>SOBRE LÍMITE</span><strong className={(accounts?.over_limit_members ?? 0) > 0 ? "stat-orange" : ""}>{accounts?.over_limit_members ?? 0}</strong><small>socios excedidos</small></div>
            </div>
            {!cashSession && <p className="panel-hint">Abre un turno de caja para registrar cobros. Los saldos se pueden consultar en cualquier momento.</p>}
          </section>

          <section className="panel full-panel pos-history-panel">
            <div className="panel-header access-list-heading">
              <div><p className="section-kicker">SALDOS</p><h2>Socios con saldo</h2></div>
              <span className="table-hint">{accounts ? `${accounts.total} ${accounts.total === 1 ? "cuenta" : "cuentas"}` : ""}</span>
            </div>
            <div className="table-toolbar">
              <label className="table-search"><Search size={17} /><input value={accountSearch} onChange={(event) => setAccountSearch(event.target.value)} placeholder="Buscar por nombre, correo o teléfono" /></label>
              <button type="button" className={accountOverLimit ? "button button-primary" : "button button-secondary"} onClick={() => { setAccountOverLimit((value) => !value); setAccountsPage(1); }}>Sobre límite · {accounts?.over_limit_members ?? 0}</button>
              {accountQuery ? <button className="button button-secondary" onClick={() => setAccountSearch("")}>Limpiar</button> : <span className="table-hint">Los socios sin adeudo no aparecen en la lista</span>}
            </div>
            <div className="table-scroll"><table className="data-table"><thead><tr><th>SOCIO</th><th>ESTADO</th><th>CARGOS</th><th>ABONOS</th><th>CRÉDITO</th><th>SALDO</th><th>ÚLTIMO MOVIMIENTO</th><th /></tr></thead><tbody>
              {accountsLoading ? <tr><td colSpan={8} className="empty-row">Cargando cuentas…</td></tr>
                : accountsError ? <tr><td colSpan={8} className="empty-row">{accountsError}</td></tr>
                : accountItems.length === 0 ? <tr><td colSpan={8} className="empty-row">{accountOverLimit ? "No hay socios sobre su límite de crédito." : accountQuery ? "No hay cuentas que coincidan." : "No hay saldos pendientes. Las ventas a cuenta aparecerán aquí."}</td></tr>
                : accountItems.map((item) => {
                  const initials = item.member_name.split(/\s+/).slice(0, 2).map((part) => part[0] ?? "").join("").toUpperCase();
                  const statusLabel = item.member_status === "active" ? "Activo" : item.member_status === "inactive" ? "Inactivo" : "Pendiente";
                  const statusClass = item.member_status === "active" ? "status-good" : item.member_status === "inactive" ? "status-bad" : "status-neutral";
                  return (
                    <tr key={item.member_id}>
                      <td><div className="person-cell"><span className="person-avatar blue">{initials}</span><span><strong>{item.member_name}</strong><small>{item.email ?? item.phone ?? "Socio"}</small></span></div></td>
                      <td><span className={`status-badge ${statusClass}`}><i />{statusLabel}</span></td>
                      <td className="time-cell">{item.charges_count} · {formatMoney(item.charges_cents)}</td>
                      <td className="time-cell">{item.payments_count} · {formatMoney(item.payments_cents)}</td>
                      <td className="time-cell">{item.credit_limit_cents === null
                        ? <span className="table-hint">Sin límite</span>
                        : <><strong>{formatMoney(item.credit_limit_cents)}</strong><small className={item.over_limit ? "stat-orange" : ""}>{item.over_limit ? `Excedido por ${formatMoney(item.balance_cents - item.credit_limit_cents)}` : `Disponible ${formatMoney(Math.max(item.credit_available_cents ?? 0, 0))}`}</small></>}</td>
                      <td className="time-cell"><strong className={item.balance_cents < 0 ? "stat-orange" : ""}>{formatMoney(item.balance_cents)}</strong></td>
                      <td className="time-cell">{item.last_activity_at ? formatSaleTime(item.last_activity_at) : "—"}</td>
                      <td><div className="pos-row-actions"><button type="button" className="text-button" onClick={() => setAccountMember(item)}>Ver cuenta</button></div></td>
                    </tr>
                  );
                })}
            </tbody></table></div>
            {accounts && accounts.pages > 1 && (
              <div className="table-bottom"><span>{accounts.total} cuentas con saldo</span><span className="member-pagination"><span>Página {accounts.page} de {accounts.pages}</span><button type="button" aria-label="Página anterior" disabled={accountsPage <= 1} onClick={() => setAccountsPage(Math.max(1, accountsPage - 1))}>‹</button><button type="button" aria-label="Página siguiente" disabled={accountsPage >= accounts.pages} onClick={() => setAccountsPage(Math.min(accounts.pages, accountsPage + 1))}>›</button></span></div>
            )}
          </section>
        </>
      )}

      {tab === "compras" && canReadInventory && (
        <>
          <section className="panel full-panel pos-cash-panel">
            <div className="panel-header access-list-heading">
              <div><p className="section-kicker">COMPRAS</p><h2>Órdenes de compra</h2></div>
              {canManageCatalog && <button className="button button-primary" onClick={() => setOrderModalOpen(true)}><Plus size={17} />Nueva orden</button>}
            </div>
            <div className="pos-stat-row" role="group" aria-label="Filtrar órdenes por estado">
              <button type="button" className={ordersStatus === "" ? "pos-stat-active" : ""} onClick={() => setOrdersStatus("")}><span>TOTAL</span><strong>{orderSummary.count}</strong><small>órdenes</small></button>
              <button type="button" className={ordersStatus === "created" ? "pos-stat-active" : ""} onClick={() => setOrdersStatus(ordersStatus === "created" ? "" : "created")}><span>CREADAS</span><strong>{orderSummary.created}</strong><small>por enviar</small></button>
              <button type="button" className={ordersStatus === "sent" ? "pos-stat-active" : ""} onClick={() => setOrdersStatus(ordersStatus === "sent" ? "" : "sent")}><span>ENVIADAS</span><strong className="stat-orange">{orderSummary.sent}</strong><small>por recibir</small></button>
              <button type="button" className={ordersStatus === "received" ? "pos-stat-active" : ""} onClick={() => setOrdersStatus(ordersStatus === "received" ? "" : "received")}><span>RECIBIDAS</span><strong>{orderSummary.received}</strong><small>cerradas</small></button>
              <button type="button" className={ordersStatus === "cancelled" ? "pos-stat-active" : ""} onClick={() => setOrdersStatus(ordersStatus === "cancelled" ? "" : "cancelled")}><span>CANCELADAS</span><strong>{orderSummary.cancelled}</strong><small>sin efecto</small></button>
            </div>
            <p className="panel-hint">Valor comprometido (excluye canceladas): <strong>{formatMoney(orderSummary.total_cents)}</strong>. Al recibir mercancía sube la existencia del producto y se actualiza su costo de reposición.</p>
          </section>

          <section className="panel full-panel pos-history-panel">
            <div className="panel-header access-list-heading">
              <div><p className="section-kicker">ÓRDENES</p><h2>Órdenes registradas</h2></div>
              <span className="table-hint">{orders ? `${orders.total} ${orders.total === 1 ? "orden" : "órdenes"}` : ""}</span>
            </div>
            <div className="table-scroll"><table className="data-table"><thead><tr><th>FOLIO</th><th>PROVEEDOR</th><th>CREADA</th><th>ESPERADA</th><th>ARTÍCULOS</th><th>RECIBIDO</th><th>TOTAL</th><th>ESTADO</th>{canManageCatalog && <th />}</tr></thead><tbody>
              {ordersLoading ? <tr><td colSpan={canManageCatalog ? 9 : 8} className="empty-row">Cargando órdenes…</td></tr>
                : ordersError ? <tr><td colSpan={canManageCatalog ? 9 : 8} className="empty-row">{ordersError}</td></tr>
                : orderItems.length === 0 ? <tr><td colSpan={canManageCatalog ? 9 : 8} className="empty-row">{ordersStatus ? "No hay órdenes con ese estado." : "Aún no hay órdenes de compra. Crea una para reabastecer el inventario."}</td></tr>
                : orderItems.map((order) => {
                  const orderedUnits = order.lines.reduce((sum, line) => sum + line.quantity, 0);
                  const receivedUnits = order.lines.reduce((sum, line) => sum + line.received_quantity, 0);
                  const pending = orderedUnits - receivedUnits;
                  return (
                    <tr key={order.id}>
                      <td className="time-cell">{order.folio}</td>
                      <td>{order.supplier_name}</td>
                      <td className="time-cell">{formatSaleTime(order.created_at)}</td>
                      <td className="time-cell">{order.expected_at ? formatDateOnly(order.expected_at) : "—"}</td>
                      <td>{orderedUnits} artículos</td>
                      <td>{receivedUnits} de {orderedUnits}{pending > 0 ? ` · faltan ${pending}` : ""}</td>
                      <td className="time-cell">{formatMoney(order.total_cents)}</td>
                      <td><span className={`status-badge ${purchaseOrderStatusBadges[order.status] ?? "status-neutral"}`}><i />{purchaseOrderStatusLabels[order.status] ?? order.status}</span></td>
                      {canManageCatalog && (
                        <td><div className="pos-row-actions">
                          {order.status === "created" && <button type="button" className="text-button" onClick={() => void changeOrderState(order, "send")}>Enviar</button>}
                          {(order.status === "created" || order.status === "sent") && <button type="button" className="text-button" onClick={() => setReceiveOrder(order)}>Recibir</button>}
                          {(order.status === "created" || order.status === "sent") && <button type="button" className="text-button" onClick={() => void changeOrderState(order, "cancel")}>Cancelar</button>}
                          {(order.status === "received" || order.status === "cancelled") && <span className="table-hint">—</span>}
                        </div></td>
                      )}
                    </tr>
                  );
                })}
            </tbody></table></div>
            {orders && orders.pages > 1 && (
              <div className="table-bottom"><span>{orders.total} órdenes registradas</span><span className="member-pagination"><span>Página {orders.page} de {orders.pages}</span><button type="button" aria-label="Página anterior" disabled={ordersPage <= 1} onClick={() => setOrdersPage(Math.max(1, ordersPage - 1))}>‹</button><button type="button" aria-label="Página siguiente" disabled={ordersPage >= orders.pages} onClick={() => setOrdersPage(Math.min(orders.pages, ordersPage + 1))}>›</button></span></div>
            )}
          </section>

          <section className="panel full-panel">
            <div className="panel-header access-list-heading">
              <div><p className="section-kicker">PROVEEDORES</p><h2>Directorio</h2></div>
              {canManageCatalog && <button className="button button-primary" onClick={() => setSupplierModal({ supplier: null })}><Plus size={17} />Nuevo proveedor</button>}
            </div>
            <div className="table-toolbar">
              <label className="table-search"><Search size={17} /><input value={supplierSearch} onChange={(event) => setSupplierSearch(event.target.value)} placeholder="Buscar por nombre, contacto, teléfono o correo" /></label>
              <span className="table-hint">Los proveedores inactivos no aceptan órdenes nuevas</span>
            </div>
            <div className="table-scroll"><table className="data-table"><thead><tr><th>PROVEEDOR</th><th>CONTACTO</th><th>TELÉFONO</th><th>CORREO</th><th>ESTADO</th>{canManageCatalog && <th />}</tr></thead><tbody>
              {suppliersLoading ? <tr><td colSpan={canManageCatalog ? 6 : 5} className="empty-row">Cargando proveedores…</td></tr>
                : suppliersError ? <tr><td colSpan={canManageCatalog ? 6 : 5} className="empty-row">{suppliersError}</td></tr>
                : supplierItems.length === 0 ? <tr><td colSpan={canManageCatalog ? 6 : 5} className="empty-row">{supplierQuery ? "No hay proveedores que coincidan." : "Aún no hay proveedores registrados."}</td></tr>
                : supplierItems.map((supplier) => (
                  <tr key={supplier.id}>
                    <td><div className="person-cell"><span className="pos-row-icon"><Truck size={15} /></span><span><strong>{supplier.name}</strong><small>{supplier.notes ?? "—"}</small></span></div></td>
                    <td>{supplier.contact_name ?? "—"}</td>
                    <td>{supplier.phone ?? "—"}</td>
                    <td>{supplier.email ?? "—"}</td>
                    <td><span className={`status-badge ${supplier.is_active ? "status-good" : "status-neutral"}`}><i />{supplier.is_active ? "Activo" : "Inactivo"}</span></td>
                    {canManageCatalog && <td><div className="pos-row-actions"><button type="button" className="text-button" onClick={() => setSupplierModal({ supplier })}>Editar</button></div></td>}
                  </tr>
                ))}
            </tbody></table></div>
            <div className="table-bottom">
              <span>{supplierTotal} {supplierTotal === 1 ? "proveedor" : "proveedores"} registrados</span>
              {supplierPages > 1 && (
                <span className="member-pagination"><span>Página {suppliersPage} de {supplierPages}</span><button type="button" aria-label="Página anterior" disabled={suppliersPage <= 1} onClick={() => setSuppliersPage(Math.max(1, suppliersPage - 1))}>‹</button><button type="button" aria-label="Página siguiente" disabled={suppliersPage >= supplierPages} onClick={() => setSuppliersPage(Math.min(supplierPages, suppliersPage + 1))}>›</button></span>
              )}
            </div>
          </section>
        </>
      )}

      <footer className="page-footer"><span>Centro Fit · Punto de venta e inventario</span><span>DATOS DEL BACKEND · PAGOS CON TERMINAL NO CONECTADOS</span></footer>

      {productModal && canManageCatalog && <ProductFormModal product={productModal.product} categories={categories} onClose={() => setProductModal(null)} onSaved={handleProductSaved} />}
      {stockModal && canManageCatalog && <StockMovementModal product={stockModal} onClose={() => setStockModal(null)} onSaved={handleStockSaved} />}
      {openCashOpen && canSell && <OpenCashModal onClose={() => setOpenCashOpen(false)} onOpened={handleCashOpened} />}
      {closeCashOpen && canSell && cashSession && <CloseCashModal cashSession={cashSession} onClose={() => setCloseCashOpen(false)} onClosed={handleCashClosed} />}
      {returnSale && canSell && <SaleReturnModal sale={returnSale} onClose={() => setReturnSale(null)} onSaved={handleReturnSaved} />}
      {serviceRefundSale && canRefundServices && <ServiceRefundModal sale={serviceRefundSale} onClose={() => setServiceRefundSale(null)} onSaved={handleServiceRefundSaved} />}
      {accountMember && <MemberAccountModal member={accountMember} canManage={canSell} canManageCredit={canManageCredit} cashSessionOpen={Boolean(cashSession)} onClose={() => setAccountMember(null)} onSaved={handleAccountSaved} />}
      {reminderOpen && canSell && <CollectionReminderModal onClose={() => setReminderOpen(false)} onSaved={handleAccountSaved} onUnauthorized={onUnauthorized} />}
      {creditLookupOpen && canManageCredit && <CreditLimitLookupModal onSelect={(summary) => { setAccountMember(summary); setCreditLookupOpen(false); }} onClose={() => setCreditLookupOpen(false)} onUnauthorized={onUnauthorized} />}
      {supplierModal && canManageCatalog && <SupplierFormModal supplier={supplierModal.supplier} onClose={() => setSupplierModal(null)} onSaved={handleSupplierSaved} />}
      {orderModalOpen && canManageCatalog && <PurchaseOrderFormModal onClose={() => setOrderModalOpen(false)} onSaved={handleOrderSaved} onUnauthorized={onUnauthorized} />}
      {receiveOrder && canManageCatalog && <ReceivePurchaseOrderModal order={receiveOrder} onClose={() => setReceiveOrder(null)} onSaved={handleOrderSaved} />}
    </>
  );
}

function ProductFormModal({ product, categories, onClose, onSaved }: { product: BackendProduct | null; categories: string[]; onClose: () => void; onSaved: (message: string) => void }) {
  const editing = product !== null;
  const [sku, setSku] = useState(product?.sku ?? "");
  const [name, setName] = useState(product?.name ?? "");
  const [category, setCategory] = useState(product?.category ?? "");
  const [barcode, setBarcode] = useState(product?.barcode ?? "");
  const [price, setPrice] = useState(product ? (product.price_cents / 100).toFixed(2) : "");
  const [cost, setCost] = useState(product && product.cost_cents !== null ? (product.cost_cents / 100).toFixed(2) : "");
  const [stockMin, setStockMin] = useState(product ? String(product.stock_min) : "0");
  const [initialStock, setInitialStock] = useState("0");
  const [isActive, setIsActive] = useState(product?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) { setError("El nombre es obligatorio."); return; }
    if (!editing && !sku.trim()) { setError("El SKU es obligatorio."); return; }
    const priceCents = parseMoneyToCents(price);
    if (priceCents === null) { setError("Indica un precio válido."); return; }
    const costCents = cost.trim() === "" ? null : parseMoneyToCents(cost);
    if (cost.trim() !== "" && costCents === null) { setError("El costo no es válido."); return; }
    const stockMinValue = Number.parseInt(stockMin, 10);
    if (!Number.isFinite(stockMinValue) || stockMinValue < 0) { setError("El stock mínimo debe ser cero o mayor."); return; }
    const initialStockValue = Number.parseInt(initialStock, 10);
    if (!editing && (!Number.isFinite(initialStockValue) || initialStockValue < 0)) { setError("La existencia inicial debe ser cero o mayor."); return; }

    setBusy(true);
    setError("");
    try {
      const response = editing && product
        ? await fetch(`/api/admin/products/${product.id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: trimmedName,
              category: category.trim() || null,
              barcode: barcode.trim() || null,
              price_cents: priceCents,
              cost_cents: costCents,
              stock_min: stockMinValue,
              is_active: isActive,
            }),
          })
        : await fetch("/api/admin/products", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              sku: sku.trim(),
              name: trimmedName,
              category: category.trim() || null,
              barcode: barcode.trim() || null,
              price_cents: priceCents,
              cost_cents: costCents,
              stock_min: stockMinValue,
              initial_stock: initialStockValue,
            }),
          });
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) {
        setError(payload.detail || "No se pudo guardar el producto.");
        return;
      }
      onSaved(editing ? "Producto actualizado." : `Producto creado: ${trimmedName}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="product-title">
        <div className="modal-header"><span className="modal-icon"><Package size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">{editing ? "EDITAR PRODUCTO" : "ALTA DE PRODUCTO"}</p>
        <h2 id="product-title">{editing ? product?.name : "Nuevo producto"}</h2>
        <p className="modal-subtitle">Los precios se guardan en pesos; el inventario se controla por el mostrador.</p>
        <form onSubmit={submit}>
          <div className="form-row">
            <label className="form-field"><span>SKU</span><input value={sku} onChange={(event) => setSku(event.target.value)} placeholder="Ej. AGUA-600" disabled={editing} maxLength={60} /></label>
            <label className="form-field"><span>Categoría</span><input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="General" list="product-categories" maxLength={80} /></label>
          </div>
          <datalist id="product-categories">{categories.map((item) => <option key={item} value={item} />)}</datalist>
          <label className="form-field"><span>Nombre</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Ej. Agua 600 ml" maxLength={160} /></label>
          <label className="form-field"><span>Código de barras (opcional)</span><input value={barcode} onChange={(event) => setBarcode(event.target.value)} placeholder="7501234567890" maxLength={64} /></label>
          <div className="form-row">
            <label className="form-field"><span>Precio de venta</span><input value={price} onChange={(event) => setPrice(event.target.value)} placeholder="0.00" inputMode="decimal" /></label>
            <label className="form-field"><span>Costo (opcional)</span><input value={cost} onChange={(event) => setCost(event.target.value)} placeholder="0.00" inputMode="decimal" /></label>
          </div>
          <div className="form-row">
            <label className="form-field"><span>Stock mínimo</span><input value={stockMin} onChange={(event) => setStockMin(event.target.value)} inputMode="numeric" /></label>
            {editing
              ? <label className="form-field"><span>Estado</span><select value={isActive ? "active" : "inactive"} onChange={(event) => setIsActive(event.target.value === "active")}><option value="active">Activo</option><option value="inactive">Inactivo</option></select></label>
              : <label className="form-field"><span>Existencia inicial</span><input value={initialStock} onChange={(event) => setInitialStock(event.target.value)} inputMode="numeric" /></label>}
          </div>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : editing ? "Guardar cambios" : "Crear producto"}</button></div>
        </form>
      </section>
    </div>
  );
}

function StockMovementModal({ product, onClose, onSaved }: { product: BackendProduct; onClose: () => void; onSaved: (message: string) => void }) {
  const [movementType, setMovementType] = useState<"intake" | "adjustment" | "waste">("intake");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsed = Number.parseInt(quantity, 10);
    if (!Number.isFinite(parsed) || parsed === 0) { setError("Indica una cantidad distinta de cero."); return; }
    if (movementType === "intake" && parsed < 0) { setError("La entrada debe ser una cantidad positiva."); return; }
    if (movementType === "waste" && parsed < 0) { setError("La merma debe ser una cantidad positiva."); return; }
    if ((movementType === "adjustment" || movementType === "waste") && !reason.trim()) { setError("El motivo es obligatorio para ajustes y mermas."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/products/${product.id}/stock`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ movement_type: movementType, quantity: parsed, reason: reason.trim() || null }),
      });
      const payload = await response.json().catch(() => ({})) as { detail?: string; stock?: number };
      if (!response.ok) {
        setError(payload.detail || "No se pudo registrar el movimiento.");
        return;
      }
      onSaved(`Movimiento registrado. Existencia de ${product.name}: ${payload.stock ?? "—"}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="stock-title">
        <div className="modal-header"><span className="modal-icon"><Tags size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">MOVIMIENTO DE INVENTARIO</p>
        <h2 id="stock-title">{product.name}</h2>
        <p className="modal-subtitle">Existencia actual: {product.stock} · mínimo {product.stock_min}. Cada movimiento queda en la bitácora del producto.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Tipo de movimiento</span><select value={movementType} onChange={(event) => setMovementType(event.target.value as "intake" | "adjustment" | "waste")}><option value="intake">Entrada</option><option value="adjustment">Ajuste (+/-)</option><option value="waste">Merma</option></select></label>
          <label className="form-field"><span>Cantidad</span><input value={quantity} onChange={(event) => setQuantity(event.target.value)} placeholder={movementType === "adjustment" ? "Ej. -2 o 5" : "Ej. 10"} inputMode="numeric" autoFocus /></label>
          <label className="form-field"><span>Motivo {movementType === "intake" ? "(opcional)" : ""}</span><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder={movementType === "waste" ? "Caducado, roto…" : "Conteo físico, compra…"} maxLength={200} /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-note"><ShieldCheck size={16} /><span>El inventario nunca puede quedar en negativo; una merma mayor a la existencia se rechaza.</span></div>
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Registrando…" : "Registrar movimiento"}</button></div>
        </form>
      </section>
    </div>
  );
}

function SupplierFormModal({ supplier, onClose, onSaved }: { supplier: BackendSupplier | null; onClose: () => void; onSaved: (message: string) => void }) {
  const editing = supplier !== null;
  const [name, setName] = useState(supplier?.name ?? "");
  const [contactName, setContactName] = useState(supplier?.contact_name ?? "");
  const [phone, setPhone] = useState(supplier?.phone ?? "");
  const [email, setEmail] = useState(supplier?.email ?? "");
  const [notes, setNotes] = useState(supplier?.notes ?? "");
  const [isActive, setIsActive] = useState(supplier?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim()) { setError("Indica el nombre del proveedor."); return; }
    setBusy(true);
    setError("");
    const body = {
      name: name.trim(),
      contact_name: contactName.trim() || null,
      phone: phone.trim() || null,
      email: email.trim() || null,
      notes: notes.trim() || null,
    };
    try {
      const response = editing
        ? await fetch(`/api/admin/suppliers/${supplier.id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...body, is_active: isActive }),
          })
        : await fetch("/api/admin/suppliers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo guardar el proveedor."); return; }
      onSaved(editing ? "Proveedor actualizado." : "Proveedor registrado.");
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="supplier-title">
        <div className="modal-header"><span className="modal-icon"><Truck size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">PROVEEDOR</p>
        <h2 id="supplier-title">{editing ? "Editar proveedor" : "Nuevo proveedor"}</h2>
        <p className="modal-subtitle">Los proveedores son el origen de las órdenes de compra. Un proveedor inactivo conserva su historial pero no acepta órdenes nuevas.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Nombre</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Distribuidora Norte" maxLength={160} autoFocus /></label>
          <div className="form-row">
            <label className="form-field"><span>Contacto</span><input value={contactName} onChange={(event) => setContactName(event.target.value)} placeholder="Ana Ruiz" maxLength={120} /></label>
            <label className="form-field"><span>Teléfono</span><input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="55 1234 5678" maxLength={40} /></label>
          </div>
          <label className="form-field"><span>Correo</span><input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="ventas@proveedor.mx" maxLength={160} /></label>
          <label className="form-field"><span>Notas (opcional)</span><input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Condiciones, días de entrega…" maxLength={200} /></label>
          {editing && <label className="form-field"><span>Estado</span><select value={isActive ? "active" : "inactive"} onChange={(event) => setIsActive(event.target.value === "active")}><option value="active">Activo</option><option value="inactive">Inactivo</option></select></label>}
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : editing ? "Guardar cambios" : "Registrar proveedor"}</button></div>
        </form>
      </section>
    </div>
  );
}

type OrderLineDraft = { key: string; product_id: string; quantity: string; unit_cost: string };

function PurchaseOrderFormModal({ onClose, onSaved, onUnauthorized }: { onClose: () => void; onSaved: (message: string) => void; onUnauthorized: () => void }) {
  const [suppliers, setSuppliers] = useState<BackendSupplier[]>([]);
  const [products, setProducts] = useState<BackendProduct[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [supplierId, setSupplierId] = useState("");
  const [expectedAt, setExpectedAt] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<OrderLineDraft[]>([{ key: "line-1", product_id: "", quantity: "1", unit_cost: "" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoadingOptions(true);
      try {
        const [suppliersResponse, productsResponse] = await Promise.all([
          fetch("/api/admin/suppliers?page_size=100&active=true", { cache: "no-store" }),
          fetch("/api/admin/products?page_size=100", { cache: "no-store" }),
        ]);
        if (suppliersResponse.status === 401 || productsResponse.status === 401) { onUnauthorized(); return; }
        if (!suppliersResponse.ok || !productsResponse.ok) throw new Error("No se pudieron cargar las opciones.");
        const supplierDirectory = await suppliersResponse.json() as SupplierDirectory;
        const productDirectory = await productsResponse.json() as ProductDirectory;
        if (!active) return;
        setSuppliers(supplierDirectory.items);
        setProducts(productDirectory.items.filter((item) => item.is_active));
      } catch {
        if (active) setError("No se pudieron cargar proveedores y productos.");
      } finally {
        if (active) setLoadingOptions(false);
      }
    };
    void load();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateLine = (key: string, patch: Partial<OrderLineDraft>) => {
    setLines((current) => current.map((line) => line.key === key ? { ...line, ...patch } : line));
  };
  const addLine = () => setLines((current) => [...current, { key: `line-${Date.now()}-${current.length}`, product_id: "", quantity: "1", unit_cost: "" }]);
  const removeLine = (key: string) => setLines((current) => current.length <= 1 ? current : current.filter((line) => line.key !== key));
  const chooseProduct = (key: string, productId: string) => {
    const product = products.find((item) => item.id === productId);
    updateLine(key, { product_id: productId, unit_cost: product && product.cost_cents !== null ? (product.cost_cents / 100).toFixed(2) : "" });
  };

  const parsedLines = lines.map((line) => ({ product_id: line.product_id, quantity: Number.parseInt(line.quantity, 10), cost: parseMoneyToCents(line.unit_cost) }));
  const totalCents = parsedLines.reduce((sum, line) => sum + (Number.isFinite(line.quantity) && line.cost !== null ? line.quantity * line.cost : 0), 0);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!supplierId) { setError("Selecciona un proveedor."); return; }
    if (parsedLines.some((line) => !line.product_id)) { setError("Selecciona un producto en cada línea."); return; }
    if (parsedLines.some((line) => !Number.isFinite(line.quantity) || line.quantity <= 0)) { setError("Cada línea necesita una cantidad mayor que cero."); return; }
    if (parsedLines.some((line) => line.cost === null)) { setError("Cada línea necesita un costo válido."); return; }
    const productIds = parsedLines.map((line) => line.product_id);
    if (new Set(productIds).size !== productIds.length) { setError("Un producto no puede repetirse en la orden."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/purchase-orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          supplier_id: supplierId,
          items: parsedLines.map((line) => ({ product_id: line.product_id, quantity: line.quantity, unit_cost_cents: line.cost })),
          expected_at: expectedAt || null,
          notes: notes.trim() || null,
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string; folio?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo crear la orden."); return; }
      onSaved(`Orden ${payload.folio ?? ""} creada.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="purchase-order-title">
        <div className="modal-header"><span className="modal-icon"><ClipboardList size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">ORDEN DE COMPRA</p>
        <h2 id="purchase-order-title">Nueva orden</h2>
        <p className="modal-subtitle">Registra lo que pedirás al proveedor. La existencia solo sube cuando la orden se recibe.</p>
        <form onSubmit={submit}>
          <div className="form-row">
            <label className="form-field"><span>Proveedor</span><select value={supplierId} onChange={(event) => setSupplierId(event.target.value)} disabled={loadingOptions} autoFocus><option value="">{loadingOptions ? "Cargando…" : "Selecciona un proveedor"}</option>{suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}</option>)}</select></label>
            <label className="form-field"><span>Fecha estimada (opcional)</span><input type="date" value={expectedAt} onChange={(event) => setExpectedAt(event.target.value)} /></label>
          </div>

          <div className="pos-order-lines">
            <div className="pos-order-lines-head"><span>PRODUCTO</span><span>CANTIDAD</span><span>COSTO UNITARIO</span><span>IMPORTE</span><span /></div>
            {lines.map((line) => {
              const product = products.find((item) => item.id === line.product_id);
              const cost = parseMoneyToCents(line.unit_cost);
              const quantity = Number.parseInt(line.quantity, 10);
              const lineTotal = Number.isFinite(quantity) && cost !== null ? quantity * cost : 0;
              return (
                <div className="pos-order-line" key={line.key}>
                  <select value={line.product_id} onChange={(event) => chooseProduct(line.key, event.target.value)} disabled={loadingOptions}><option value="">{loadingOptions ? "Cargando…" : "Selecciona"}</option>{products.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.sku}</option>)}</select>
                  <input value={line.quantity} onChange={(event) => updateLine(line.key, { quantity: event.target.value })} inputMode="numeric" placeholder="1" />
                  <input value={line.unit_cost} onChange={(event) => updateLine(line.key, { unit_cost: event.target.value })} inputMode="decimal" placeholder="0.00" />
                  <span className="pos-order-line-total">{formatMoney(lineTotal)}{product && product.stock <= product.stock_min ? <small className="pos-min">stock bajo</small> : null}</span>
                  <button type="button" className="icon-button pos-remove" aria-label="Quitar línea" onClick={() => removeLine(line.key)} disabled={lines.length <= 1}><Trash2 size={14} /></button>
                </div>
              );
            })}
            <button type="button" className="button button-secondary button-small pos-order-add" onClick={addLine}><Plus size={15} />Agregar producto</button>
          </div>

          <label className="form-field"><span>Notas (opcional)</span><input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Referencia, condiciones de entrega…" maxLength={200} /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-note"><ShieldCheck size={16} /><span>No se puede pedir el mismo producto dos veces en una orden. El total es informativo; el costo real se fija al recibir.</span></div>
          <div className="pos-total"><span>Total estimado</span><strong>{formatMoney(totalCents)}</strong></div>
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy || loadingOptions}><Check size={16} />{busy ? "Creando…" : "Crear orden"}</button></div>
        </form>
      </section>
    </div>
  );
}

function ReceivePurchaseOrderModal({ order, onClose, onSaved }: { order: BackendPurchaseOrder; onClose: () => void; onSaved: (message: string) => void }) {
  const pendingLines = order.lines.filter((line) => line.pending_quantity > 0);
  const [quantities, setQuantities] = useState<Record<string, string>>(() => Object.fromEntries(order.lines.map((line) => [line.item_id, String(line.pending_quantity)])));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const setQuantity = (itemId: string, value: string) => setQuantities((current) => ({ ...current, [itemId]: value }));

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const tooMuch = pendingLines.find((line) => (Number.parseInt(quantities[line.item_id] ?? "0", 10) || 0) > line.pending_quantity);
    if (tooMuch) { setError(`No puedes recibir más de ${tooMuch.pending_quantity} de ${tooMuch.product_name}.`); return; }
    const toReceive = pendingLines
      .map((line) => ({ item_id: line.item_id, quantity: Number.parseInt(quantities[line.item_id] ?? "0", 10) }))
      .filter((item) => Number.isFinite(item.quantity) && item.quantity > 0);
    if (toReceive.length === 0) { setError("Indica al menos una cantidad recibida."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/purchase-orders/${order.id}/receive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: toReceive }),
      });
      const payload = await response.json().catch(() => ({})) as { detail?: string; status?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo registrar la recepción."); return; }
      onSaved(payload.status === "received" ? `Orden ${order.folio} recibida por completo.` : `Recepción parcial de ${order.folio} registrada.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="receive-order-title">
        <div className="modal-header"><span className="modal-icon"><ShoppingBasket size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">RECEPCIÓN DE MERCANCÍA</p>
        <h2 id="receive-order-title">{order.folio}</h2>
        <p className="modal-subtitle">{order.supplier_name} · ajusta las cantidades que realmente llegaron. Una entrega incompleta deja la orden abierta para completarla después.</p>
        <form onSubmit={submit}>
          <div className="table-scroll"><table className="data-table"><thead><tr><th>PRODUCTO</th><th>PEDIDO</th><th>RECIBIDO</th><th>PENDIENTE</th><th>RECIBIR AHORA</th></tr></thead><tbody>
            {pendingLines.length === 0 ? <tr><td colSpan={5} className="empty-row">Esta orden ya está completa.</td></tr>
              : pendingLines.map((line) => (
                <tr key={line.item_id}>
                  <td><div className="person-cell"><span className="pos-row-icon"><Package size={15} /></span><span><strong>{line.product_name}</strong><small>{line.sku}</small></span></div></td>
                  <td className="time-cell">{line.quantity}</td>
                  <td className="time-cell">{line.received_quantity}</td>
                  <td className="time-cell">{line.pending_quantity}</td>
                  <td><input className="pos-receive-input" value={quantities[line.item_id] ?? ""} onChange={(event) => setQuantity(line.item_id, event.target.value)} inputMode="numeric" /></td>
                </tr>
              ))}
          </tbody></table></div>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-note"><ShieldCheck size={16} /><span>Recibir mercancía sube la existencia y actualiza el costo de reposición del producto. No se puede recibir más de lo pedido.</span></div>
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy || pendingLines.length === 0}><Check size={16} />{busy ? "Registrando…" : "Registrar recepción"}</button></div>
        </form>
      </section>
    </div>
  );
}

function OpenCashModal({ onClose, onOpened }: { onClose: () => void; onOpened: (message: string) => void }) {
  const [openingCash, setOpeningCash] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cents = parseMoneyToCents(openingCash);
    if (cents === null) { setError("Indica un fondo de caja válido."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/cash-sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ opening_cash_cents: cents }),
      });
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) {
        setError(payload.detail || "No se pudo abrir el turno de caja.");
        return;
      }
      onOpened("Turno de caja abierto.");
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="open-cash-title">
        <div className="modal-header"><span className="modal-icon"><Banknote size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">APERTURA DE CAJA</p>
        <h2 id="open-cash-title">Abrir turno</h2>
        <p className="modal-subtitle">Registra el fondo con el que inicia el turno. Solo puede existir un turno abierto a la vez.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Fondo de caja</span><input value={openingCash} onChange={(event) => setOpeningCash(event.target.value)} placeholder="0.00" inputMode="decimal" autoFocus /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Abriendo…" : "Abrir turno"}</button></div>
        </form>
      </section>
    </div>
  );
}

function CloseCashModal({ cashSession, onClose, onClosed }: { cashSession: CashSession; onClose: () => void; onClosed: (message: string) => void }) {
  const [counted, setCounted] = useState((cashSession.expected_cash_cents / 100).toFixed(2));
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const countedCents = parseMoneyToCents(counted);
  const difference = countedCents === null ? null : countedCents - cashSession.expected_cash_cents;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (countedCents === null) { setError("Indica el efectivo contado."); return; }
    if (difference !== 0 && !notes.trim()) { setError("Explica la diferencia de efectivo para cerrar el turno."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/cash-sessions/${cashSession.id}/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ counted_cash_cents: countedCents, notes: notes.trim() || null }),
      });
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) {
        setError(payload.detail || "No se pudo cerrar el turno.");
        return;
      }
      onClosed("Corte de caja registrado.");
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="close-cash-title">
        <div className="modal-header"><span className="modal-icon"><Receipt size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">CORTE DE CAJA</p>
        <h2 id="close-cash-title">Cerrar turno</h2>
        <p className="modal-subtitle">Turno abierto por {cashSession.opened_by_email ?? "—"} · {cashSession.sales_count} ventas por {formatMoney(cashSession.total_sales_cents)}.</p>
        <form onSubmit={submit}>
          <div className="form-row">
            <label className="form-field"><span>Efectivo esperado</span><input value={formatMoney(cashSession.expected_cash_cents)} readOnly /></label>
            <label className="form-field"><span>Efectivo contado</span><input value={counted} onChange={(event) => setCounted(event.target.value)} inputMode="decimal" autoFocus /></label>
          </div>
          <div className={`modal-feedback pos-difference ${difference !== null && difference !== 0 ? "pos-difference-alert" : ""}`}>
            <span>Diferencia</span>
            <strong>{difference === null ? "—" : formatMoney(difference)}</strong>
          </div>
          <label className="form-field"><span>Notas {difference !== null && difference !== 0 ? "(obligatorias)" : "(opcionales)"}</span><input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Explica faltantes o sobrantes" maxLength={500} /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Cerrando…" : "Cerrar turno"}</button></div>
        </form>
      </section>
    </div>
  );
}

function SaleReturnModal({ sale, onClose, onSaved }: { sale: BackendSale; onClose: () => void; onSaved: (message: string) => void }) {
  const returnableLines = sale.lines.filter((line) => line.returnable_quantity > 0);
  const isAccountSale = sale.payment_method === "account";
  const [quantities, setQuantities] = useState<Record<string, string>>(() =>
    Object.fromEntries(returnableLines.map((line) => [line.sale_item_id, ""])),
  );
  const [dispositions, setDispositions] = useState<Record<string, "restock" | "write_off">>(() =>
    Object.fromEntries(returnableLines.map((line) => [line.sale_item_id, "restock" as const])),
  );
  const [refundMethod, setRefundMethod] = useState(isAccountSale ? "account" : sale.payment_method);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const parsed = returnableLines.map((line) => {
    const raw = quantities[line.sale_item_id] ?? "";
    const value = Number.parseInt(raw, 10);
    const quantity = Number.isFinite(value) ? value : 0;
    return { line, quantity };
  });
  const totalRefund = parsed.reduce((sum, { line, quantity }) => sum + (quantity > 0 ? line.unit_price_cents * quantity : 0), 0);
  const hasSelection = parsed.some(({ quantity }) => quantity > 0);
  const overLimit = parsed.some(({ line, quantity }) => quantity > line.returnable_quantity);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const items = parsed
      .filter(({ quantity }) => quantity > 0)
      .map(({ line, quantity }) => ({ sale_item_id: line.sale_item_id, quantity, disposition: dispositions[line.sale_item_id] ?? "restock" }));
    if (items.length === 0) { setError("Indica cuántas unidades se devuelven en al menos un producto."); return; }
    if (overLimit) { setError("Una cantidad supera lo disponible para devolver."); return; }
    if (!reason.trim()) { setError("El motivo de la devolución es obligatorio."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/sales/${sale.id}/returns`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items, refund_method: refundMethod, reason: reason.trim() }),
      });
      const payload = await response.json().catch(() => ({})) as { detail?: string; folio?: string; total_refund_cents?: number };
      if (!response.ok) { setError(payload.detail || "No se pudo registrar la devolución."); return; }
      onSaved(`Devolución ${payload.folio ?? ""} registrada por ${formatMoney(payload.total_refund_cents ?? totalRefund)}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="sale-return-title">
        <div className="modal-header"><span className="modal-icon"><RotateCcw size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">DEVOLUCIÓN</p>
        <h2 id="sale-return-title">Devolver venta {sale.folio}</h2>
        <p className="modal-subtitle">{sale.member_name ?? "Público general"} · {formatMoney(sale.total_cents)} · {paymentMethodLabels[sale.payment_method] ?? sale.payment_method}</p>
        <form onSubmit={submit}>
          <div className="return-lines">
            {returnableLines.map((line) => (
              <div key={line.sale_item_id} className="return-line">
                <div className="return-line-copy"><strong>{line.product_name}</strong><small>{line.sku} · {formatMoney(line.unit_price_cents)} c/u · disponible {line.returnable_quantity}</small></div>
                <label className="form-field return-qty"><span>Cantidad</span><input value={quantities[line.sale_item_id] ?? ""} onChange={(event) => setQuantities((current) => ({ ...current, [line.sale_item_id]: event.target.value.replace(/[^0-9]/g, "") }))} inputMode="numeric" placeholder="0" maxLength={3} /></label>
                <label className="form-field return-disposition"><span>Destino</span><select value={dispositions[line.sale_item_id] ?? "restock"} onChange={(event) => setDispositions((current) => ({ ...current, [line.sale_item_id]: event.target.value as "restock" | "write_off" }))}><option value="restock">Reingresa a stock</option><option value="write_off">Merma (no revendible)</option></select></label>
              </div>
            ))}
          </div>
          <div className="form-row">
            <label className="form-field"><span>Forma del reembolso</span>{isAccountSale
              ? <select value="account" disabled><option value="account">Cuenta del socio</option></select>
              : <select value={refundMethod} onChange={(event) => setRefundMethod(event.target.value)}><option value="cash">Efectivo</option><option value="card">Tarjeta</option><option value="transfer">Transferencia</option></select>}</label>
            <label className="form-field"><span>Motivo (obligatorio)</span><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Producto defectuoso, cambio de talla" maxLength={200} autoFocus /></label>
          </div>
          {isAccountSale && <p className="manual-hint">La venta se cargó a la cuenta del socio: el importe se abona a su saldo, no sale efectivo de la caja.</p>}
          <div className="modal-feedback pos-difference"><span>Total a reembolsar</span><strong>{formatMoney(totalRefund)}</strong></div>
          {overLimit && <div className="login-error" role="alert">Una cantidad supera lo disponible para devolver.</div>}
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy || !hasSelection}><Check size={16} />{busy ? "Registrando…" : "Registrar devolución"}</button></div>
        </form>
      </section>
    </div>
  );
}

function ServiceRefundModal({ sale, onClose, onSaved }: { sale: BackendSale; onClose: () => void; onSaved: (message: string) => void }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const serviceLine = sale.lines.find((line) => line.product_id === null);
  const isCash = sale.payment_method === "cash";

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!reason.trim()) { setError("El motivo del reembolso es obligatorio."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/sales/${sale.id}/service-refund`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: reason.trim() }),
      });
      const payload = await response.json().catch(() => ({})) as { detail?: string; folio?: string; total_refund_cents?: number };
      if (!response.ok) { setError(payload.detail || "No se pudo reembolsar el servicio."); return; }
      onSaved(`Reembolso ${payload.folio ?? ""} registrado por ${formatMoney(payload.total_refund_cents ?? sale.total_cents)}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="service-refund-title">
        <div className="modal-header"><span className="modal-icon"><RotateCcw size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">REEMBOLSO DE SERVICIO</p>
        <h2 id="service-refund-title">Reembolsar venta {sale.folio}</h2>
        <p className="modal-subtitle">{sale.member_name ?? "Público general"} · {serviceLine?.product_name ?? "Servicio"} · {paymentMethodLabels[sale.payment_method] ?? sale.payment_method}</p>
        <form onSubmit={submit}>
          <p className="manual-hint">Es el cobro de una clase premium: no hay mercancía que reingresar al stock. La reserva de la clase conserva su estado y solo se devuelve el importe.</p>
          {isCash && <p className="manual-hint">El importe sale en efectivo de la caja, así que el turno debe estar abierto.</p>}
          <label className="form-field"><span>Motivo (obligatorio)</span><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Cobro duplicado, cortesía, error de captura" maxLength={200} autoFocus /></label>
          <div className="modal-feedback pos-difference"><span>Total a reembolsar</span><strong>{formatMoney(sale.total_cents)}</strong></div>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Reembolsando…" : "Reembolsar servicio"}</button></div>
        </form>
      </section>
    </div>
  );
}

function CreditLimitLookupModal({ onSelect, onClose, onUnauthorized }: { onSelect: (summary: MemberAccountSummary) => void; onClose: () => void; onUnauthorized: () => void }) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<BackendMember[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    const handle = window.setTimeout(() => setQuery(search.trim()), 250);
    return () => window.clearTimeout(handle);
  }, [search]);

  useEffect(() => {
    if (query.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`/api/admin/members?search=${encodeURIComponent(query)}&page_size=8`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("No se pudo buscar socios.");
        const directory = await response.json() as MemberDirectory;
        if (active) setResults(directory.items);
      } catch (loadError) {
        if (active) setError(loadError instanceof Error ? loadError.message : "Error al buscar socios.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const openAccount = async (member: BackendMember) => {
    setBusyId(member.id);
    setError("");
    try {
      const response = await fetch(`/api/admin/member-accounts/${member.id}`, { cache: "no-store" });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) throw new Error("No se pudo abrir la cuenta del socio.");
      const statement = await response.json() as MemberAccountStatement;
      onSelect(statement.summary);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Error al abrir la cuenta.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="credit-lookup-title">
        <div className="modal-header"><span className="modal-icon"><Wallet size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">CRÉDITO DEL SOCIO</p>
        <h2 id="credit-lookup-title">Asignar límite de crédito</h2>
        <p className="modal-subtitle">Busca al socio, revisa su saldo y define su límite. Un límite vacío significa «sin tope».</p>
        <label className="table-search"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Nombre, correo o teléfono" autoFocus /></label>
        {loading && <p className="panel-hint">Buscando socios…</p>}
        {error && <div className="login-error" role="alert">{error}</div>}
        {query.length >= 2 && !loading && !error && results.length === 0 && <p className="panel-hint">Sin coincidencias.</p>}
        {results.length > 0 && (
          <ul className="manual-results pos-member-results">
            {results.map((member) => (
              <li key={member.id}>
                <button type="button" disabled={busyId === member.id} onClick={() => void openAccount(member)}>
                  <span className="person-cell"><span className="person-avatar blue">{`${member.first_name[0] ?? ""}${member.last_name[0] ?? ""}`.toUpperCase()}</span><span><strong>{member.first_name} {member.last_name}</strong><small>{member.email ?? member.phone ?? "Socio"}</small></span></span>
                  <span className="table-hint">{busyId === member.id ? "Abriendo…" : "Ver cuenta"}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function MemberAccountModal({ member, canManage, canManageCredit, cashSessionOpen, onClose, onSaved }: { member: MemberAccountSummary; canManage: boolean; canManageCredit: boolean; cashSessionOpen: boolean; onClose: () => void; onSaved: (message: string) => void }) {
  const [statement, setStatement] = useState<MemberAccountStatement | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<"cash" | "card" | "transfer">("cash");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [paymentError, setPaymentError] = useState("");
  const [limitDraft, setLimitDraft] = useState("");
  const [limitBusy, setLimitBusy] = useState(false);
  const [limitError, setLimitError] = useState("");
  const [deliveryBusy, setDeliveryBusy] = useState<"pdf" | "csv" | null>(null);
  const [deliveryError, setDeliveryError] = useState("");
  const [deliveries, setDeliveries] = useState<StatementDelivery[]>([]);
  const [deliveriesLoading, setDeliveriesLoading] = useState(true);
  const [deliveriesError, setDeliveriesError] = useState("");
  const [retryingId, setRetryingId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`/api/admin/member-accounts/${member.member_id}`, { cache: "no-store" });
        if (!response.ok) throw new Error("No se pudo consultar la cuenta del socio.");
        const data = await response.json() as MemberAccountStatement;
        if (active) {
          setStatement(data);
          setLimitDraft(data.summary.credit_limit_cents === null ? "" : (data.summary.credit_limit_cents / 100).toFixed(2));
        }
      } catch (loadError) {
        if (active) setError(loadError instanceof Error ? loadError.message : "Error al cargar la cuenta.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [member.member_id, refresh]);

  useEffect(() => {
    let active = true;
    const loadDeliveries = async () => {
      setDeliveriesLoading(true);
      setDeliveriesError("");
      try {
        const response = await fetch(
          `/api/admin/member-accounts/${member.member_id}/statement/deliveries?page=1&page_size=10`,
          { cache: "no-store" },
        );
        if (!response.ok) throw new Error("No se pudo consultar el historial de envíos.");
        const data = await response.json() as StatementDeliveryPage;
        if (active) setDeliveries(data.items);
      } catch (loadError) {
        if (active) setDeliveriesError(loadError instanceof Error ? loadError.message : "Error al cargar el historial de envíos.");
      } finally {
        if (active) setDeliveriesLoading(false);
      }
    };
    void loadDeliveries();
    return () => { active = false; };
  }, [member.member_id, refresh]);

  const balance = statement?.summary.balance_cents ?? member.balance_cents;
  // ``null`` means "no limit", so it must not fall back to the older summary.
  const creditLimit = statement ? statement.summary.credit_limit_cents : member.credit_limit_cents;
  const creditAvailable = statement
    ? statement.summary.credit_available_cents
    : member.credit_available_cents;
  const overLimit = statement?.summary.over_limit ?? member.over_limit;
  const aging = statement?.summary.aging ?? member.aging;
  const statementEmail = statement?.summary.email ?? member.email;

  const saveLimit = async (cents: number | null) => {
    setLimitBusy(true);
    setLimitError("");
    try {
      const response = await fetch(`/api/admin/member-accounts/${member.member_id}/credit-limit`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credit_limit_cents: cents }),
      });
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) {
        setLimitError(payload.detail || "No se pudo actualizar el límite de crédito.");
        return;
      }
      setRefresh((value) => value + 1);
      onSaved(cents === null ? "Límite de crédito retirado." : `Límite de crédito actualizado a ${formatMoney(cents)}.`);
    } catch {
      setLimitError("No se pudo conectar con el backend.");
    } finally {
      setLimitBusy(false);
    }
  };

  const submitLimit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (limitDraft.trim() === "") {
      void saveLimit(null);
      return;
    }
    const cents = parseMoneyToCents(limitDraft);
    if (cents === null) {
      setLimitError("Indica un límite válido.");
      return;
    }
    void saveLimit(cents);
  };

  const sendStatement = async (documentFormat: "pdf" | "csv") => {
    setDeliveryBusy(documentFormat);
    setDeliveryError("");
    try {
      const response = await fetch(`/api/admin/member-accounts/${member.member_id}/statement/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ format: documentFormat }),
      });
      const payload = await response.json().catch(() => ({})) as {
        detail?: string;
        status?: string;
        recipient?: string;
      };
      if (!response.ok) {
        setDeliveryError(payload.detail || "No se pudo enviar el estado de cuenta.");
        return;
      }
      const recipient = payload.recipient ?? "el socio";
      onSaved(payload.status === "simulated"
        ? `Envío simulado a ${recipient} (modo vista previa).`
        : `Estado de cuenta enviado a ${recipient}.`);
      setRefresh((value) => value + 1);
    } catch {
      setDeliveryError("No se pudo conectar con el backend.");
    } finally {
      setDeliveryBusy(null);
    }
  };

  const retryDelivery = async (delivery: StatementDelivery) => {
    if (retryingId !== null) return;
    setRetryingId(delivery.id);
    setDeliveryError("");
    try {
      const response = await fetch(
        `/api/admin/member-accounts/${member.member_id}/statement/deliveries/${delivery.id}/retry`,
        { method: "POST" },
      );
      const payload = await response.json().catch(() => ({})) as {
        detail?: string;
        status?: string;
        recipient?: string;
      };
      if (!response.ok) {
        setDeliveryError(payload.detail || "No se pudo reintentar el envío.");
        return;
      }
      const recipient = payload.recipient ?? delivery.recipient;
      onSaved(payload.status === "simulated"
        ? `Reintento simulado a ${recipient} (modo vista previa).`
        : `Estado de cuenta reenviado a ${recipient}.`);
      setRefresh((value) => value + 1);
    } catch {
      setDeliveryError("No se pudo conectar con el backend.");
    } finally {
      setRetryingId(null);
    }
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cents = parseMoneyToCents(amount);
    if (cents === null || cents <= 0) {
      setPaymentError("Ingresa un monto mayor a cero.");
      return;
    }
    if (cents > balance) {
      setPaymentError("El pago supera el saldo pendiente del socio.");
      return;
    }
    setBusy(true);
    setPaymentError("");
    try {
      const response = await fetch(`/api/admin/member-accounts/${member.member_id}/payments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount_cents: cents, method, note: note.trim() || null }),
      });
      const payload = await response.json().catch(() => ({})) as { detail?: string; balance_cents?: number };
      if (!response.ok) {
        setPaymentError(payload.detail || "No se pudo registrar el pago.");
        return;
      }
      setAmount("");
      setNote("");
      setRefresh((value) => value + 1);
      onSaved(`Pago registrado. Saldo del socio: ${formatMoney(payload.balance_cents ?? 0)}.`);
    } catch {
      setPaymentError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="member-account-title">
        <div className="modal-header"><span className="modal-icon"><Wallet size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">CUENTA DEL SOCIO</p>
        <h2 id="member-account-title">{member.member_name}</h2>
        <p className="modal-subtitle">{member.email ?? member.phone ?? "Socio"} · Saldo {formatMoney(balance)}{statement ? ` · Corte ${formatDateOnly(statement.as_of)}` : ""}</p>
        <div className="pos-statement-actions">
          <a className="button button-secondary" href={`/api/admin/member-accounts/${member.member_id}/statement?format=pdf`} download><Download size={16} />Descargar PDF</a>
          <a className="button button-secondary" href={`/api/admin/member-accounts/${member.member_id}/statement?format=csv`} download><Download size={16} />Descargar CSV</a>
          {canManage && (
            <>
              <button type="button" className="button button-primary" disabled={deliveryBusy !== null || retryingId !== null || !statementEmail} title={statementEmail ? undefined : "El socio no tiene correo registrado"} onClick={() => void sendStatement("pdf")}><Mail size={16} />{deliveryBusy === "pdf" ? "Enviando…" : "Enviar PDF"}</button>
              <button type="button" className="button button-secondary" disabled={deliveryBusy !== null || retryingId !== null || !statementEmail} title={statementEmail ? undefined : "El socio no tiene correo registrado"} onClick={() => void sendStatement("csv")}><Mail size={16} />{deliveryBusy === "csv" ? "Enviando…" : "Enviar CSV"}</button>
            </>
          )}
        </div>
        {canManage && statement && !statementEmail && <p className="panel-hint">Agrega un correo al socio para enviarle el estado de cuenta.</p>}
        {deliveryError && <div className="login-error" role="alert">{deliveryError}</div>}
        {loading && !statement ? <p className="panel-hint">Consultando movimientos…</p>
          : error ? <div className="login-error" role="alert">{error}</div>
          : statement && (
            <>
              <div className="pos-cash-grid">
                <div className="summary-stat"><span>CARGOS</span><strong>{formatMoney(statement.summary.charges_cents)}</strong><small>{statement.summary.charges_count} ventas a cuenta</small></div>
                <div className="summary-stat"><span>ABONOS</span><strong>{formatMoney(statement.summary.payments_cents)}</strong><small>{statement.summary.payments_count} pagos</small></div>
                <div className="summary-stat"><span>DEVOLUCIONES</span><strong>{formatMoney(statement.summary.credits_cents)}</strong><small>abonadas a la cuenta</small></div>
                <div className="summary-stat"><span>SALDO</span><strong className={statement.summary.balance_cents < 0 ? "stat-orange" : ""}>{formatMoney(statement.summary.balance_cents)}</strong><small>{statement.summary.balance_cents < 0 ? "a favor" : "por cobrar"}</small></div>
              </div>
              <div className="pos-cash-grid pos-credit-grid">
                <div className="summary-stat"><span>LÍMITE DE CRÉDITO</span><strong className={overLimit ? "stat-orange" : ""}>{creditLimit === null ? "Sin límite" : formatMoney(creditLimit)}</strong><small>{creditLimit === null ? "sin tope configurado" : overLimit ? "excedido" : "tope vigente"}</small></div>
                <div className="summary-stat"><span>CRÉDITO DISPONIBLE</span><strong className={overLimit ? "stat-orange" : ""}>{creditLimit === null ? "—" : formatMoney(Math.max(creditAvailable ?? 0, 0))}</strong><small>{creditLimit === null ? "no aplica" : overLimit ? `excedido por ${formatMoney(balance - creditLimit)}` : "antes de la próxima venta"}</small></div>
              </div>
              <p className="section-kicker pos-aging-title">ANTIGÜEDAD DEL SALDO</p>
              <div className="pos-aging-grid" role="group" aria-label="Antigüedad del saldo">
                <div className="summary-stat"><span>0–30 DÍAS</span><strong>{formatMoney(aging.current_cents)}</strong><small>corriente</small></div>
                <div className="summary-stat"><span>31–60 DÍAS</span><strong>{formatMoney(aging.days_31_60_cents)}</strong><small>por vencer</small></div>
                <div className="summary-stat"><span>61–90 DÍAS</span><strong>{formatMoney(aging.days_61_90_cents)}</strong><small>atrasado</small></div>
                <div className="summary-stat"><span>+90 DÍAS</span><strong className="stat-orange">{formatMoney(aging.over_90_cents)}</strong><small>antigüedad crítica</small></div>
              </div>
              {overLimit && <p className="panel-hint">El saldo supera el límite: no se aceptarán nuevas ventas a cuenta hasta que se cobre o se amplíe el límite.</p>}
              {canManageCredit && (
                <form onSubmit={submitLimit} className="pos-credit-form">
                  <div className="form-row">
                    <label className="form-field"><span>Límite de crédito (vacío = sin límite)</span><input value={limitDraft} onChange={(event) => setLimitDraft(event.target.value)} placeholder="Sin límite" inputMode="decimal" /></label>
                    <div className="pos-credit-actions">
                      <button type="button" className="button button-secondary" disabled={limitBusy || creditLimit === null} onClick={() => { setLimitDraft(""); void saveLimit(null); }}>Sin límite</button>
                      <button type="submit" className="button button-primary" disabled={limitBusy}>{limitBusy ? "Guardando…" : "Guardar límite"}</button>
                    </div>
                  </div>
                  {limitError && <div className="login-error" role="alert">{limitError}</div>}
                </form>
              )}
              <div className="table-scroll">
                <table className="data-table"><thead><tr><th>FECHA</th><th>MOVIMIENTO</th><th>REFERENCIA</th><th>FORMA</th><th>IMPORTE</th><th>SALDO</th></tr></thead><tbody>
                  {statement.entries.length === 0 ? <tr><td colSpan={6} className="empty-row">Sin movimientos.</td></tr>
                    : statement.entries.map((entry, index) => (
                      <tr key={`${entry.reference}-${entry.kind}-${index}`}>
                        <td className="time-cell">{formatSaleTime(entry.occurred_at)}</td>
                        <td>{entry.description}</td>
                        <td className="time-cell">{entry.reference}</td>
                        <td>{entry.method ? paymentMethodLabels[entry.method] ?? entry.method : "—"}</td>
                        <td className="time-cell">{entry.amount_cents > 0 ? "+" : ""}{formatMoney(entry.amount_cents)}</td>
                        <td className="time-cell">{formatMoney(entry.balance_cents)}</td>
                      </tr>
                    ))}
                </tbody></table>
              </div>
              {canManage && statement.summary.balance_cents > 0 && (
                cashSessionOpen ? (
                  <form onSubmit={submit} className="pos-account-payment">
                    <div className="form-row">
                      <label className="form-field"><span>Monto</span><input value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="0.00" inputMode="decimal" /></label>
                      <label className="form-field"><span>Forma de pago</span><select value={method} onChange={(event) => setMethod(event.target.value as "cash" | "card" | "transfer")}><option value="cash">Efectivo</option><option value="card">Tarjeta</option><option value="transfer">Transferencia</option></select></label>
                      <label className="form-field"><span>Nota (opcional)</span><input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Referencia del cobro" maxLength={200} /></label>
                    </div>
                    {paymentError && <div className="login-error" role="alert">{paymentError}</div>}
                    <div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setAmount((balance / 100).toFixed(2))}>Usar saldo completo</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Registrando…" : "Registrar pago"}</button></div>
                  </form>
                ) : <p className="panel-hint">Abre un turno de caja para registrar cobros contra esta cuenta.</p>
              )}
              {canManage && statement.summary.balance_cents < 0 && <p className="panel-hint">El socio tiene saldo a favor por devoluciones; se aplicará en su próxima venta a cuenta.</p>}
              <div className="pos-statement-history">
                <div className="pos-statement-history-head">
                  <p className="section-kicker">HISTORIAL DE ENVÍOS</p>
                  <small>Últimos 10 intentos</small>
                </div>
                {deliveriesLoading ? <p className="panel-hint">Consultando envíos…</p>
                  : deliveriesError ? <div className="login-error" role="alert">{deliveriesError}</div>
                    : deliveries.length === 0 ? <p className="panel-hint">Aún no se ha enviado el estado de cuenta.</p>
                      : (
                        <div className="pos-statement-delivery-list">
                          {deliveries.map((delivery) => {
                            const retryable = delivery.status === "failed" || delivery.status === "simulated";
                            return (
                              <div className="pos-statement-delivery" key={delivery.id}>
                                <div className="pos-statement-delivery-main">
                                  <span className={`status-badge ${statementDeliveryStatusBadges[delivery.status] ?? "status-neutral"}`}><i />{statementDeliveryStatusLabels[delivery.status] ?? delivery.status}</span>
                                  <strong>{delivery.recipient}</strong>
                                  <small>{statementPurposeLabels[delivery.purpose] ?? delivery.purpose} · {delivery.format.toUpperCase()} · {formatSaleTime(delivery.created_at)} · corte {formatDateOnly(delivery.as_of)}</small>
                                </div>
                                <div className="pos-statement-delivery-side">
                                  <small>{delivery.actor_email ? `Por ${delivery.actor_email}` : "Sin usuario registrado"}</small>
                                  {delivery.retry_of_id && <small className="pos-delivery-retry-note">Reintento de un envío anterior</small>}
                                  {delivery.error && <small className="pos-delivery-error">{delivery.error}</small>}
                                  {canManage && retryable && (
                                    <button
                                      type="button"
                                      className="text-button pos-delivery-retry"
                                      disabled={retryingId !== null || deliveryBusy !== null}
                                      onClick={() => void retryDelivery(delivery)}
                                    >
                                      <RotateCcw size={13} />{retryingId === delivery.id ? "Reintentando…" : "Reintentar"}
                                    </button>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
              </div>
            </>
          )}
      </section>
    </div>
  );
}

function CollectionReminderModal({ onClose, onSaved, onUnauthorized }: { onClose: () => void; onSaved: (message: string) => void; onUnauthorized: () => void }) {
  const [directory, setDirectory] = useState<MemberAccountDirectory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [format, setFormat] = useState<"pdf" | "csv">("pdf");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [batch, setBatch] = useState<StatementReminderBatch | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await fetch("/api/admin/member-accounts?page=1&page_size=100", { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("No se pudieron consultar las cuentas por cobrar.");
        const data = await response.json() as MemberAccountDirectory;
        if (!active) return;
        setDirectory(data);
        const preselect = data.items
          .filter((item) => item.balance_cents > 0 && item.aging.days_31_60_cents + item.aging.days_61_90_cents + item.aging.over_90_cents > 0 && Boolean(item.email?.trim()))
          .map((item) => item.member_id);
        setSelected(new Set(preselect));
      } catch (loadError) {
        if (active) setError(loadError instanceof Error ? loadError.message : "Error al cargar las cuentas.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const candidates = useMemo(() => (directory?.items ?? []).filter((item) => {
    const overdue = item.aging.days_31_60_cents + item.aging.days_61_90_cents + item.aging.over_90_cents;
    return item.balance_cents > 0 && overdue > 0;
  }), [directory]);

  const withEmail = candidates.filter((item) => Boolean(item.email?.trim()));
  const overdueOf = (item: MemberAccountSummary) => item.aging.days_31_60_cents + item.aging.days_61_90_cents + item.aging.over_90_cents;

  const toggle = (memberId: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(memberId)) next.delete(memberId);
      else next.add(memberId);
      return next;
    });
    setConfirming(false);
  };

  const toggleAll = () => {
    setSelected((current) => current.size === withEmail.length
      ? new Set()
      : new Set(withEmail.map((item) => item.member_id)));
    setConfirming(false);
  };

  const send = async () => {
    if (selected.size === 0 || busy) return;
    if (!confirming) {
      setConfirming(true);
      setError("");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/member-accounts/reminders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ member_ids: Array.from(selected), format }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as StatementReminderBatch & { detail?: string };
      if (!response.ok) {
        setError(payload.detail || "No se pudieron enviar los recordatorios.");
        return;
      }
      setBatch(payload);
      setConfirming(false);
      const parts = [
        payload.sent > 0 ? `${payload.sent} enviados` : "",
        payload.simulated > 0 ? `${payload.simulated} simulados` : "",
        payload.skipped > 0 ? `${payload.skipped} omitidos` : "",
        payload.failed > 0 ? `${payload.failed} fallidos` : "",
      ].filter(Boolean);
      onSaved(`Recordatorios procesados: ${parts.join(", ") || "sin cambios"}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const allSelected = withEmail.length > 0 && selected.size === withEmail.length;

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="collection-reminder-title">
        <div className="modal-header"><span className="modal-icon"><Bell size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">COBRANZA</p>
        <h2 id="collection-reminder-title">Recordatorios de saldo vencido</h2>
        <p className="modal-subtitle">Se envía el estado de cuenta a los socios con cargos de más de 30 días. Un socio se omite si no tiene correo, ya pagó o recibió un recordatorio en los últimos 7 días.</p>
        {loading ? <p className="panel-hint">Consultando cuentas por cobrar…</p>
          : error && candidates.length === 0 ? <div className="login-error" role="alert">{error}</div>
          : candidates.length === 0 ? <p className="panel-hint">No hay socios con saldo de más de 30 días.</p>
          : (
            <>
              <div className="pos-reminder-toolbar">
                <span className="table-hint">{candidates.length} {candidates.length === 1 ? "socio con saldo vencido" : "socios con saldo vencido"} · {withEmail.length} con correo</span>
                <div className="pos-reminder-tools">
                  <label className="form-field pos-reminder-format"><span>Adjunto</span><select value={format} onChange={(event) => { setFormat(event.target.value as "pdf" | "csv"); setConfirming(false); }}><option value="pdf">PDF</option><option value="csv">CSV</option></select></label>
                  <button type="button" className="button button-secondary" disabled={withEmail.length === 0 || busy} onClick={toggleAll}>{allSelected ? "Quitar selección" : "Seleccionar todos"}</button>
                </div>
              </div>
              <div className="pos-reminder-list">
                {candidates.map((item) => {
                  const disabled = !item.email?.trim() || busy;
                  const initials = item.member_name.split(/\s+/).slice(0, 2).map((part) => part[0] ?? "").join("").toUpperCase();
                  return (
                    <label className={`pos-reminder-row${disabled ? " pos-reminder-row-disabled" : ""}`} key={item.member_id}>
                      <input type="checkbox" checked={selected.has(item.member_id)} disabled={disabled} onChange={() => toggle(item.member_id)} />
                      <span className="person-avatar blue">{initials}</span>
                      <span className="pos-reminder-person"><strong>{item.member_name}</strong><small>{item.email?.trim() || "Sin correo registrado"}</small></span>
                      <span className="pos-reminder-amount"><small>Saldo</small><strong>{formatMoney(item.balance_cents)}</strong></span>
                      <span className="pos-reminder-amount"><small>+30 días</small><strong className="stat-orange">{formatMoney(overdueOf(item))}</strong></span>
                    </label>
                  );
                })}
              </div>
              {directory && directory.total > directory.items.length && <p className="panel-hint">Se muestran las primeras {directory.items.length} cuentas de {directory.total}. Filtra o cobra las más antiguas para ver el resto.</p>}
              {error && <div className="login-error" role="alert">{error}</div>}
              {batch && (
                <div className="pos-reminder-results" aria-live="polite">
                  <div className="pos-statement-history-head"><p className="section-kicker">RESULTADO DEL LOTE</p><small>{batch.requested} {batch.requested === 1 ? "socio" : "socios"} procesados</small></div>
                  <div className="pos-reminder-summary">
                    <span><strong>{batch.sent}</strong> enviados</span>
                    <span><strong>{batch.simulated}</strong> simulados</span>
                    <span><strong>{batch.skipped}</strong> omitidos</span>
                    <span><strong>{batch.failed}</strong> fallidos</span>
                  </div>
                  <div className="pos-statement-delivery-list">
                    {batch.results.map((result) => (
                      <div className="pos-statement-delivery" key={result.member_id}>
                        <div className="pos-statement-delivery-main">
                          <span className={`status-badge ${reminderResultBadges[result.status] ?? "status-neutral"}`}><i />{reminderResultLabels[result.status] ?? result.status}</span>
                          <strong>{result.member_name ?? result.member_id}</strong>
                          <small>{result.reason ?? `Saldo ${formatMoney(result.balance_cents)} · vencido ${formatMoney(result.overdue_cents)}`}</small>
                        </div>
                        <div className="pos-statement-delivery-side">
                          <small>{result.delivery ? `A ${result.delivery.recipient}` : "Sin envío registrado"}</small>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div className="modal-actions pos-reminder-actions">
                <button type="button" className="button button-secondary" onClick={onClose}>Cerrar</button>
                <button type="button" className={confirming ? "button button-primary" : "button button-secondary"} disabled={selected.size === 0 || busy} onClick={() => void send()}><Mail size={16} />{busy ? "Enviando…" : confirming ? `Confirmar envío a ${selected.size}` : `Enviar recordatorios (${selected.size})`}</button>
              </div>
              {confirming && <p className="panel-hint">Se enviará el estado de cuenta a {selected.size} {selected.size === 1 ? "socio" : "socios"}. Pulsa de nuevo para confirmar.</p>}
            </>
          )}
      </section>
    </div>
  );
}

function ClassesView({ permissions, onUnauthorized, onToast }: { permissions: string[]; onUnauthorized: () => void; onToast: (message: string) => void }) {
  const canManage = permissions.includes("classes.manage");

  const [tab, setTab] = useState<"agenda" | "catalogo">("agenda");
  const [directory, setDirectory] = useState<ClassSessionDirectory | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | ClassSessionState>("");
  const [day, setDay] = useState("");
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);

  const [types, setTypes] = useState<BackendClassType[]>([]);
  const [rooms, setRooms] = useState<BackendClassRoom[]>([]);
  const [instructors, setInstructors] = useState<BackendInstructor[]>([]);
  const [catalogLoaded, setCatalogLoaded] = useState(false);

  const [sessionModal, setSessionModal] = useState<{ session: BackendClassSession | null } | null>(null);
  const [roster, setRoster] = useState<BackendClassSession | null>(null);
  const [typeModalOpen, setTypeModalOpen] = useState(false);
  const [roomModalOpen, setRoomModalOpen] = useState(false);

  const reload = () => setRefresh((value) => value + 1);

  useEffect(() => {
    const handle = window.setTimeout(() => { setQuery(search.trim()); setPage(1); }, 250);
    return () => window.clearTimeout(handle);
  }, [search]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setCatalogLoaded(false);
      try {
        const [typesResponse, roomsResponse, instructorsResponse] = await Promise.all([
          fetch("/api/admin/classes/types", { cache: "no-store" }),
          fetch("/api/admin/classes/rooms", { cache: "no-store" }),
          fetch("/api/admin/classes/instructors", { cache: "no-store" }),
        ]);
        if ([typesResponse, roomsResponse, instructorsResponse].some((response) => response.status === 401)) {
          onUnauthorized();
          return;
        }
        if (!active) return;
        if (typesResponse.ok) setTypes(await typesResponse.json() as BackendClassType[]);
        if (roomsResponse.ok) setRooms(await roomsResponse.json() as BackendClassRoom[]);
        if (instructorsResponse.ok) setInstructors(await instructorsResponse.json() as BackendInstructor[]);
      } catch {
        // The catalogue only feeds the forms; a failure leaves the selects empty.
      } finally {
        if (active) setCatalogLoaded(true);
      }
    };
    void load();
    return () => { active = false; };
  }, [refresh, onUnauthorized]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      const params = new URLSearchParams({ page: String(page), page_size: String(CLASSES_PAGE_SIZE) });
      if (query) params.set("search", query);
      if (statusFilter) params.set("status", statusFilter);
      if (day) {
        const start = new Date(`${day}T00:00:00`);
        const end = new Date(start.getTime() + 24 * 60 * 60 * 1000);
        params.set("date_from", start.toISOString());
        params.set("date_to", end.toISOString());
      }
      try {
        const response = await fetch(`/api/admin/classes/sessions?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        const data = await response.json() as ClassSessionDirectory;
        if (active) setDirectory(data);
      } catch {
        if (active) setError("No se pudo cargar la agenda de clases.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [page, query, statusFilter, day, refresh, onUnauthorized]);

  const summary = directory?.summary ?? { total: 0, scheduled: 0, cancelled: 0, upcoming: 0, reserved_total: 0, waitlist_total: 0 };
  const items = directory?.items ?? [];
  const total = directory?.total ?? 0;
  const pages = directory?.pages ?? 0;
  const currentPage = directory?.page ?? 1;
  const hasFilters = Boolean(query) || Boolean(statusFilter) || Boolean(day);

  const cancelSession = async (session: BackendClassSession) => {
    try {
      const response = await fetch(`/api/admin/classes/sessions/${session.id}/cancel`, { method: "POST" });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo cancelar la clase."); return; }
      reload();
      onToast(`Clase cancelada: ${session.title}.`);
    } catch {
      onToast("No se pudo conectar con el backend.");
    }
  };

  const tabButton = (value: "agenda" | "catalogo", label: string) => (
    <button type="button" className={tab === value ? "staff-tab-active" : ""} onClick={() => setTab(value)}>{label}</button>
  );

  return (
    <>
      <section className="access-summary-band pos-cash-band">
        <div className="access-summary-main">
          <span className="summary-icon"><CalendarDays size={18} /></span>
          <div>
            <span>AGENDA DE CLASES</span>
            <strong>{loading ? "Consultando…" : `${summary.scheduled} clases programadas`}</strong>
          </div>
        </div>
        <div className="summary-divider" />
        <div className="summary-stat"><span>PRÓXIMAS</span><strong>{summary.upcoming}</strong></div>
        <div className="summary-stat"><span>INSCRITOS</span><strong>{summary.reserved_total}</strong></div>
        <div className="summary-stat"><span>EN ESPERA</span><strong>{summary.waitlist_total}</strong></div>
        {canManage && <button className="button button-primary" onClick={() => setSessionModal({ session: null })}><Plus size={16} />Nueva clase</button>}
      </section>

      <div className="staff-tabs pos-tabs">
        {tabButton("agenda", "Agenda")}
        {tabButton("catalogo", "Catálogo")}
        <span className="staff-tabs-note"><ShieldCheck size={14} />Las clases premium se cobran al marcar la asistencia</span>
      </div>

      {tab === "agenda" && (
        <section className="panel full-panel">
          <div className="panel-header access-list-heading">
            <div><p className="section-kicker">PROGRAMACIÓN</p><h2>Calendario de clases</h2></div>
            {canManage && <button className="button button-primary" onClick={() => setSessionModal({ session: null })}><Plus size={17} />Nueva clase</button>}
          </div>
          <div className="table-toolbar">
            <label className="table-search"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar por clase o tipo" /></label>
            <label className="table-select"><span>Estado</span><select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as "" | ClassSessionState); setPage(1); }}><option value="">Todas</option><option value="scheduled">Programadas</option><option value="cancelled">Canceladas</option></select></label>
            <label className="table-select"><span>Día</span><input type="date" value={day} onChange={(event) => { setDay(event.target.value); setPage(1); }} /></label>
            {hasFilters ? <button className="button button-secondary" onClick={() => { setSearch(""); setStatusFilter(""); setDay(""); setPage(1); }}>Limpiar filtros</button> : <span className="table-hint">Consulta cupos y listas de espera</span>}
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>CLASE</th><th>HORARIO</th><th>INSTRUCTOR</th><th>SALÓN</th><th>CUPO</th><th>ESPERA</th><th>ESTADO</th><th /></tr></thead>
              <tbody>
                {loading ? <tr><td colSpan={8} className="empty-row">Cargando clases…</td></tr>
                  : error ? <tr><td colSpan={8} className="empty-row">{error}</td></tr>
                  : items.length === 0 ? <tr><td colSpan={8} className="empty-row">{hasFilters ? "No hay clases que coincidan con el filtro." : "Aún no hay clases programadas."}</td></tr>
                  : items.map((session) => {
                    const fill = session.capacity > 0 ? Math.min(Math.round((session.reserved_count / session.capacity) * 100), 100) : 0;
                    return (
                      <tr key={session.id}>
                        <td><div className="person-cell"><span className="pos-row-icon"><CalendarDays size={15} /></span><span><strong>{session.title}</strong><small>{session.class_type_name}{session.access_type === "premium" ? " · Premium" : ""}</small></span></div></td>
                        <td className="time-cell">{formatClassDay(session.starts_at)}<small className="pos-min">{formatClassClock(session.starts_at)}–{formatClassClock(session.ends_at)}</small></td>
                        <td>{session.instructor_name ?? "Por asignar"}</td>
                        <td>{session.room_name ?? "—"}</td>
                        <td><div className="class-capacity"><span>{session.reserved_count}/{session.capacity}</span><span className="class-capacity-track"><span style={{ width: `${fill}%` }} /></span></div></td>
                        <td>{session.waitlist_count}</td>
                        <td><span className={`status-badge ${classSessionBadge(session.status)}`}><i />{classStatusLabels[session.status]}</span></td>
                        <td><div className="pos-row-actions">
                          <button type="button" className="text-button" onClick={() => setRoster(session)}>Lista</button>
                          {canManage && session.status === "scheduled" && <>
                            <button type="button" className="text-button" onClick={() => setSessionModal({ session })}>Editar</button>
                            <button type="button" className="text-button" onClick={() => cancelSession(session)}>Cancelar</button>
                          </>}
                        </div></td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
          <div className="table-bottom">
            <span>{total} clases programadas</span>
            {pages > 1 && (
              <span className="member-pagination">
                <span>Página {currentPage} de {pages}</span>
                <button type="button" aria-label="Página anterior" disabled={currentPage <= 1} onClick={() => setPage((value) => Math.max(value - 1, 1))}>‹</button>
                <button type="button" aria-label="Página siguiente" disabled={currentPage >= pages} onClick={() => setPage((value) => value + 1)}>›</button>
              </span>
            )}
          </div>
        </section>
      )}

      {tab === "catalogo" && (
        <div className="dashboard-grid">
          <section className="panel">
            <div className="panel-header"><div><p className="section-kicker">CATÁLOGO</p><h2>Tipos de clase</h2></div>{canManage && <button className="button button-primary button-small" onClick={() => setTypeModalOpen(true)}><Plus size={15} />Agregar</button>}</div>
            {types.length === 0 ? <p className="panel-hint">{catalogLoaded ? "Aún no hay tipos de clase." : "Cargando…"}</p> : (
              <ul className="class-catalog-list">
                {types.map((type) => <li key={type.id}><span className="class-type-dot" /><span><strong>{type.name}</strong><small>{type.description ?? "Sin descripción"}</small></span></li>)}
              </ul>
            )}
          </section>
          <section className="panel">
            <div className="panel-header"><div><p className="section-kicker">CATÁLOGO</p><h2>Salones</h2></div>{canManage && <button className="button button-primary button-small" onClick={() => setRoomModalOpen(true)}><Plus size={15} />Agregar</button>}</div>
            {rooms.length === 0 ? <p className="panel-hint">{catalogLoaded ? "Aún no hay salones." : "Cargando…"}</p> : (
              <ul className="class-catalog-list">
                {rooms.map((room) => <li key={room.id}><span className="class-type-dot" /><span><strong>{room.name}</strong><small>Capacidad {room.capacity}</small></span></li>)}
              </ul>
            )}
          </section>
        </div>
      )}

      {canManage && sessionModal && (
        <ClassSessionModal
          session={sessionModal.session}
          types={types}
          rooms={rooms}
          instructors={instructors}
          onClose={() => setSessionModal(null)}
          onSaved={(message) => { setSessionModal(null); reload(); onToast(message); }}
          onUnauthorized={onUnauthorized}
        />
      )}
      {roster && (
        <ClassRosterModal
          session={roster}
          canManage={canManage}
          onClose={() => setRoster(null)}
          onChanged={reload}
          onToast={onToast}
          onUnauthorized={onUnauthorized}
        />
      )}
      {canManage && typeModalOpen && <ClassTypeModal onClose={() => setTypeModalOpen(false)} onSaved={(message) => { setTypeModalOpen(false); reload(); onToast(message); }} onUnauthorized={onUnauthorized} />}
      {canManage && roomModalOpen && <ClassRoomModal onClose={() => setRoomModalOpen(false)} onSaved={(message) => { setRoomModalOpen(false); reload(); onToast(message); }} onUnauthorized={onUnauthorized} />}

      <footer className="page-footer"><span>Centro Fit · Clases y reservaciones</span><span>DATOS DEL BACKEND · CLASES PREMIUM CON COBRO EN RECEPCIÓN</span></footer>
    </>
  );
}

function ClassSessionModal({
  session,
  types,
  rooms,
  instructors,
  onClose,
  onSaved,
  onUnauthorized,
}: {
  session: BackendClassSession | null;
  types: BackendClassType[];
  rooms: BackendClassRoom[];
  instructors: BackendInstructor[];
  onClose: () => void;
  onSaved: (message: string) => void;
  onUnauthorized: () => void;
}) {
  const editing = session !== null;
  const [title, setTitle] = useState(session?.title ?? "");
  const [typeId, setTypeId] = useState(session?.class_type_id ?? types[0]?.id ?? "");
  const [roomId, setRoomId] = useState(session?.room_id ?? "");
  const [instructorId, setInstructorId] = useState(session?.instructor_id ?? "");
  const [startsAt, setStartsAt] = useState(session ? toDateTimeLocalValue(session.starts_at) : defaultSessionStart());
  const [endsAt, setEndsAt] = useState(
    session
      ? toDateTimeLocalValue(session.ends_at)
      : toDateTimeLocalValue(new Date(new Date(defaultSessionStart()).getTime() + 60 * 60 * 1000).toISOString()),
  );
  const [capacity, setCapacity] = useState(session ? String(session.capacity) : "15");
  const [accessType, setAccessType] = useState<"included" | "premium">(session?.access_type ?? "included");
  const [extraPrice, setExtraPrice] = useState(session && session.extra_price_cents > 0 ? (session.extra_price_cents / 100).toFixed(2) : "");
  const [waitlist, setWaitlist] = useState(session?.waitlist_enabled ?? true);
  const [cancelWindow, setCancelWindow] = useState(session ? String(session.cancel_window_hours) : "4");
  const [notes, setNotes] = useState(session?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) { setError("El título de la clase es obligatorio."); return; }
    if (!typeId) { setError("Selecciona un tipo de clase."); return; }
    const capacityValue = Number.parseInt(capacity, 10);
    if (!Number.isFinite(capacityValue) || capacityValue <= 0) { setError("Indica una capacidad válida."); return; }
    const windowValue = Number.parseInt(cancelWindow, 10);
    if (!Number.isFinite(windowValue) || windowValue < 0) { setError("La ventana de cancelación no es válida."); return; }
    const start = new Date(startsAt);
    const end = new Date(endsAt);
    if (!(end.getTime() > start.getTime())) { setError("La hora de término debe ser posterior a la de inicio."); return; }
    const extraCents = accessType === "premium" ? parseMoneyToCents(extraPrice || "0") : 0;
    if (extraCents === null) { setError("El precio extra no es válido."); return; }

    const body = {
      title: trimmed,
      room_id: roomId || null,
      instructor_id: instructorId || null,
      starts_at: fromDateTimeLocalValue(startsAt),
      ends_at: fromDateTimeLocalValue(endsAt),
      capacity: capacityValue,
      access_type: accessType,
      extra_price_cents: extraCents,
      waitlist_enabled: waitlist,
      cancel_window_hours: windowValue,
      notes: notes.trim() || null,
    };

    setBusy(true);
    setError("");
    try {
      const response = editing && session
        ? await fetch(`/api/admin/classes/sessions/${session.id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          })
        : await fetch("/api/admin/classes/sessions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...body, class_type_id: typeId }),
          });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) {
        setError(payload.detail || "No se pudo guardar la clase.");
        return;
      }
      onSaved(editing ? "Clase actualizada." : `Clase creada: ${trimmed}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="class-session-title">
        <div className="modal-header"><span className="modal-icon"><CalendarDays size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">{editing ? "EDITAR CLASE" : "PROGRAMAR CLASE"}</p>
        <h2 id="class-session-title">{editing ? session?.title : "Nueva clase"}</h2>
        <p className="modal-subtitle">La capacidad se controla por reservas confirmadas; el cupo restante entra a la lista de espera.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Título</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Ej. Spinning 6am" maxLength={160} autoFocus /></label>
          <div className="form-row">
            <label className="form-field"><span>Tipo de clase</span><select value={typeId} onChange={(event) => setTypeId(event.target.value)} disabled={editing}><option value="">Selecciona…</option>{types.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}</select></label>
            <label className="form-field"><span>Salón</span><select value={roomId} onChange={(event) => setRoomId(event.target.value)}><option value="">Sin asignar</option>{rooms.map((room) => <option key={room.id} value={room.id}>{room.name} · {room.capacity}</option>)}</select></label>
          </div>
          <label className="form-field"><span>Instructor</span><select value={instructorId} onChange={(event) => setInstructorId(event.target.value)}><option value="">Por asignar</option>{instructors.map((instructor) => <option key={instructor.id} value={instructor.id}>{instructor.name} · {instructor.job_title}</option>)}</select></label>
          <div className="form-row">
            <label className="form-field"><span>Inicio</span><input type="datetime-local" value={startsAt} onChange={(event) => setStartsAt(event.target.value)} /></label>
            <label className="form-field"><span>Fin</span><input type="datetime-local" value={endsAt} onChange={(event) => setEndsAt(event.target.value)} /></label>
          </div>
          <div className="form-row">
            <label className="form-field"><span>Capacidad</span><input value={capacity} onChange={(event) => setCapacity(event.target.value)} inputMode="numeric" /></label>
            <label className="form-field"><span>Ventana de cancelación (horas)</span><input value={cancelWindow} onChange={(event) => setCancelWindow(event.target.value)} inputMode="numeric" /></label>
          </div>
          <div className="form-row">
            <label className="form-field"><span>Acceso</span><select value={accessType} onChange={(event) => setAccessType(event.target.value as "included" | "premium")}><option value="included">Incluida en la membresía</option><option value="premium">Premium (pago extra)</option></select></label>
            <label className="form-field"><span>Precio extra (opcional)</span><input value={extraPrice} onChange={(event) => setExtraPrice(event.target.value)} placeholder="0.00" inputMode="decimal" disabled={accessType !== "premium"} /></label>
          </div>
          {accessType === "premium" && <div className="modal-note"><ShieldCheck size={16} /><span>El precio extra se cobra al marcar al socio como «Asistió» en la lista de la clase, con la forma de pago que elija en recepción.</span></div>}
          <label className="form-field form-check"><span><input type="checkbox" checked={waitlist} onChange={(event) => setWaitlist(event.target.checked)} />Permitir lista de espera cuando el salón esté lleno</span></label>
          <label className="form-field"><span>Notas (opcional)</span><input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Material, indicaciones…" maxLength={500} /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : editing ? "Guardar cambios" : "Programar clase"}</button></div>
        </form>
      </section>
    </div>
  );
}

function ClassRosterModal({
  session,
  canManage,
  onClose,
  onChanged,
  onToast,
  onUnauthorized,
}: {
  session: BackendClassSession;
  canManage: boolean;
  onClose: () => void;
  onChanged: () => void;
  onToast: (message: string) => void;
  onUnauthorized: () => void;
}) {
  const [roster, setRoster] = useState<ClassRoster | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [memberQuery, setMemberQuery] = useState("");
  const [memberResults, setMemberResults] = useState<BackendMember[]>([]);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<"cash" | "card" | "transfer" | "account">("cash");

  const load = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/admin/classes/sessions/${session.id}/reservations`, { cache: "no-store" });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) throw new Error("failed");
      setRoster(await response.json() as ClassRoster);
      setError("");
    } catch {
      setError("No se pudo cargar la lista de la clase.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [session.id]);

  useEffect(() => {
    const term = memberQuery.trim();
    if (term.length < 2) { setMemberResults([]); return; }
    let active = true;
    const handle = window.setTimeout(async () => {
      setSearching(true);
      try {
        const response = await fetch(`/api/admin/members?search=${encodeURIComponent(term)}&page_size=6`, { cache: "no-store" });
        if (response.ok) {
          const directory = await response.json() as MemberDirectory;
          if (active) setMemberResults(directory.items);
        } else if (active) {
          setMemberResults([]);
        }
      } catch {
        if (active) setMemberResults([]);
      } finally {
        if (active) setSearching(false);
      }
    }, 250);
    return () => { active = false; window.clearTimeout(handle); };
  }, [memberQuery]);

  const reserve = async (member: BackendMember) => {
    setBusy(true);
    setMemberQuery("");
    setMemberResults([]);
    try {
      const response = await fetch(`/api/admin/classes/sessions/${session.id}/reservations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ member_id: member.id, origin: "reception" }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string; status?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo reservar el lugar."); return; }
      await load();
      onChanged();
      onToast(payload.status === "waitlist" ? `${member.first_name} quedó en lista de espera.` : `Reserva confirmada para ${member.first_name}.`);
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const cancelReservation = async (reservation: BackendReservation) => {
    setBusy(true);
    try {
      const response = await fetch(`/api/admin/classes/reservations/${reservation.id}/cancel`, { method: "POST" });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string; late_cancellation?: boolean; charge_status?: string | null; charge_cents?: number | null; charge_payment_method?: string | null };
      if (!response.ok) { onToast(payload.detail || "No se pudo cancelar la reserva."); return; }
      await load();
      onChanged();
      const refunded = payload.charge_status === "refunded" && payload.charge_cents
        ? ` Se reembolsaron ${formatMoney(payload.charge_cents)} (${paymentMethodLabels[payload.charge_payment_method ?? ""] ?? payload.charge_payment_method}).`
        : "";
      onToast(payload.late_cancellation ? `Reserva cancelada fuera de la ventana (penalización pendiente).${refunded}` : `Reserva cancelada.${refunded}`);
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const mark = async (reservation: BackendReservation, attended: boolean) => {
    setBusy(true);
    try {
      const response = await fetch(`/api/admin/classes/reservations/${reservation.id}/attendance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ attended, payment_method: attended && isPremium ? paymentMethod : null }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string; charge_status?: string | null; charge_cents?: number | null; charge_payment_method?: string | null; charge_folio?: string | null };
      if (!response.ok) { onToast(payload.detail || "No se pudo marcar la asistencia."); return; }
      await load();
      onChanged();
      if (attended) {
        const charged = payload.charge_status === "completed" && payload.charge_cents
          ? ` Cobro de ${formatMoney(payload.charge_cents)} (${paymentMethodLabels[payload.charge_payment_method ?? ""] ?? payload.charge_payment_method}) · folio ${payload.charge_folio}.`
          : "";
        onToast(`Asistencia registrada.${charged}`);
      } else {
        const refunded = payload.charge_status === "refunded" && payload.charge_cents
          ? ` Se reembolsaron ${formatMoney(payload.charge_cents)}.`
          : "";
        onToast(`Inasistencia registrada.${refunded}`);
      }
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const current = roster?.session ?? session;
  const reservations = roster?.reservations ?? [];
  const isPremium = current.access_type === "premium" && current.extra_price_cents > 0;

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="class-roster-title">
        <div className="modal-header"><span className="modal-icon"><Users size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">LISTA DE LA CLASE</p>
        <h2 id="class-roster-title">{current.title}</h2>
        <p className="modal-subtitle">{formatClassDay(current.starts_at)} · {formatClassClock(current.starts_at)}–{formatClassClock(current.ends_at)} · {current.reserved_count}/{current.capacity} confirmadas · {current.waitlist_count} en espera</p>

        {isPremium && (
          <div className="modal-note">
            <ShieldCheck size={16} />
            <span>Clase premium · {formatMoney(current.extra_price_cents)} por asistente. Al marcar «Asistió» se cobra en la forma de pago elegida; al cancelar se reembolsa.</span>
            <select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value as "cash" | "card" | "transfer" | "account")} disabled={busy}>
              <option value="cash">Efectivo</option>
              <option value="card">Tarjeta</option>
              <option value="transfer">Transferencia</option>
              <option value="account">Cuenta del socio</option>
            </select>
          </div>
        )}

        {canManage && current.status === "scheduled" && (
          <div className="class-roster-search">
            <label className="form-field"><span>Reservar para un socio</span><input value={memberQuery} onChange={(event) => setMemberQuery(event.target.value)} placeholder="Buscar por nombre o correo" autoComplete="off" /></label>
            {searching && <p className="manual-hint">Buscando socios…</p>}
            {memberResults.length > 0 && (
              <ul className="manual-results">
                {memberResults.map((member) => (
                  <li key={member.id}>
                    <button type="button" disabled={busy} onClick={() => reserve(member)}>
                      <span className="person-cell"><span className={`person-avatar ${memberAvatarColor(member.id)}`}>{`${member.first_name[0] ?? ""}${member.last_name[0] ?? ""}`.toUpperCase()}</span><span><strong>{member.first_name} {member.last_name}</strong><small>{member.email ?? member.phone ?? "Socio"}</small></span></span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {loading ? <p className="panel-hint">Cargando lista…</p>
          : error ? <p className="role-empty" role="alert">{error}</p>
          : reservations.length === 0 ? <p className="panel-hint">Todavía no hay reservas para esta clase.</p>
          : (
            <div className="table-scroll roster-scroll">
              <table className="data-table">
                <thead><tr><th>SOCIO</th><th>ORIGEN</th><th>ESTADO</th>{canManage && <th />}</tr></thead>
                <tbody>
                  {reservations.map((reservation) => (
                    <tr key={reservation.id}>
                      <td><div className="person-cell"><span className={`person-avatar ${memberAvatarColor(reservation.member_id)}`}>{reservation.member_name.slice(0, 2).toUpperCase()}</span><span><strong>{reservation.member_name}</strong><small>{reservation.member_email ?? "Sin correo"}{reservation.waitlist_position ? ` · turno ${reservation.waitlist_position}` : ""}</small></span></div></td>
                      <td>{reservation.origin === "reception" ? "Recepción" : reservation.origin === "app" ? "App" : "Web"}</td>
                      <td><span className={`status-badge ${classReservationBadge(reservation.status)}`}><i />{classReservationLabels[reservation.status]}</span>{reservation.late_cancellation && <small className="pos-min"> · cancelación tardía</small>}{isPremium && (reservation.charge_status === "completed" && reservation.charge_cents !== null ? <small className="pos-min"> · pagado {formatMoney(reservation.charge_cents)}</small> : reservation.charge_status === "refunded" && reservation.charge_cents !== null ? <small className="pos-min"> · reembolsado {formatMoney(reservation.charge_cents)}</small> : reservation.status === "reserved" ? <small className="pos-min"> · cobro pendiente {formatMoney(current.extra_price_cents)}</small> : null)}</td>
                      {canManage && (
                        <td><div className="pos-row-actions">
                          {reservation.status === "reserved" && <button type="button" className="text-button" disabled={busy} onClick={() => mark(reservation, true)}>Asistió</button>}
                          {(reservation.status === "reserved" || reservation.status === "attended") && <button type="button" className="text-button" disabled={busy} onClick={() => mark(reservation, false)}>No asistió</button>}
                          {(reservation.status === "reserved" || reservation.status === "waitlist") && <button type="button" className="text-button" disabled={busy} onClick={() => cancelReservation(reservation)}>Cancelar</button>}
                        </div></td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cerrar</button></div>
      </section>
    </div>
  );
}

function ClassTypeModal({ onClose, onSaved, onUnauthorized }: { onClose: () => void; onSaved: (message: string) => void; onUnauthorized: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim()) { setError("El nombre es obligatorio."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/classes/types", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), description: description.trim() || null }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo crear el tipo de clase."); return; }
      onSaved(`Tipo de clase creado: ${name.trim()}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="class-type-title">
        <div className="modal-header"><span className="modal-icon"><Dumbbell size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">CATÁLOGO DE CLASES</p>
        <h2 id="class-type-title">Nuevo tipo de clase</h2>
        <p className="modal-subtitle">Agrupa las clases por disciplina para filtrar la agenda y los reportes.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Nombre</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Ej. Yoga" maxLength={120} autoFocus /></label>
          <label className="form-field"><span>Descripción (opcional)</span><input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Nivel, duración, equipo…" maxLength={400} /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : "Crear tipo"}</button></div>
        </form>
      </section>
    </div>
  );
}

function ClassRoomModal({ onClose, onSaved, onUnauthorized }: { onClose: () => void; onSaved: (message: string) => void; onUnauthorized: () => void }) {
  const [name, setName] = useState("");
  const [capacity, setCapacity] = useState("20");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim()) { setError("El nombre es obligatorio."); return; }
    const capacityValue = Number.parseInt(capacity, 10);
    if (!Number.isFinite(capacityValue) || capacityValue <= 0) { setError("La capacidad debe ser mayor que cero."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/classes/rooms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), capacity: capacityValue }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo crear el salón."); return; }
      onSaved(`Salón creado: ${name.trim()}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="class-room-title">
        <div className="modal-header"><span className="modal-icon"><DoorOpen size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">CATÁLOGO DE CLASES</p>
        <h2 id="class-room-title">Nuevo salón</h2>
        <p className="modal-subtitle">La capacidad del salón es una referencia; el cupo real se define por clase.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Nombre</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Ej. Salón A" maxLength={120} autoFocus /></label>
          <label className="form-field"><span>Capacidad</span><input value={capacity} onChange={(event) => setCapacity(event.target.value)} inputMode="numeric" /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : "Crear salón"}</button></div>
        </form>
      </section>
    </div>
  );
}

type LineDraft = {
  key: string;
  exercise_id: string;
  sets: string;
  reps: string;
  rest_seconds: string;
  load_note: string;
  notes: string;
};

function newLineDraft(exerciseId = ""): LineDraft {
  return {
    key: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    exercise_id: exerciseId,
    sets: "3",
    reps: "10",
    rest_seconds: "60",
    load_note: "",
    notes: "",
  };
}

function lineDraftPayload(line: LineDraft) {
  const sets = Number.parseInt(line.sets, 10);
  const rest = line.rest_seconds.trim() === "" ? null : Number.parseInt(line.rest_seconds, 10);
  return {
    exercise_id: line.exercise_id,
    sets: Number.isFinite(sets) ? sets : 0,
    reps: line.reps.trim(),
    rest_seconds: rest === null || Number.isFinite(rest) ? rest : null,
    load_note: line.load_note.trim() || null,
    notes: line.notes.trim() || null,
  };
}

function formatStamp(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

function RoutineLineEditor({ exercises, lines, disabled, onChange }: { exercises: BackendExercise[]; lines: LineDraft[]; disabled?: boolean; onChange: (lines: LineDraft[]) => void }) {
  const update = (key: string, patch: Partial<LineDraft>) => onChange(lines.map((line) => (line.key === key ? { ...line, ...patch } : line)));
  return (
    <div className="routine-builder">
      <div className="routine-builder-head"><span>Ejercicio</span><span>Series</span><span>Reps</span><span>Descanso (s)</span><span>Carga</span><span /></div>
      {lines.map((line) => (
        <div className="routine-builder-row" key={line.key}>
          <select value={line.exercise_id} disabled={disabled} onChange={(event) => update(line.key, { exercise_id: event.target.value })}>
            <option value="">Selecciona…</option>
            {exercises.map((exercise) => <option key={exercise.id} value={exercise.id}>{exercise.name}</option>)}
          </select>
          <input value={line.sets} disabled={disabled} inputMode="numeric" aria-label="Series" onChange={(event) => update(line.key, { sets: event.target.value })} />
          <input value={line.reps} disabled={disabled} aria-label="Repeticiones" placeholder="10" onChange={(event) => update(line.key, { reps: event.target.value })} />
          <input value={line.rest_seconds} disabled={disabled} inputMode="numeric" aria-label="Descanso en segundos" onChange={(event) => update(line.key, { rest_seconds: event.target.value })} />
          <input value={line.load_note} disabled={disabled} aria-label="Carga" placeholder="Opcional" onChange={(event) => update(line.key, { load_note: event.target.value })} />
          <button type="button" className="icon-button" aria-label="Quitar ejercicio" disabled={disabled || lines.length <= 1} onClick={() => onChange(lines.filter((item) => item.key !== line.key))}><Trash2 size={15} /></button>
        </div>
      ))}
      <button type="button" className="button button-secondary button-small" disabled={disabled} onClick={() => onChange([...lines, newLineDraft()])}><Plus size={15} />Agregar ejercicio</button>
    </div>
  );
}

function RoutinePlanList({ items }: { items: BackendRoutineLine[] }) {
  if (items.length === 0) return <p className="panel-hint">Esta versión todavía no tiene ejercicios.</p>;
  return (
    <ol className="routine-plan-list">
      {items.map((item) => (
        <li className="routine-plan-row" key={item.id}>
          <span className="routine-plan-index">{item.position}</span>
          <span className="routine-plan-body">
            <strong>{item.exercise_name}</strong>
            <small>{item.muscle_group} · {item.category}{item.load_note ? ` · ${item.load_note}` : ""}</small>
            {equipmentUnavailable(item.equipment_status) && (
              <span className="routine-plan-warning"><AlertTriangle size={12} />Equipo {item.equipment_status === "out_of_service" ? "fuera de servicio" : "en mantenimiento"}</span>
            )}
          </span>
          <span className="routine-plan-meta">{item.sets} × {item.reps}{item.rest_seconds ? ` · ${item.rest_seconds}s` : ""}</span>
        </li>
      ))}
    </ol>
  );
}

function PhysioView({ permissions, onUnauthorized, onToast }: { permissions: string[]; onUnauthorized: () => void; onToast: (message: string) => void }) {
  const canManage = permissions.includes("physio.manage");
  const canAdjust = permissions.includes("physio.adjust");
  const canReadReport = permissions.includes("finance.read");

  const [tab, setTab] = useState<"agenda" | "paquetes" | "catalogo" | "reporte">("agenda");
  const [day, setDay] = useState(todayInputValue());
  const [therapistFilter, setTherapistFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | PhysioAppointmentState>("");
  const [paymentMethod, setPaymentMethod] = useState<PhysioPaymentMethod>("cash");
  const [refresh, setRefresh] = useState(0);
  const reload = () => setRefresh((value) => value + 1);

  const [appointments, setAppointments] = useState<BackendPhysioAppointment[]>([]);
  const [appointmentsLoading, setAppointmentsLoading] = useState(false);
  const [appointmentsError, setAppointmentsError] = useState("");

  const [services, setServices] = useState<BackendPhysioService[]>([]);
  const [offers, setOffers] = useState<BackendPhysioOffer[]>([]);
  const [therapists, setTherapists] = useState<BackendPhysioTherapist[]>([]);
  const [rooms, setRooms] = useState<BackendPhysioRoom[]>([]);
  const [specialties, setSpecialties] = useState<BackendPhysioSpecialty[]>([]);
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const [roomDraft, setRoomDraft] = useState("");
  const [specialtyDraft, setSpecialtyDraft] = useState("");
  const [catalogBusy, setCatalogBusy] = useState(false);

  const [appointmentModal, setAppointmentModal] = useState<{ appointment: BackendPhysioAppointment | null } | null>(null);
  const [packModalOpen, setPackModalOpen] = useState(false);
  const [serviceModal, setServiceModal] = useState<{ service: BackendPhysioService | null } | null>(null);
  const [offerModal, setOfferModal] = useState<{ offer: BackendPhysioOffer | null } | null>(null);
  const [confirming, setConfirming] = useState<{ kind: "cancel" | "close-day"; appointment?: BackendPhysioAppointment } | null>(null);
  const [busy, setBusy] = useState(false);

  const [packQuery, setPackQuery] = useState("");
  const [packResults, setPackResults] = useState<BackendMember[]>([]);
  const [packSearching, setPackSearching] = useState(false);
  const [packMember, setPackMember] = useState<BackendMember | null>(null);
  const [packs, setPacks] = useState<BackendPhysioPack[]>([]);
  const [packsLoading, setPacksLoading] = useState(false);
  const [packDetail, setPackDetail] = useState<{ pack: BackendPhysioPack; adjustments: BackendPhysioPackAdjustment[] } | null>(null);
  const [packAction, setPackAction] = useState<{ kind: "extend" | "void"; pack: BackendPhysioPack; days: string; reason: string; error: string } | null>(null);

  const [reportFrom, setReportFrom] = useState(todayInputValue());
  const [reportTo, setReportTo] = useState(todayInputValue());
  const [report, setReport] = useState<BackendPhysioReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      setCatalogLoaded(false);
      try {
        const [servicesResponse, offersResponse, therapistsResponse, roomsResponse, specialtiesResponse] = await Promise.all([
          fetch("/api/admin/physio/services", { cache: "no-store" }),
          fetch("/api/admin/physio/offers", { cache: "no-store" }),
          fetch("/api/admin/physio/therapists", { cache: "no-store" }),
          fetch("/api/admin/physio/rooms", { cache: "no-store" }),
          fetch("/api/admin/physio/specialties", { cache: "no-store" }),
        ]);
        if ([servicesResponse, offersResponse, therapistsResponse, roomsResponse, specialtiesResponse].some((response) => response.status === 401)) {
          onUnauthorized();
          return;
        }
        if (!active) return;
        if (servicesResponse.ok) setServices(await servicesResponse.json() as BackendPhysioService[]);
        if (offersResponse.ok) setOffers(await offersResponse.json() as BackendPhysioOffer[]);
        if (therapistsResponse.ok) setTherapists(await therapistsResponse.json() as BackendPhysioTherapist[]);
        if (roomsResponse.ok) setRooms(await roomsResponse.json() as BackendPhysioRoom[]);
        if (specialtiesResponse.ok) setSpecialties(await specialtiesResponse.json() as BackendPhysioSpecialty[]);
      } catch {
        // The catalogue only feeds the forms and labels; the agenda still loads.
      } finally {
        if (active) setCatalogLoaded(true);
      }
    };
    void load();
    return () => { active = false; };
  }, [refresh, onUnauthorized]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setAppointmentsLoading(true);
      setAppointmentsError("");
      const params = new URLSearchParams();
      if (day) params.set("date", day);
      if (therapistFilter) params.set("therapist_id", therapistFilter);
      if (statusFilter) params.set("status", statusFilter);
      try {
        const response = await fetch(`/api/admin/physio/appointments?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        const data = await response.json() as BackendPhysioAppointment[];
        if (active) setAppointments(data);
      } catch {
        if (active) setAppointmentsError("No se pudo cargar la agenda de fisioterapia.");
      } finally {
        if (active) setAppointmentsLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [day, therapistFilter, statusFilter, refresh, onUnauthorized]);

  useEffect(() => {
    const term = packQuery.trim();
    if (term.length < 2) { setPackResults([]); return; }
    let active = true;
    const handle = window.setTimeout(async () => {
      setPackSearching(true);
      try {
        const response = await fetch(`/api/admin/members?search=${encodeURIComponent(term)}&page_size=6`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (response.ok) {
          const directory = await response.json() as MemberDirectory;
          if (active) setPackResults(directory.items);
        } else if (active) {
          setPackResults([]);
        }
      } catch {
        if (active) setPackResults([]);
      } finally {
        if (active) setPackSearching(false);
      }
    }, 250);
    return () => { active = false; window.clearTimeout(handle); };
  }, [packQuery, onUnauthorized]);

  useEffect(() => {
    if (!packMember) { setPacks([]); return; }
    let active = true;
    const load = async () => {
      setPacksLoading(true);
      try {
        const response = await fetch(`/api/admin/physio/packs?member_id=${encodeURIComponent(packMember.id)}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        const data = await response.json() as BackendPhysioPack[];
        if (active) setPacks(data);
      } catch {
        if (active) setPacks([]);
      } finally {
        if (active) setPacksLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [packMember, refresh, onUnauthorized]);

  useEffect(() => {
    if (tab !== "reporte" || !canReadReport) return;
    if (!reportFrom || !reportTo || reportFrom > reportTo) {
      setReport(null);
      setReportError("El rango de fechas no es válido.");
      return;
    }
    let active = true;
    const load = async () => {
      setReportLoading(true);
      setReportError("");
      const params = new URLSearchParams({ date_from: reportFrom, date_to: reportTo });
      try {
        const response = await fetch(`/api/admin/physio/report?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        const data = await response.json() as BackendPhysioReport;
        if (active) setReport(data);
      } catch {
        if (active) setReportError("No se pudo cargar el reporte de fisioterapia.");
      } finally {
        if (active) setReportLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [tab, canReadReport, reportFrom, reportTo, refresh, onUnauthorized]);

  const openPackDetail = async (pack: BackendPhysioPack) => {
    try {
      const response = await fetch(`/api/admin/physio/packs/${pack.id}`, { cache: "no-store" });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) return;
      setPackDetail(await response.json() as { pack: BackendPhysioPack; adjustments: BackendPhysioPackAdjustment[] });
    } catch {
      // El historial es informativo; la tabla ya muestra el estado del paquete.
    }
  };

  const openPackAction = (kind: "extend" | "void", pack: BackendPhysioPack) => {
    setPackAction({ kind, pack, days: kind === "extend" ? "30" : "", reason: "", error: "" });
    void openPackDetail(pack);
  };

  const submitPackAction = async () => {
    if (!packAction) return;
    const { kind, pack, days } = packAction;
    const reason = packAction.reason.trim();
    if (reason.length === 0) { setPackAction({ ...packAction, error: "Escribe el motivo del ajuste." }); return; }
    let parsedDays = 0;
    if (kind === "extend") {
      parsedDays = Number(days);
      if (!Number.isInteger(parsedDays) || parsedDays < 1 || parsedDays > 366) { setPackAction({ ...packAction, error: "Indica entre 1 y 366 días." }); return; }
    }
    setBusy(true);
    try {
      const response = await fetch(`/api/admin/physio/packs/${pack.id}/${kind}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(kind === "extend" ? { days: parsedDays, reason } : { reason }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string; pack?: BackendPhysioPack; cancelled_appointments?: number };
      if (!response.ok) { setPackAction({ ...packAction, error: payload.detail || "No se pudo ajustar el paquete." }); return; }
      setPackAction(null);
      setPackDetail(null);
      reload();
      if (kind === "extend") {
        onToast(`Paquete extendido ${parsedDays} días (acumulado ${payload.pack?.extended_days ?? parsedDays}).`);
      } else {
        onToast(payload.cancelled_appointments
          ? `Paquete anulado sin devolución; ${payload.cancelled_appointments} cita(s) futuras canceladas.`
          : "Paquete anulado sin devolución.");
      }
    } catch {
      setPackAction({ ...packAction, error: "No se pudo conectar con el backend." });
    } finally {
      setBusy(false);
    }
  };

  const createCatalogItem = async (kind: "room" | "specialty") => {
    const name = (kind === "room" ? roomDraft : specialtyDraft).trim();
    if (!name) return;
    setCatalogBusy(true);
    try {
      const response = await fetch(`/api/admin/physio/${kind === "room" ? "rooms" : "specialties"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || `No se pudo crear ${kind === "room" ? "el consultorio" : "la especialidad"}.`); return; }
      if (kind === "room") setRoomDraft(""); else setSpecialtyDraft("");
      reload();
      onToast(kind === "room" ? "Consultorio creado." : "Especialidad creada.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setCatalogBusy(false);
    }
  };

  const toggleCatalogItem = async (kind: "room" | "specialty", item: BackendPhysioRoom | BackendPhysioSpecialty) => {
    setCatalogBusy(true);
    try {
      const response = await fetch(`/api/admin/physio/${kind === "room" ? "rooms" : "specialties"}/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !item.is_active }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo actualizar el catálogo."); return; }
      reload();
      onToast(item.is_active ? "Registro desactivado." : "Registro activado.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setCatalogBusy(false);
    }
  };

  const assignTherapistProfile = async (therapist: BackendPhysioTherapist, patch: { specialty_id?: string | null; room_id?: string | null }) => {
    setCatalogBusy(true);
    try {
      const response = await fetch(`/api/admin/physio/therapists/${therapist.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo actualizar el perfil del fisioterapeuta."); return; }
      reload();
      onToast(`Perfil de ${therapist.name} actualizado.`);
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setCatalogBusy(false);
    }
  };

  const mark = async (appointment: BackendPhysioAppointment, attended: boolean) => {
    setBusy(true);
    try {
      const response = await fetch(`/api/admin/physio/appointments/${appointment.id}/attendance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // El backend ignora la forma de pago cuando el paquete cubre la sesión.
        body: JSON.stringify({ attended, payment_method: attended ? paymentMethod : null }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as Partial<BackendPhysioAppointment> & { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo registrar la asistencia."); return; }
      reload();
      if (attended) {
        if (payload.charge_status === "completed" && payload.charge_cents != null) {
          onToast(`Asistencia registrada · cobro de ${formatMoney(payload.charge_cents)} (${paymentMethodLabels[payload.charge_payment_method ?? ""] ?? payload.charge_payment_method}).`);
        } else if (payload.pack_id) {
          onToast(`Asistencia registrada · sesión descontada del paquete${payload.pack_remaining_sessions != null ? ` (quedan ${payload.pack_remaining_sessions})` : ""}.`);
        } else {
          onToast("Asistencia registrada.");
        }
      } else {
        onToast(appointment.status === "attended" ? "Cita corregida a inasistencia; la sesión o el cobro se revirtió." : "Inasistencia registrada.");
      }
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const cancelAppointment = async (appointment: BackendPhysioAppointment) => {
    setConfirming(null);
    setBusy(true);
    try {
      const response = await fetch(`/api/admin/physio/appointments/${appointment.id}/cancel`, { method: "POST" });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo cancelar la cita."); return; }
      reload();
      onToast("Cita cancelada. El paquete y el cobro no se modifican.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const closeDay = async () => {
    setConfirming(null);
    setBusy(true);
    try {
      const response = await fetch("/api/admin/physio/appointments/close-day", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: day }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string; closed?: number };
      if (!response.ok) { onToast(payload.detail || "No se pudo cerrar el día."); return; }
      reload();
      onToast(payload.closed ? `${payload.closed} cita(s) pendientes marcadas como inasistencia.` : "No quedaban citas pendientes por cerrar.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const scheduledCount = appointments.filter((item) => item.status === "scheduled").length;
  const attendedCount = appointments.filter((item) => item.status === "attended").length;
  const noShowCount = appointments.filter((item) => item.status === "no_show").length;
  const coveredCount = appointments.filter((item) => item.pack_id !== null).length;

  const tabButton = (value: "agenda" | "paquetes" | "catalogo" | "reporte", label: string) => (
    <button type="button" className={tab === value ? "staff-tab-active" : ""} onClick={() => setTab(value)}>{label}</button>
  );

  return (
    <>
      <section className="access-summary-band pos-cash-band">
        <div className="access-summary-main">
          <span className="summary-icon"><Activity size={18} /></span>
          <div>
            <span>AGENDA DE FISIOTERAPIA</span>
            <strong>{appointmentsLoading ? "Consultando…" : `${appointments.length} citas ${day ? `del ${formatInputDay(day)}` : "en total"}`}</strong>
          </div>
        </div>
        <div className="summary-divider" />
        <div className="summary-stat"><span>AGENDADAS</span><strong>{scheduledCount}</strong></div>
        <div className="summary-stat"><span>ASISTIERON</span><strong>{attendedCount}</strong></div>
        <div className="summary-stat"><span>INASISTENCIAS</span><strong>{noShowCount}</strong></div>
        <div className="summary-stat"><span>CON PAQUETE</span><strong>{coveredCount}</strong></div>
        {canManage && <button className="button button-secondary" onClick={() => setConfirming({ kind: "close-day" })}><Check size={16} />Cerrar día</button>}
        {canManage && <button className="button button-primary" onClick={() => setAppointmentModal({ appointment: null })}><Plus size={16} />Agendar cita</button>}
      </section>

      {confirming && (
        <div className="modal-note physio-confirm">
          <AlertTriangle size={16} />
          <span>
            {confirming.kind === "close-day"
              ? `¿Cerrar el ${formatInputDay(day)}? Las citas pendientes que ya terminaron se marcan como inasistencia; no se cobra ni se descuenta ninguna sesión.`
              : `¿Cancelar la cita de ${confirming.appointment?.member_name}? El paquete y el cobro no se modifican.`}
          </span>
          <div className="physio-confirm-actions">
            <button type="button" className="button button-secondary button-small" onClick={() => setConfirming(null)}>Volver</button>
            <button
              type="button"
              className="button button-primary button-small"
              disabled={busy}
              onClick={() => (confirming.kind === "cancel" && confirming.appointment ? cancelAppointment(confirming.appointment) : closeDay())}
            >
              Confirmar
            </button>
          </div>
        </div>
      )}

      <div className="staff-tabs pos-tabs">
        {tabButton("agenda", "Agenda")}
        {tabButton("paquetes", "Paquetes")}
        {tabButton("catalogo", "Catálogo")}
        {canReadReport && tabButton("reporte", "Reporte")}
        <span className="staff-tabs-note"><ShieldCheck size={14} />Las sesiones se descuentan del paquete al marcar la asistencia</span>
      </div>

      {tab === "agenda" && (
        <section className="panel full-panel">
          <div className="panel-header access-list-heading">
            <div><p className="section-kicker">CITAS</p><h2>Agenda del día</h2></div>
            {canManage && <button className="button button-primary" onClick={() => setAppointmentModal({ appointment: null })}><Plus size={17} />Agendar cita</button>}
          </div>
          <div className="table-toolbar">
            <label className="table-select"><span>Día</span><input type="date" value={day} onChange={(event) => setDay(event.target.value)} /></label>
            <label className="table-select"><span>Terapeuta</span><select value={therapistFilter} onChange={(event) => setTherapistFilter(event.target.value)}><option value="">Todos</option>{therapists.map((therapist) => <option key={therapist.id} value={therapist.id}>{therapist.name}</option>)}</select></label>
            <label className="table-select"><span>Estado</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as "" | PhysioAppointmentState)}><option value="">Todos</option><option value="scheduled">Agendadas</option><option value="attended">Asistieron</option><option value="no_show">No asistieron</option><option value="cancelled">Canceladas</option></select></label>
            {canManage && <label className="table-select"><span>Cobro de sesión suelta</span><select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value as PhysioPaymentMethod)}><option value="cash">Efectivo</option><option value="card">Tarjeta</option><option value="transfer">Transferencia</option><option value="account">Cuenta del socio</option></select></label>}
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>PACIENTE</th><th>SERVICIO</th><th>TERAPEUTA</th><th>HORARIO</th><th>CUBERTURA</th><th>COBRO</th><th>ESTADO</th><th /></tr></thead>
              <tbody>
                {appointmentsLoading ? <tr><td colSpan={8} className="empty-row">Cargando agenda…</td></tr>
                  : appointmentsError ? <tr><td colSpan={8} className="empty-row">{appointmentsError}</td></tr>
                  : appointments.length === 0 ? <tr><td colSpan={8} className="empty-row">No hay citas para este filtro.</td></tr>
                  : appointments.map((appointment) => {
                    const future = parseBackendMoment(appointment.starts_at).getTime() > Date.now();
                    const canMove = canManage && appointment.status === "scheduled" && future;
                    return (
                      <tr key={appointment.id}>
                        <td><div className="person-cell"><span className={`person-avatar ${memberAvatarColor(appointment.member_id)}`}>{appointment.member_name.slice(0, 2).toUpperCase()}</span><span><strong>{appointment.member_name}</strong><small>{appointment.notes ?? "Sin notas"}</small></span></div></td>
                        <td>{appointment.service_name}<small className="pos-min">{formatMoney(appointment.service_price_cents)} por sesión</small></td>
                        <td>{appointment.therapist_name}</td>
                        <td className="time-cell">{formatPhysioDay(appointment.starts_at)}<small className="pos-min">{formatPhysioClock(appointment.starts_at)}–{formatPhysioClock(appointment.ends_at)}{appointment.room ? ` · ${appointment.room}` : ""}</small></td>
                        <td>{appointment.pack_id ? <span className="status-badge status-good"><i />Paquete{appointment.pack_remaining_sessions != null ? ` · ${appointment.pack_remaining_sessions} restantes` : ""}</span> : <span className="status-badge status-neutral"><i />Sesión suelta</span>}</td>
                        <td>
                          {appointment.charge_status === "completed" && appointment.charge_cents != null ? (
                            <>Cobrado {formatMoney(appointment.charge_cents)}<small className="pos-min">{paymentMethodLabels[appointment.charge_payment_method ?? ""] ?? appointment.charge_payment_method}</small></>
                          ) : appointment.charge_status === "refunded" && appointment.charge_cents != null ? (
                            <>Reembolsado {formatMoney(appointment.charge_cents)}</>
                          ) : appointment.status === "scheduled" ? (
                            <span className="pos-min">{appointment.pack_id ? "Se descuenta del paquete" : `Por cobrar ${formatMoney(appointment.service_price_cents)}`}</span>
                          ) : (
                            <span className="pos-min">—</span>
                          )}
                        </td>
                        <td><span className={`status-badge ${physioStatusBadge(appointment.status)}`}><i />{physioStatusLabels[appointment.status]}</span></td>
                        <td>
                          {canManage && appointment.status !== "cancelled" && (
                            <div className="pos-row-actions">
                              {appointment.status !== "attended" && <button type="button" className="text-button" disabled={busy || future} title={future ? "La cita aún no empieza" : undefined} onClick={() => mark(appointment, true)}>Asistió</button>}
                              {appointment.status !== "no_show" && <button type="button" className="text-button" disabled={busy || future} title={future ? "La cita aún no empieza" : undefined} onClick={() => mark(appointment, false)}>No asistió</button>}
                              {canMove && <button type="button" className="text-button" disabled={busy} onClick={() => setAppointmentModal({ appointment })}>Mover</button>}
                              {canMove && <button type="button" className="text-button" disabled={busy} onClick={() => setConfirming({ kind: "cancel", appointment })}>Cancelar</button>}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
          <div className="table-bottom">
            <span>{appointments.length} citas · ventana de asistencia desde el inicio hasta 24 h después del fin</span>
          </div>
        </section>
      )}

      {tab === "paquetes" && (
        <section className="panel full-panel">
          <div className="panel-header access-list-heading">
            <div><p className="section-kicker">PAQUETES</p><h2>Paquetes prepagados</h2></div>
            {canManage && <button className="button button-primary" onClick={() => setPackModalOpen(true)}><Plus size={17} />Vender paquete</button>}
          </div>
          <div className="class-roster-search">
            <label className="form-field"><span>Buscar socio</span><input value={packQuery} onChange={(event) => setPackQuery(event.target.value)} placeholder="Nombre o correo" autoComplete="off" /></label>
            {packSearching && <p className="manual-hint">Buscando socios…</p>}
            {packResults.length > 0 && (
              <ul className="manual-results">
                {packResults.map((member) => (
                  <li key={member.id}>
                    <button type="button" onClick={() => { setPackMember(member); setPackQuery(""); setPackResults([]); }}>
                      <span className="person-cell"><span className={`person-avatar ${memberAvatarColor(member.id)}`}>{`${member.first_name[0] ?? ""}${member.last_name[0] ?? ""}`.toUpperCase()}</span><span><strong>{member.first_name} {member.last_name}</strong><small>{member.email ?? member.phone ?? "Socio"}</small></span></span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {packMember ? (
            <>
              <div className="panel-header access-list-heading">
                <div className="person-cell"><span className={`person-avatar ${memberAvatarColor(packMember.id)}`}>{`${packMember.first_name[0] ?? ""}${packMember.last_name[0] ?? ""}`.toUpperCase()}</span><span><strong>{packMember.first_name} {packMember.last_name}</strong><small>{packMember.email ?? packMember.phone ?? "Socio"}</small></span></div>
                <button type="button" className="text-button" onClick={() => { setPackMember(null); setPacks([]); }}>Cambiar socio</button>
              </div>
              {packAction && (
                <div className="modal-note physio-confirm">
                  <AlertTriangle size={16} />
                  <div className="physio-action-card">
                    <strong>{packAction.kind === "extend" ? "Extender vigencia" : "Anular paquete"} · {packAction.pack.offer_name}</strong>
                    <p>
                      {packAction.kind === "extend"
                        ? "Suma días de vigencia desde hoy o desde el vencimiento actual, lo que ocurra más tarde. Cada ajuste queda auditado con su motivo."
                        : `Anula las ${packAction.pack.remaining_sessions} sesión(es) restantes sin reembolso y cancela las citas futuras cubiertas por el paquete.`}
                    </p>
                    <div className="form-row">
                      {packAction.kind === "extend" && (
                        <label className="form-field"><span>Días (1-366)</span><input type="number" min={1} max={366} value={packAction.days} onChange={(event) => setPackAction({ ...packAction, days: event.target.value, error: "" })} /></label>
                      )}
                      <label className="form-field"><span>Motivo (obligatorio)</span><input value={packAction.reason} maxLength={300} placeholder="Ej. Lesión, viaje, ajuste comercial…" onChange={(event) => setPackAction({ ...packAction, reason: event.target.value, error: "" })} /></label>
                    </div>
                    {packAction.error && <div className="login-error" role="alert">{packAction.error}</div>}
                    <div className="physio-confirm-actions">
                      <button type="button" className="button button-secondary button-small" onClick={() => { setPackAction(null); setPackDetail(null); }}>Volver</button>
                      <button type="button" className="button button-primary button-small" disabled={busy} onClick={submitPackAction}>{packAction.kind === "extend" ? "Extender paquete" : "Anular paquete"}</button>
                    </div>
                    {packDetail && packDetail.adjustments.length > 0 && (
                      <ul className="physio-adjustment-list">
                        {packDetail.adjustments.map((adjustment) => (
                          <li key={adjustment.id}>
                            <span>{adjustment.kind === "extension" ? `Extensión de ${adjustment.days ?? 0} días` : "Anulación"}</span>
                            <small>{formatPhysioDate(adjustment.created_at)} · {adjustment.reason}</small>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )}
              {packsLoading ? <p className="panel-hint">Cargando paquetes…</p>
                : packs.length === 0 ? <p className="panel-hint">Este socio no tiene paquetes de fisioterapia.</p>
                : (
                  <div className="table-scroll">
                    <table className="data-table">
                      <thead><tr><th>PAQUETE</th><th>SERVICIO</th><th>SESIONES</th><th>VIGENCIA</th><th>ESTADO</th><th>PRECIO</th>{canAdjust && <th />}</tr></thead>
                      <tbody>
                        {packs.map((pack) => (
                          <tr key={pack.id}>
                            <td><strong>{pack.offer_name}</strong><small className="pos-min">Comprado {formatPhysioDate(pack.purchased_at)}{pack.voided_at ? ` · Anulado ${formatPhysioDate(pack.voided_at)}` : ""}</small></td>
                            <td>{pack.service_name}</td>
                            <td>{pack.sessions_used}/{pack.sessions_total}<small className="pos-min">{pack.remaining_sessions} restantes{pack.voided_sessions > 0 ? ` · ${pack.voided_sessions} anuladas` : ""}</small></td>
                            <td>{formatPhysioDate(pack.valid_until)}{pack.extended_days > 0 && <small className="pos-min">+{pack.extended_days} días extendidos</small>}</td>
                            <td><span className={`status-badge ${physioPackBadge(pack.status)}`}><i />{physioPackStatusLabels[pack.status]}</span>{pack.void_reason && <small className="pos-min">{pack.void_reason}</small>}</td>
                            <td>{formatMoney(pack.price_cents)}</td>
                            {canAdjust && (
                              <td>
                                {pack.status !== "voided" && (
                                  <div className="pos-row-actions">
                                    <button type="button" className="text-button" disabled={busy} onClick={() => openPackAction("extend", pack)}>Extender</button>
                                    {pack.remaining_sessions > 0 && <button type="button" className="text-button" disabled={busy} onClick={() => openPackAction("void", pack)}>Anular</button>}
                                  </div>
                                )}
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
            </>
          ) : <p className="panel-hint">Busca un socio para consultar sus paquetes y sesiones restantes.</p>}
        </section>
      )}

      {tab === "catalogo" && (
        <>
          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-header"><div><p className="section-kicker">CATÁLOGO</p><h2>Servicios</h2></div>{canManage && <button className="button button-primary button-small" onClick={() => setServiceModal({ service: null })}><Plus size={15} />Agregar</button>}</div>
              {services.length === 0 ? <p className="panel-hint">{catalogLoaded ? "Aún no hay servicios de fisioterapia." : "Cargando…"}</p> : (
                <ul className="class-catalog-list">
                  {services.map((service) => (
                    <li key={service.id}>
                      <span className="class-type-dot" />
                      <span><strong>{service.name}{service.is_active ? "" : " · Inactivo"}</strong><small>{service.code} · {service.duration_minutes} min · {formatMoney(service.price_cents)}</small></span>
                      {canManage && <button type="button" className="text-button" style={{ marginLeft: "auto" }} onClick={() => setServiceModal({ service })}>Editar</button>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="panel">
              <div className="panel-header"><div><p className="section-kicker">CATÁLOGO</p><h2>Paquetes</h2></div>{canManage && <button className="button button-primary button-small" onClick={() => setOfferModal({ offer: null })}><Plus size={15} />Agregar</button>}</div>
              {offers.length === 0 ? <p className="panel-hint">{catalogLoaded ? "Aún no hay paquetes configurados." : "Cargando…"}</p> : (
                <ul className="class-catalog-list">
                  {offers.map((offer) => (
                    <li key={offer.id}>
                      <span className="class-type-dot" />
                      <span><strong>{offer.name}{offer.is_active ? "" : " · Inactivo"}</strong><small>{offer.service_name} · {offer.sessions} sesiones · {formatMoney(offer.price_cents)} · vigencia {offer.validity_days} días{offer.discount_percent > 0 ? ` · -${offer.discount_percent}%` : ""}</small></span>
                      {canManage && <button type="button" className="text-button" style={{ marginLeft: "auto" }} onClick={() => setOfferModal({ offer })}>Editar</button>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-header"><div><p className="section-kicker">CATÁLOGO</p><h2>Consultorios</h2></div></div>
              {canManage && (
                <form className="physio-catalog-form" onSubmit={(event) => { event.preventDefault(); void createCatalogItem("room"); }}>
                  <label className="form-field"><span>Nuevo consultorio</span><input value={roomDraft} maxLength={80} placeholder="Ej. Consultorio 3" onChange={(event) => setRoomDraft(event.target.value)} /></label>
                  <button type="submit" className="button button-primary button-small" disabled={catalogBusy || roomDraft.trim().length === 0}><Plus size={15} />Agregar</button>
                </form>
              )}
              {rooms.length === 0 ? <p className="panel-hint">{catalogLoaded ? "Aún no hay consultorios." : "Cargando…"}</p> : (
                <ul className="class-catalog-list">
                  {rooms.map((room) => (
                    <li key={room.id}>
                      <span className="class-type-dot" />
                      <span><strong>{room.name}{room.is_active ? "" : " · Inactivo"}</strong><small>{room.is_active ? "Disponible al agendar" : "Oculto en el agendado"}</small></span>
                      {canManage && <button type="button" className="text-button" style={{ marginLeft: "auto" }} disabled={catalogBusy} onClick={() => void toggleCatalogItem("room", room)}>{room.is_active ? "Desactivar" : "Activar"}</button>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="panel">
              <div className="panel-header"><div><p className="section-kicker">CATÁLOGO</p><h2>Especialidades</h2></div></div>
              {canManage && (
                <form className="physio-catalog-form" onSubmit={(event) => { event.preventDefault(); void createCatalogItem("specialty"); }}>
                  <label className="form-field"><span>Nueva especialidad</span><input value={specialtyDraft} maxLength={80} placeholder="Ej. Terapia manual" onChange={(event) => setSpecialtyDraft(event.target.value)} /></label>
                  <button type="submit" className="button button-primary button-small" disabled={catalogBusy || specialtyDraft.trim().length === 0}><Plus size={15} />Agregar</button>
                </form>
              )}
              {specialties.length === 0 ? <p className="panel-hint">{catalogLoaded ? "Aún no hay especialidades." : "Cargando…"}</p> : (
                <ul className="class-catalog-list">
                  {specialties.map((specialty) => (
                    <li key={specialty.id}>
                      <span className="class-type-dot" />
                      <span><strong>{specialty.name}{specialty.is_active ? "" : " · Inactivo"}</strong><small>{specialty.is_active ? "Disponible para asignar" : "Oculta en la asignación"}</small></span>
                      {canManage && <button type="button" className="text-button" style={{ marginLeft: "auto" }} disabled={catalogBusy} onClick={() => void toggleCatalogItem("specialty", specialty)}>{specialty.is_active ? "Desactivar" : "Activar"}</button>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
          <section className="panel full-panel">
            <div className="panel-header access-list-heading">
              <div><p className="section-kicker">EQUIPO</p><h2>Especialidad y consultorio del fisioterapeuta</h2></div>
              <span className="table-hint">El consultorio predeterminado se usa al agendar si no eliges otro.</span>
            </div>
            {therapists.length === 0 ? <p className="panel-hint">{catalogLoaded ? "Aún no hay fisioterapeutas activos." : "Cargando…"}</p> : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr><th>FISIOTERAPEUTA</th><th>ESPECIALIDAD</th><th>CONSULTORIO PREDETERMINADO</th></tr></thead>
                  <tbody>
                    {therapists.map((therapist) => (
                      <tr key={therapist.id}>
                        <td><strong>{therapist.name}</strong><small className="pos-min">{therapist.job_title}</small></td>
                        <td>
                          <select className="role-assign" value={therapist.specialty_id ?? ""} disabled={!canManage || catalogBusy} onChange={(event) => void assignTherapistProfile(therapist, { specialty_id: event.target.value || null })}>
                            <option value="">Sin especialidad</option>
                            {specialties.filter((specialty) => specialty.is_active || specialty.id === therapist.specialty_id).map((specialty) => <option key={specialty.id} value={specialty.id}>{specialty.name}</option>)}
                          </select>
                        </td>
                        <td>
                          <select className="role-assign" value={therapist.room_id ?? ""} disabled={!canManage || catalogBusy} onChange={(event) => void assignTherapistProfile(therapist, { room_id: event.target.value || null })}>
                            <option value="">Sin consultorio</option>
                            {rooms.filter((room) => room.is_active || room.id === therapist.room_id).map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {tab === "reporte" && canReadReport && (
        <>
          <div className="report-controls">
            <div className="report-dates">
              <label>Desde<input type="date" value={reportFrom} max={reportTo} onChange={(event) => setReportFrom(event.target.value)} /></label>
              <label>Hasta<input type="date" value={reportTo} min={reportFrom} onChange={(event) => setReportTo(event.target.value)} /></label>
            </div>
            <button type="button" className="button button-secondary" onClick={() => setRefresh((value) => value + 1)} disabled={reportLoading}>Actualizar</button>
            <a className="button button-primary" href={`/api/admin/physio/report/export?date_from=${reportFrom}&date_to=${reportTo}`} onClick={() => onToast("Preparando la descarga del reporte en CSV.")}>Exportar CSV</a>
            <span className="table-hint">La ocupación estima 8 h de agenda por fisioterapeuta y día.</span>
          </div>
          {!report ? <ReportFallback loading={reportLoading} error={reportError} /> : (
            <>
              <section className="panel full-panel">
                <div className="panel-header access-list-heading">
                  <div><p className="section-kicker">CONSULTORIO</p><h2>Indicadores del periodo</h2></div>
                  <span className="table-hint">{formatDateOnly(report.date_from)} a {formatDateOnly(report.date_to)}</span>
                </div>
                <div className="report-stat-grid">
                  <ReportStat label="Citas" value={String(report.totals.appointments)} hint={`${report.totals.scheduled} agendadas · ${report.totals.cancelled} canceladas`} />
                  <ReportStat label="Asistencia" value={`${report.totals.attendance_rate_percent}%`} hint={`${report.totals.attended} asistencias`} />
                  <ReportStat label="Inasistencias" value={`${report.totals.no_show_rate_percent}%`} hint={`${report.totals.no_show} no asistidas · ${report.totals.cancellation_rate_percent}% cancelación`} />
                  <ReportStat label="Ocupación" value={`${report.occupancy.percent}%`} hint={`${formatAgendaMinutes(report.occupancy.booked_minutes)} agendadas de ${formatAgendaMinutes(report.occupancy.available_minutes)} disponibles`} />
                  <ReportStat label="Ingresos netos" value={formatMoney(report.revenue.net_cents)} hint={`Paquetes ${formatMoney(report.revenue.package_cents)} · Sueltas ${formatMoney(report.revenue.single_cents)} · Devoluciones ${formatMoney(report.revenue.refunded_cents)}`} />
                  <ReportStat label="Paquetes vendidos" value={String(report.revenue.packages_sold)} hint={`${report.revenue.sessions_sold} sesiones · descuento ${formatMoney(report.revenue.discount_cents)}`} />
                  <ReportStat label="Sesiones sueltas" value={String(report.revenue.single_charges)} hint={formatMoney(report.revenue.single_cents)} />
                  <ReportStat label="Ajustes" value={`${report.adjustments.extended} / ${report.adjustments.voided}`} hint={`${report.adjustments.extended_days} días extendidos · ${report.adjustments.voided_sessions} sesiones anuladas`} />
                </div>
              </section>
              <section className="panel full-panel">
                <div className="panel-header access-list-heading"><div><p className="section-kicker">INGRESOS</p><h2>Por día</h2></div><span className="chart-legend"><i />Paquetes + sesiones sueltas</span></div>
                <ReportBarChart points={report.daily.map((row) => ({ label: reportDayLabel(row.day, report.daily.length), value: row.revenue_cents, hint: `${formatDateOnly(row.day)} · ${formatMoney(row.revenue_cents)} · ${row.appointments} citas (${row.attended} asistieron)` }))} />
                <div className="chart-foot"><span>{formatDateOnly(report.date_from)}</span><span>MXN NETO</span><span>{formatDateOnly(report.date_to)}</span></div>
              </section>
              <div className="report-columns">
                <ReportList title="POR FISIOTERAPEUTA" rows={report.by_therapist.map((row) => ({ label: row.therapist_name, value: `${row.attended}/${row.appointments} · ${Math.round(row.attended_minutes / 60)} h` }))} />
                <ReportList title="POR SERVICIO" rows={report.by_service.map((row) => ({ label: row.service_name, value: `${row.attended}/${row.appointments} · ${row.single_charges} sueltas` }))} />
                <ReportList title="POR HORA" rows={report.by_hour.map((row) => ({ label: `${String(row.hour).padStart(2, "0")}:00`, value: `${row.attended}/${row.appointments}` }))} />
              </div>
              <section className="panel full-panel">
                <div className="panel-header access-list-heading"><div><p className="section-kicker">DETALLE</p><h2>Citas e ingresos por día</h2></div></div>
                <div className="table-scroll">
                  <table className="data-table">
                    <thead><tr><th>DÍA</th><th>CITAS</th><th>ATENDIDAS</th><th>INASISTENCIAS</th><th>CANCELADAS</th><th>INGRESOS</th></tr></thead>
                    <tbody>
                      {report.daily.length === 0 ? <tr><td colSpan={6} className="empty-row">Sin actividad en el periodo.</td></tr>
                        : report.daily.map((row) => (
                          <tr key={row.day}>
                            <td>{formatDateOnly(row.day)}</td>
                            <td>{row.appointments}</td>
                            <td>{row.attended}</td>
                            <td>{row.no_show}</td>
                            <td>{row.cancelled}</td>
                            <td>{formatMoney(row.revenue_cents)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </>
      )}

      {canManage && appointmentModal && (
        <PhysioAppointmentModal
          appointment={appointmentModal.appointment}
          services={services}
          therapists={therapists}
          rooms={rooms}
          onClose={() => setAppointmentModal(null)}
          onSaved={(message) => { setAppointmentModal(null); reload(); onToast(message); }}
          onUnauthorized={onUnauthorized}
        />
      )}
      {canManage && packModalOpen && (
        <PhysioPackModal
          initialMember={packMember}
          offers={offers}
          onClose={() => setPackModalOpen(false)}
          onSaved={(message) => { setPackModalOpen(false); reload(); onToast(message); }}
          onUnauthorized={onUnauthorized}
        />
      )}
      {canManage && serviceModal && (
        <PhysioServiceModal
          service={serviceModal.service}
          onClose={() => setServiceModal(null)}
          onSaved={(message) => { setServiceModal(null); reload(); onToast(message); }}
          onUnauthorized={onUnauthorized}
        />
      )}
      {canManage && offerModal && (
        <PhysioOfferModal
          offer={offerModal.offer}
          services={services}
          onClose={() => setOfferModal(null)}
          onSaved={(message) => { setOfferModal(null); reload(); onToast(message); }}
          onUnauthorized={onUnauthorized}
        />
      )}

      <footer className="page-footer"><span>Centro Fit · Fisioterapia</span><span>DATOS DEL BACKEND · PAQUETES PREPAGADOS Y COBRO EN RECEPCIÓN</span></footer>
    </>
  );
}

function PhysioAppointmentModal({
  appointment,
  services,
  therapists,
  rooms,
  onClose,
  onSaved,
  onUnauthorized,
}: {
  appointment: BackendPhysioAppointment | null;
  services: BackendPhysioService[];
  therapists: BackendPhysioTherapist[];
  rooms: BackendPhysioRoom[];
  onClose: () => void;
  onSaved: (message: string) => void;
  onUnauthorized: () => void;
}) {
  const moving = appointment !== null;
  const availableServices = services.filter((service) => service.is_active || service.id === appointment?.service_id);
  const availableRooms = rooms.filter((room) => room.is_active || room.id === appointment?.room_id);

  const [memberQuery, setMemberQuery] = useState("");
  const [memberResults, setMemberResults] = useState<BackendMember[]>([]);
  const [searching, setSearching] = useState(false);
  const [member, setMember] = useState<BackendMember | null>(null);
  const [serviceId, setServiceId] = useState(appointment?.service_id ?? availableServices[0]?.id ?? "");
  const [therapistId, setTherapistId] = useState(appointment?.therapist_employee_id ?? therapists[0]?.id ?? "");
  const [startsAt, setStartsAt] = useState(appointment ? toDateTimeLocalValue(parseBackendMoment(appointment.starts_at).toISOString()) : defaultSessionStart());
  const [roomId, setRoomId] = useState(appointment?.room_id ?? "");
  const [notes, setNotes] = useState(appointment?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const term = memberQuery.trim();
    if (term.length < 2) { setMemberResults([]); return; }
    let active = true;
    const handle = window.setTimeout(async () => {
      setSearching(true);
      try {
        const response = await fetch(`/api/admin/members?search=${encodeURIComponent(term)}&page_size=6`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (response.ok) {
          const directory = await response.json() as MemberDirectory;
          if (active) setMemberResults(directory.items);
        } else if (active) {
          setMemberResults([]);
        }
      } catch {
        if (active) setMemberResults([]);
      } finally {
        if (active) setSearching(false);
      }
    }, 250);
    return () => { active = false; window.clearTimeout(handle); };
  }, [memberQuery, onUnauthorized]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!moving && !member) { setError("Selecciona al socio que asistirá a la cita."); return; }
    if (!serviceId) { setError("Selecciona un servicio."); return; }
    if (!therapistId) { setError("Selecciona un fisioterapeuta."); return; }
    if (!startsAt) { setError("Indica la fecha y hora de la cita."); return; }
    setBusy(true);
    setError("");
    try {
      let response: Response;
      if (moving && appointment) {
        const patch: Record<string, unknown> = {
          starts_at: fromDateTimeLocalValue(startsAt),
          therapist_employee_id: therapistId,
          notes: notes.trim() || null,
        };
        // Solo toca el consultorio cuando cambió, para no borrar el texto
        // congelado de citas antiguas que nunca tuvieron catálogo.
        if (roomId !== (appointment.room_id ?? "")) patch.room_id = roomId || null;
        response = await fetch(`/api/admin/physio/appointments/${appointment.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
        });
      } else {
        response = await fetch("/api/admin/physio/appointments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            member_id: member?.id,
            service_id: serviceId,
            therapist_employee_id: therapistId,
            starts_at: fromDateTimeLocalValue(startsAt),
            room_id: roomId || null,
            notes: notes.trim() || null,
          }),
        });
      }
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo guardar la cita."); return; }
      onSaved(moving ? "Cita reprogramada." : `Cita agendada para ${member?.first_name ?? "el socio"}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="physio-appointment-title">
        <div className="modal-header"><span className="modal-icon"><Activity size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">{moving ? "MOVER CITA" : "AGENDAR CITA"}</p>
        <h2 id="physio-appointment-title">{moving ? appointment?.member_name : "Nueva cita de fisioterapia"}</h2>
        <p className="modal-subtitle">{moving ? `${appointment?.service_name} · ${formatPhysioDate(appointment?.starts_at ?? "")}` : "Si el socio tiene un paquete vigente para el servicio, la sesión se descuenta al marcar la asistencia; si no, se cobra como sesión suelta."}</p>
        <form onSubmit={submit}>
          {!moving && (
            <div className="class-roster-search">
              {member ? (
                <div className="panel-header access-list-heading">
                  <div className="person-cell"><span className={`person-avatar ${memberAvatarColor(member.id)}`}>{`${member.first_name[0] ?? ""}${member.last_name[0] ?? ""}`.toUpperCase()}</span><span><strong>{member.first_name} {member.last_name}</strong><small>{member.email ?? member.phone ?? "Socio"}</small></span></div>
                  <button type="button" className="text-button" onClick={() => setMember(null)}>Cambiar</button>
                </div>
              ) : (
                <>
                  <label className="form-field"><span>Socio</span><input value={memberQuery} onChange={(event) => setMemberQuery(event.target.value)} placeholder="Buscar por nombre o correo" autoComplete="off" autoFocus /></label>
                  {searching && <p className="manual-hint">Buscando socios…</p>}
                  {memberResults.length > 0 && (
                    <ul className="manual-results">
                      {memberResults.map((item) => (
                        <li key={item.id}>
                          <button type="button" onClick={() => { setMember(item); setMemberQuery(""); setMemberResults([]); }}>
                            <span className="person-cell"><span className={`person-avatar ${memberAvatarColor(item.id)}`}>{`${item.first_name[0] ?? ""}${item.last_name[0] ?? ""}`.toUpperCase()}</span><span><strong>{item.first_name} {item.last_name}</strong><small>{item.email ?? item.phone ?? "Socio"}</small></span></span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </div>
          )}
          <div className="form-row">
            <label className="form-field"><span>Servicio</span><select value={serviceId} onChange={(event) => setServiceId(event.target.value)} disabled={moving}><option value="">Selecciona…</option>{availableServices.map((service) => <option key={service.id} value={service.id}>{service.name} · {service.duration_minutes} min</option>)}</select></label>
            <label className="form-field"><span>Fisioterapeuta</span><select value={therapistId} onChange={(event) => setTherapistId(event.target.value)}><option value="">Selecciona…</option>{therapists.map((therapist) => <option key={therapist.id} value={therapist.id}>{therapist.name} · {therapist.job_title}</option>)}</select></label>
          </div>
          <div className="form-row">
            <label className="form-field"><span>Inicio</span><input type="datetime-local" value={startsAt} onChange={(event) => setStartsAt(event.target.value)} /></label>
            <label className="form-field"><span>Consultorio (opcional)</span><select value={roomId} onChange={(event) => setRoomId(event.target.value)}><option value="">Usar el del fisioterapeuta</option>{availableRooms.map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}</select></label>
          </div>
          <label className="form-field"><span>Notas (opcional)</span><input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Indicaciones, lesión, seguimiento…" maxLength={500} /></label>
          <div className="modal-note"><ShieldCheck size={16} /><span>La agenda evita dos citas a la misma hora con el mismo fisioterapeuta. Si no eliges consultorio se usa el predeterminado del fisioterapeuta. Para cobrar una sesión suelta debe haber un turno de caja abierto al marcar la asistencia.</span></div>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : moving ? "Guardar cambios" : "Agendar cita"}</button></div>
        </form>
      </section>
    </div>
  );
}

function PhysioPackModal({
  initialMember,
  offers,
  onClose,
  onSaved,
  onUnauthorized,
}: {
  initialMember: BackendMember | null;
  offers: BackendPhysioOffer[];
  onClose: () => void;
  onSaved: (message: string) => void;
  onUnauthorized: () => void;
}) {
  const activeOffers = offers.filter((offer) => offer.is_active);
  const [memberQuery, setMemberQuery] = useState("");
  const [memberResults, setMemberResults] = useState<BackendMember[]>([]);
  const [searching, setSearching] = useState(false);
  const [member, setMember] = useState<BackendMember | null>(initialMember);
  const [offerId, setOfferId] = useState(activeOffers[0]?.id ?? "");
  const [paymentMethod, setPaymentMethod] = useState<PhysioPaymentMethod>("cash");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const term = memberQuery.trim();
    if (term.length < 2) { setMemberResults([]); return; }
    let active = true;
    const handle = window.setTimeout(async () => {
      setSearching(true);
      try {
        const response = await fetch(`/api/admin/members?search=${encodeURIComponent(term)}&page_size=6`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (response.ok) {
          const directory = await response.json() as MemberDirectory;
          if (active) setMemberResults(directory.items);
        } else if (active) {
          setMemberResults([]);
        }
      } catch {
        if (active) setMemberResults([]);
      } finally {
        if (active) setSearching(false);
      }
    }, 250);
    return () => { active = false; window.clearTimeout(handle); };
  }, [memberQuery, onUnauthorized]);

  const selectedOffer = activeOffers.find((offer) => offer.id === offerId) ?? null;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!member) { setError("Selecciona al socio que comprará el paquete."); return; }
    if (!offerId) { setError("Selecciona un paquete."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/physio/packs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ member_id: member.id, offer_id: offerId, payment_method: paymentMethod }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo vender el paquete."); return; }
      onSaved(selectedOffer ? `Paquete vendido: ${selectedOffer.name} (${selectedOffer.sessions} sesiones).` : "Paquete vendido.");
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="physio-pack-title">
        <div className="modal-header"><span className="modal-icon"><Package size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">VENDER PAQUETE</p>
        <h2 id="physio-pack-title">Paquete de fisioterapia</h2>
        <p className="modal-subtitle">La venta entra al libro de ventas y a la caja como un servicio. Las sesiones se descuentan al marcar cada asistencia y vencen al terminar la vigencia.</p>
        <form onSubmit={submit}>
          <div className="class-roster-search">
            {member ? (
              <div className="panel-header access-list-heading">
                <div className="person-cell"><span className={`person-avatar ${memberAvatarColor(member.id)}`}>{`${member.first_name[0] ?? ""}${member.last_name[0] ?? ""}`.toUpperCase()}</span><span><strong>{member.first_name} {member.last_name}</strong><small>{member.email ?? member.phone ?? "Socio"}</small></span></div>
                <button type="button" className="text-button" onClick={() => setMember(null)}>Cambiar</button>
              </div>
            ) : (
              <>
                <label className="form-field"><span>Socio</span><input value={memberQuery} onChange={(event) => setMemberQuery(event.target.value)} placeholder="Buscar por nombre o correo" autoComplete="off" autoFocus /></label>
                {searching && <p className="manual-hint">Buscando socios…</p>}
                {memberResults.length > 0 && (
                  <ul className="manual-results">
                    {memberResults.map((item) => (
                      <li key={item.id}>
                        <button type="button" onClick={() => { setMember(item); setMemberQuery(""); setMemberResults([]); }}>
                          <span className="person-cell"><span className={`person-avatar ${memberAvatarColor(item.id)}`}>{`${item.first_name[0] ?? ""}${item.last_name[0] ?? ""}`.toUpperCase()}</span><span><strong>{item.first_name} {item.last_name}</strong><small>{item.email ?? item.phone ?? "Socio"}</small></span></span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
          <label className="form-field"><span>Paquete</span><select value={offerId} onChange={(event) => setOfferId(event.target.value)}><option value="">Selecciona…</option>{activeOffers.map((offer) => <option key={offer.id} value={offer.id}>{offer.name} · {offer.sessions} sesiones · {formatMoney(offer.price_cents)}</option>)}</select></label>
          <label className="form-field"><span>Forma de pago</span><select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value as PhysioPaymentMethod)}><option value="cash">Efectivo</option><option value="card">Tarjeta</option><option value="transfer">Transferencia</option><option value="account">Cuenta del socio</option></select></label>
          {selectedOffer && (
            <div className="modal-note">
              <ShieldCheck size={16} />
              <span>{selectedOffer.service_name} · {selectedOffer.sessions} sesiones · vigencia {selectedOffer.validity_days} días · {formatMoney(selectedOffer.price_cents)}{selectedOffer.savings_cents > 0 ? ` (ahorro ${formatMoney(selectedOffer.savings_cents)})` : ""}. El pago en efectivo requiere un turno de caja abierto.</span>
            </div>
          )}
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Vendiendo…" : "Vender paquete"}</button></div>
        </form>
      </section>
    </div>
  );
}

function PhysioServiceModal({ service, onClose, onSaved, onUnauthorized }: { service: BackendPhysioService | null; onClose: () => void; onSaved: (message: string) => void; onUnauthorized: () => void }) {
  const editing = service !== null;
  const [code, setCode] = useState(service?.code ?? "");
  const [name, setName] = useState(service?.name ?? "");
  const [description, setDescription] = useState(service?.description ?? "");
  const [duration, setDuration] = useState(String(service?.duration_minutes ?? 45));
  const [price, setPrice] = useState(service ? (service.price_cents / 100).toFixed(2) : "");
  const [active, setActive] = useState(service?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!code.trim()) { setError("El código es obligatorio."); return; }
    if (!name.trim()) { setError("El nombre es obligatorio."); return; }
    const durationValue = Number.parseInt(duration, 10);
    if (!Number.isFinite(durationValue) || durationValue <= 0) { setError("Indica una duración válida en minutos."); return; }
    const priceCents = parseMoneyToCents(price);
    if (priceCents === null) { setError("El precio no es válido."); return; }
    const body = {
      code: code.trim(),
      name: name.trim(),
      description: description.trim() || null,
      duration_minutes: durationValue,
      price_cents: priceCents,
      is_active: active,
    };
    setBusy(true);
    setError("");
    try {
      const response = editing && service
        ? await fetch(`/api/admin/physio/services/${service.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        : await fetch("/api/admin/physio/services", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo guardar el servicio."); return; }
      onSaved(editing ? "Servicio actualizado." : `Servicio creado: ${name.trim()}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="physio-service-title">
        <div className="modal-header"><span className="modal-icon"><Activity size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">CATÁLOGO DE FISIOTERAPIA</p>
        <h2 id="physio-service-title">{editing ? service?.name : "Nuevo servicio"}</h2>
        <p className="modal-subtitle">La duración define el fin de cada cita en la agenda; el precio es el de una sesión suelta.</p>
        <form onSubmit={submit}>
          <div className="form-row">
            <label className="form-field"><span>Código</span><input value={code} onChange={(event) => setCode(event.target.value)} placeholder="Ej. DESC" maxLength={40} autoFocus /></label>
            <label className="form-field"><span>Duración (minutos)</span><input value={duration} onChange={(event) => setDuration(event.target.value)} inputMode="numeric" /></label>
          </div>
          <label className="form-field"><span>Nombre</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Ej. Descarga muscular" maxLength={160} /></label>
          <label className="form-field"><span>Descripción (opcional)</span><input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Técnica, indicaciones…" maxLength={400} /></label>
          <label className="form-field"><span>Precio por sesión</span><input value={price} onChange={(event) => setPrice(event.target.value)} placeholder="0.00" inputMode="decimal" /></label>
          <label className="form-field form-check"><span><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />Servicio activo para agendar y vender</span></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : editing ? "Guardar cambios" : "Crear servicio"}</button></div>
        </form>
      </section>
    </div>
  );
}

function PhysioOfferModal({ offer, services, onClose, onSaved, onUnauthorized }: { offer: BackendPhysioOffer | null; services: BackendPhysioService[]; onClose: () => void; onSaved: (message: string) => void; onUnauthorized: () => void }) {
  const editing = offer !== null;
  const activeServices = services.filter((service) => service.is_active || service.id === offer?.service_id);
  const [serviceId, setServiceId] = useState(offer?.service_id ?? activeServices[0]?.id ?? "");
  const [name, setName] = useState(offer?.name ?? "");
  const [sessions, setSessions] = useState(String(offer?.sessions ?? 4));
  const [price, setPrice] = useState(offer ? (offer.price_cents / 100).toFixed(2) : "");
  const [validity, setValidity] = useState(String(offer?.validity_days ?? 31));
  const [active, setActive] = useState(offer?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selectedService = activeServices.find((service) => service.id === serviceId) ?? null;
  const sessionsValue = Number.parseInt(sessions, 10);
  const listPriceCents = selectedService && Number.isFinite(sessionsValue) && sessionsValue > 0 ? selectedService.price_cents * sessionsValue : null;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editing && !serviceId) { setError("Selecciona el servicio del paquete."); return; }
    if (!name.trim()) { setError("El nombre del paquete es obligatorio."); return; }
    if (!Number.isFinite(sessionsValue) || sessionsValue < 1) { setError("Indica cuántas sesiones incluye el paquete."); return; }
    const priceCents = parseMoneyToCents(price);
    if (priceCents === null) { setError("El precio del paquete no es válido."); return; }
    const validityValue = Number.parseInt(validity, 10);
    if (!Number.isFinite(validityValue) || validityValue < 1) { setError("Indica una vigencia válida en días."); return; }
    if (listPriceCents !== null && priceCents > listPriceCents) { setError(`El precio no puede superar la suma de las sesiones sueltas (${formatMoney(listPriceCents)}).`); return; }
    const body = { name: name.trim(), sessions: sessionsValue, price_cents: priceCents, validity_days: validityValue, is_active: active };
    setBusy(true);
    setError("");
    try {
      const response = editing && offer
        ? await fetch(`/api/admin/physio/offers/${offer.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        : await fetch("/api/admin/physio/offers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...body, service_id: serviceId }) });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo guardar el paquete."); return; }
      onSaved(editing ? "Paquete actualizado." : `Paquete creado: ${name.trim()}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="physio-offer-title">
        <div className="modal-header"><span className="modal-icon"><Package size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">CATÁLOGO DE FISIOTERAPIA</p>
        <h2 id="physio-offer-title">{editing ? offer?.name : "Nuevo paquete"}</h2>
        <p className="modal-subtitle">El paquete se vende una sola vez y queda prepagado. El precio de lista usa el precio actual del servicio por el número de sesiones.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Servicio</span><select value={serviceId} onChange={(event) => setServiceId(event.target.value)} disabled={editing}><option value="">Selecciona…</option>{activeServices.map((service) => <option key={service.id} value={service.id}>{service.name}</option>)}</select></label>
          <label className="form-field"><span>Nombre del paquete</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Ej. Paquete de 4 descargas" maxLength={160} autoFocus /></label>
          <div className="form-row">
            <label className="form-field"><span>Sesiones incluidas</span><input value={sessions} onChange={(event) => setSessions(event.target.value)} inputMode="numeric" /></label>
            <label className="form-field"><span>Vigencia (días)</span><input value={validity} onChange={(event) => setValidity(event.target.value)} inputMode="numeric" /></label>
          </div>
          <label className="form-field"><span>Precio del paquete</span><input value={price} onChange={(event) => setPrice(event.target.value)} placeholder="0.00" inputMode="decimal" /></label>
          {listPriceCents !== null && <div className="modal-note"><ShieldCheck size={16} /><span>Precio de lista: {formatMoney(listPriceCents)} por {sessionsValue} sesión(es) sueltas. Un precio menor se muestra como ahorro en la venta.</span></div>}
          <label className="form-field form-check"><span><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />Paquete activo para vender</span></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : editing ? "Guardar cambios" : "Crear paquete"}</button></div>
        </form>
      </section>
    </div>
  );
}

function RoutinesView({ permissions, onUnauthorized, onToast, onNotificationsChanged }: { permissions: string[]; onUnauthorized: () => void; onToast: (message: string) => void; onNotificationsChanged: () => void }) {
  const canManage = permissions.includes("routines.manage");

  const [tab, setTab] = useState<"seguimiento" | "rutinas" | "ejercicios">("seguimiento");
  const [overview, setOverview] = useState<RoutinesOverview | null>(null);
  const [refresh, setRefresh] = useState(0);
  const reload = () => setRefresh((value) => value + 1);

  const [assignmentDirectory, setAssignmentDirectory] = useState<AssignmentDirectory | null>(null);
  const [assignmentSearch, setAssignmentSearch] = useState("");
  const [assignmentQuery, setAssignmentQuery] = useState("");
  const [assignmentStatus, setAssignmentStatus] = useState<"" | AssignmentState>("");
  const [assignmentPage, setAssignmentPage] = useState(1);
  const [assignmentLoading, setAssignmentLoading] = useState(false);
  const [assignmentError, setAssignmentError] = useState("");

  const [routineDirectory, setRoutineDirectory] = useState<RoutineDirectory | null>(null);
  const [routineSearch, setRoutineSearch] = useState("");
  const [routineQuery, setRoutineQuery] = useState("");
  const [routineStatus, setRoutineStatus] = useState<"" | RoutineState>("");
  const [routinePage, setRoutinePage] = useState(1);
  const [routineLoading, setRoutineLoading] = useState(false);
  const [routineError, setRoutineError] = useState("");

  const [exerciseDirectory, setExerciseDirectory] = useState<ExerciseDirectory | null>(null);
  const [exerciseSearch, setExerciseSearch] = useState("");
  const [exerciseQuery, setExerciseQuery] = useState("");
  const [exerciseMuscle, setExerciseMuscle] = useState("");
  const [exerciseCategory, setExerciseCategory] = useState("");
  const [exercisePage, setExercisePage] = useState(1);
  const [exerciseLoading, setExerciseLoading] = useState(false);
  const [exerciseError, setExerciseError] = useState("");

  const [exerciseOptions, setExerciseOptions] = useState<BackendExercise[]>([]);
  const [equipmentChoices, setEquipmentChoices] = useState<EquipmentChoice[]>([]);
  const [instructors, setInstructors] = useState<BackendInstructor[]>([]);
  const [members, setMembers] = useState<BackendMember[]>([]);

  const [exerciseModal, setExerciseModal] = useState<{ exercise: BackendExercise | null } | null>(null);
  const [routineModalOpen, setRoutineModalOpen] = useState(false);
  const [routineDetailId, setRoutineDetailId] = useState<string | null>(null);
  const [assignmentModalOpen, setAssignmentModalOpen] = useState(false);
  const [assignmentDetailId, setAssignmentDetailId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch("/api/admin/routines/overview", { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (response.ok && active) setOverview(await response.json() as RoutinesOverview);
      } catch {
        // The summary band is decorative: a failure leaves the previous values.
      }
    };
    void load();
    return () => { active = false; };
  }, [refresh, onUnauthorized]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [exercisesResponse, instructorsResponse, membersResponse, equipmentResponse] = await Promise.all([
          fetch("/api/admin/routines/exercises?page=1&page_size=100&include_inactive=false", { cache: "no-store" }),
          fetch("/api/admin/classes/instructors", { cache: "no-store" }),
          fetch("/api/admin/members?page=1&page_size=100", { cache: "no-store" }),
          fetch("/api/admin/maintenance/equipment/options", { cache: "no-store" }),
        ]);
        if ([exercisesResponse, instructorsResponse, membersResponse, equipmentResponse].some((response) => response.status === 401)) {
          onUnauthorized();
          return;
        }
        if (!active) return;
        if (exercisesResponse.ok) setExerciseOptions((await exercisesResponse.json() as ExerciseDirectory).items);
        if (instructorsResponse.ok) setInstructors(await instructorsResponse.json() as BackendInstructor[]);
        if (membersResponse.ok) setMembers((await membersResponse.json() as MemberDirectory).items);
        if (equipmentResponse.ok) setEquipmentChoices(await equipmentResponse.json() as EquipmentChoice[]);
      } catch {
        // The selects only feed the forms; a failure leaves them empty.
      }
    };
    void load();
    return () => { active = false; };
  }, [refresh, onUnauthorized]);

  useEffect(() => {
    const handle = window.setTimeout(() => { setAssignmentQuery(assignmentSearch.trim()); setAssignmentPage(1); }, 250);
    return () => window.clearTimeout(handle);
  }, [assignmentSearch]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setAssignmentLoading(true);
      setAssignmentError("");
      const params = new URLSearchParams({ page: String(assignmentPage), page_size: String(ASSIGNMENTS_PAGE_SIZE) });
      if (assignmentQuery) params.set("search", assignmentQuery);
      if (assignmentStatus) params.set("status", assignmentStatus);
      try {
        const response = await fetch(`/api/admin/routines/assignments?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        if (active) setAssignmentDirectory(await response.json() as AssignmentDirectory);
      } catch {
        if (active) setAssignmentError("No se pudo cargar el seguimiento de rutinas.");
      } finally {
        if (active) setAssignmentLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [assignmentPage, assignmentQuery, assignmentStatus, refresh, onUnauthorized]);

  useEffect(() => {
    const handle = window.setTimeout(() => { setRoutineQuery(routineSearch.trim()); setRoutinePage(1); }, 250);
    return () => window.clearTimeout(handle);
  }, [routineSearch]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setRoutineLoading(true);
      setRoutineError("");
      const params = new URLSearchParams({ page: String(routinePage), page_size: String(ROUTINES_PAGE_SIZE) });
      if (routineQuery) params.set("search", routineQuery);
      if (routineStatus) params.set("status", routineStatus);
      try {
        const response = await fetch(`/api/admin/routines?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        if (active) setRoutineDirectory(await response.json() as RoutineDirectory);
      } catch {
        if (active) setRoutineError("No se pudo cargar el catálogo de rutinas.");
      } finally {
        if (active) setRoutineLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [routinePage, routineQuery, routineStatus, refresh, onUnauthorized]);

  useEffect(() => {
    const handle = window.setTimeout(() => { setExerciseQuery(exerciseSearch.trim()); setExercisePage(1); }, 250);
    return () => window.clearTimeout(handle);
  }, [exerciseSearch]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setExerciseLoading(true);
      setExerciseError("");
      const params = new URLSearchParams({ page: String(exercisePage), page_size: String(ROUTINES_PAGE_SIZE), include_inactive: "true" });
      if (exerciseQuery) params.set("search", exerciseQuery);
      if (exerciseMuscle) params.set("muscle_group", exerciseMuscle);
      if (exerciseCategory) params.set("category", exerciseCategory);
      try {
        const response = await fetch(`/api/admin/routines/exercises?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        if (active) setExerciseDirectory(await response.json() as ExerciseDirectory);
      } catch {
        if (active) setExerciseError("No se pudo cargar la biblioteca de ejercicios.");
      } finally {
        if (active) setExerciseLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [exercisePage, exerciseQuery, exerciseMuscle, exerciseCategory, refresh, onUnauthorized]);

  const archiveRoutine = async (routine: BackendRoutine) => {
    try {
      const response = await fetch(`/api/admin/routines/${routine.id}/archive`, { method: "POST" });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo archivar la rutina."); return; }
      reload();
      onToast(`Rutina archivada: ${routine.name}.`);
    } catch {
      onToast("No se pudo conectar con el backend.");
    }
  };

  const tabButton = (value: "seguimiento" | "rutinas" | "ejercicios", label: string) => (
    <button type="button" className={tab === value ? "staff-tab-active" : ""} onClick={() => setTab(value)}>{label}</button>
  );

  const assignmentSummary = assignmentDirectory?.summary ?? { total: 0, active: 0, completed: 0, cancelled: 0 };
  const assignmentItems = assignmentDirectory?.items ?? [];
  const routineSummary = routineDirectory?.summary ?? { total: 0, active: 0, draft: 0, archived: 0 };
  const routineItems = routineDirectory?.items ?? [];
  const exerciseItems = exerciseDirectory?.items ?? [];

  return (
    <>
      <section className="access-summary-band pos-cash-band">
        <div className="access-summary-main">
          <span className="summary-icon"><Dumbbell size={18} /></span>
          <div>
            <span>RUTINAS Y PROGRESO</span>
            <strong>{overview ? `${overview.routines_active} rutinas activas` : "Consultando…"}</strong>
          </div>
        </div>
        <div className="summary-divider" />
        <div className="summary-stat"><span>ASIGNACIONES</span><strong>{overview?.assignments_active ?? "—"}</strong></div>
        <div className="summary-stat"><span>EJERCICIOS</span><strong>{overview?.exercises ?? "—"}</strong></div>
        <div className="summary-stat"><span>ENTRENOS (7 DÍAS)</span><strong>{overview?.workouts_last_7_days ?? "—"}</strong></div>
        {canManage && <button className="button button-primary" onClick={() => setAssignmentModalOpen(true)}><Plus size={16} />Asignar rutina</button>}
      </section>

      <div className="staff-tabs pos-tabs">
        {tabButton("seguimiento", "Seguimiento")}
        {tabButton("rutinas", "Rutinas")}
        {tabButton("ejercicios", "Ejercicios")}
        <span className="staff-tabs-note"><ShieldCheck size={14} />Cada asignación conserva la versión de la rutina que se le entregó</span>
      </div>

      {tab === "seguimiento" && (
        <section className="panel full-panel">
          <div className="panel-header access-list-heading">
            <div><p className="section-kicker">ENTRENAMIENTO</p><h2>Seguimiento de socios</h2></div>
            {canManage && <button className="button button-primary" onClick={() => setAssignmentModalOpen(true)}><Plus size={17} />Asignar rutina</button>}
          </div>
          <div className="table-toolbar">
            <label className="table-search"><Search size={17} /><input value={assignmentSearch} onChange={(event) => setAssignmentSearch(event.target.value)} placeholder="Buscar por socio o rutina" /></label>
            <label className="table-select"><span>Estado</span><select value={assignmentStatus} onChange={(event) => { setAssignmentStatus(event.target.value as "" | AssignmentState); setAssignmentPage(1); }}><option value="">Todas</option><option value="active">Activas</option><option value="completed">Completadas</option><option value="cancelled">Canceladas</option></select></label>
            {assignmentQuery || assignmentStatus ? <button className="button button-secondary" onClick={() => { setAssignmentSearch(""); setAssignmentStatus(""); setAssignmentPage(1); }}>Limpiar filtros</button> : <span className="table-hint">Abre una asignación para registrar entrenos y medidas</span>}
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>SOCIO</th><th>RUTINA</th><th>VERSIÓN</th><th>FRECUENCIA</th><th>ENTRENOS</th><th>ÚLTIMO</th><th>ESTADO</th><th /></tr></thead>
              <tbody>
                {assignmentLoading ? <tr><td colSpan={8} className="empty-row">Cargando asignaciones…</td></tr>
                  : assignmentError ? <tr><td colSpan={8} className="empty-row">{assignmentError}</td></tr>
                  : assignmentItems.length === 0 ? <tr><td colSpan={8} className="empty-row">{assignmentQuery || assignmentStatus ? "No hay asignaciones que coincidan con el filtro." : "Aún no hay rutinas asignadas."}</td></tr>
                  : assignmentItems.map((assignment) => (
                    <tr key={assignment.id}>
                      <td><div className="person-cell"><span className="pos-row-icon"><Users size={15} /></span><span><strong>{assignment.member_name}</strong><small>{assignment.member_email ?? "Sin correo"}</small></span></div></td>
                      <td>{assignment.routine_name}</td>
                      <td>v{assignment.routine_version}</td>
                      <td>{assignment.frequency_per_week ? `${assignment.frequency_per_week}×/sem` : "—"}</td>
                      <td>{assignment.workouts_logged}</td>
                      <td>{formatDateOnly(assignment.last_workout_at)}</td>
                      <td><span className={`status-badge ${assignmentStatusBadges[assignment.status]}`}><i />{assignmentStatusLabels[assignment.status]}</span></td>
                      <td><div className="pos-row-actions"><button type="button" className="text-button" onClick={() => setAssignmentDetailId(assignment.id)}>Abrir</button></div></td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <div className="table-bottom">
            <span>{assignmentSummary.total} asignaciones · {assignmentSummary.active} activas</span>
            {(assignmentDirectory?.pages ?? 0) > 1 && (
              <span className="member-pagination">
                <span>Página {assignmentDirectory?.page ?? 1} de {assignmentDirectory?.pages ?? 1}</span>
                <button type="button" aria-label="Página anterior" disabled={assignmentPage <= 1} onClick={() => setAssignmentPage((value) => Math.max(value - 1, 1))}>‹</button>
                <button type="button" aria-label="Página siguiente" disabled={assignmentPage >= (assignmentDirectory?.pages ?? 1)} onClick={() => setAssignmentPage((value) => value + 1)}>›</button>
              </span>
            )}
          </div>
        </section>
      )}

      {tab === "rutinas" && (
        <section className="panel full-panel">
          <div className="panel-header access-list-heading">
            <div><p className="section-kicker">CATÁLOGO</p><h2>Rutinas</h2></div>
            {canManage && <button className="button button-primary" onClick={() => setRoutineModalOpen(true)}><Plus size={17} />Nueva rutina</button>}
          </div>
          <div className="table-toolbar">
            <label className="table-search"><Search size={17} /><input value={routineSearch} onChange={(event) => setRoutineSearch(event.target.value)} placeholder="Buscar por nombre" /></label>
            <label className="table-select"><span>Estado</span><select value={routineStatus} onChange={(event) => { setRoutineStatus(event.target.value as "" | RoutineState); setRoutinePage(1); }}><option value="">Todas</option><option value="active">Activas</option><option value="draft">Borradores</option><option value="archived">Archivadas</option></select></label>
            {routineQuery || routineStatus ? <button className="button button-secondary" onClick={() => { setRoutineSearch(""); setRoutineStatus(""); setRoutinePage(1); }}>Limpiar filtros</button> : <span className="table-hint">{routineSummary.active} activas · {routineSummary.archived} archivadas</span>}
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>RUTINA</th><th>ENTRENADOR</th><th>VERSIÓN</th><th>EJERCICIOS</th><th>ASIGNACIONES</th><th>ESTADO</th><th /></tr></thead>
              <tbody>
                {routineLoading ? <tr><td colSpan={7} className="empty-row">Cargando rutinas…</td></tr>
                  : routineError ? <tr><td colSpan={7} className="empty-row">{routineError}</td></tr>
                  : routineItems.length === 0 ? <tr><td colSpan={7} className="empty-row">{routineQuery || routineStatus ? "No hay rutinas que coincidan con el filtro." : "Aún no hay rutinas en el catálogo."}</td></tr>
                  : routineItems.map((routine) => (
                    <tr key={routine.id}>
                      <td><div className="person-cell"><span className="pos-row-icon"><Dumbbell size={15} /></span><span><strong>{routine.name}</strong><small>{routine.objective ?? "Sin objetivo"}</small></span></div></td>
                      <td>{routine.trainer_name ?? "Por asignar"}</td>
                      <td>v{routine.version}</td>
                      <td>{routine.item_count}</td>
                      <td>{routine.active_assignments}</td>
                      <td><span className={`status-badge ${routineStatusBadges[routine.status]}`}><i />{routineStatusLabels[routine.status]}</span></td>
                      <td><div className="pos-row-actions">
                        <button type="button" className="text-button" onClick={() => setRoutineDetailId(routine.id)}>Abrir</button>
                        {canManage && routine.status !== "archived" && <button type="button" className="text-button" onClick={() => archiveRoutine(routine)}>Archivar</button>}
                      </div></td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <div className="table-bottom">
            <span>{routineSummary.total} rutinas en el catálogo</span>
            {(routineDirectory?.pages ?? 0) > 1 && (
              <span className="member-pagination">
                <span>Página {routineDirectory?.page ?? 1} de {routineDirectory?.pages ?? 1}</span>
                <button type="button" aria-label="Página anterior" disabled={routinePage <= 1} onClick={() => setRoutinePage((value) => Math.max(value - 1, 1))}>‹</button>
                <button type="button" aria-label="Página siguiente" disabled={routinePage >= (routineDirectory?.pages ?? 1)} onClick={() => setRoutinePage((value) => value + 1)}>›</button>
              </span>
            )}
          </div>
        </section>
      )}

      {tab === "ejercicios" && (
        <section className="panel full-panel">
          <div className="panel-header access-list-heading">
            <div><p className="section-kicker">BIBLIOTECA</p><h2>Ejercicios</h2></div>
            {canManage && <button className="button button-primary" onClick={() => setExerciseModal({ exercise: null })}><Plus size={17} />Nuevo ejercicio</button>}
          </div>
          <div className="table-toolbar">
            <label className="table-search"><Search size={17} /><input value={exerciseSearch} onChange={(event) => setExerciseSearch(event.target.value)} placeholder="Buscar por nombre" /></label>
            <label className="table-select"><span>Grupo</span><select value={exerciseMuscle} onChange={(event) => { setExerciseMuscle(event.target.value); setExercisePage(1); }}><option value="">Todos</option>{(exerciseDirectory?.muscle_groups ?? []).map((group) => <option key={group} value={group}>{group}</option>)}</select></label>
            <label className="table-select"><span>Categoría</span><select value={exerciseCategory} onChange={(event) => { setExerciseCategory(event.target.value); setExercisePage(1); }}><option value="">Todas</option>{(exerciseDirectory?.categories ?? []).map((category) => <option key={category} value={category}>{category}</option>)}</select></label>
            {exerciseQuery || exerciseMuscle || exerciseCategory ? <button className="button button-secondary" onClick={() => { setExerciseSearch(""); setExerciseMuscle(""); setExerciseCategory(""); setExercisePage(1); }}>Limpiar filtros</button> : <span className="table-hint">Vincula un ejercicio a su máquina para ver cuándo entra en mantenimiento</span>}
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>EJERCICIO</th><th>GRUPO</th><th>CATEGORÍA</th><th>EQUIPO</th><th>ESTADO</th><th /></tr></thead>
              <tbody>
                {exerciseLoading ? <tr><td colSpan={6} className="empty-row">Cargando ejercicios…</td></tr>
                  : exerciseError ? <tr><td colSpan={6} className="empty-row">{exerciseError}</td></tr>
                  : exerciseItems.length === 0 ? <tr><td colSpan={6} className="empty-row">{exerciseQuery || exerciseMuscle || exerciseCategory ? "No hay ejercicios que coincidan con el filtro." : "Aún no hay ejercicios en la biblioteca."}</td></tr>
                  : exerciseItems.map((exercise) => (
                    <tr key={exercise.id}>
                      <td><div className="person-cell"><span className="pos-row-icon"><Activity size={15} /></span><span><strong>{exercise.name}</strong><small>{exercise.description ?? "Sin descripción"}</small></span></div></td>
                      <td>{exercise.muscle_group}</td>
                      <td>{exercise.category}</td>
                      <td>
                        {exercise.equipment_name ?? "—"}
                        {exercise.equipment_status && (
                          <span className={`status-badge ${equipmentStatusBadges[exercise.equipment_status]}`} style={{ marginLeft: 8 }}><i />{equipmentStatusLabels[exercise.equipment_status]}</span>
                        )}
                      </td>
                      <td><span className={`status-badge ${exercise.is_active ? "status-good" : "status-neutral"}`}><i />{exercise.is_active ? "Disponible" : "Inactivo"}</span></td>
                      <td><div className="pos-row-actions">{canManage && <button type="button" className="text-button" onClick={() => setExerciseModal({ exercise })}>Editar</button>}</div></td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <div className="table-bottom"><span>{exerciseDirectory?.total ?? 0} ejercicios en la biblioteca</span></div>
        </section>
      )}

      {exerciseModal && <ExerciseFormModal exercise={exerciseModal.exercise} equipment={equipmentChoices} onClose={() => setExerciseModal(null)} onSaved={(message) => { setExerciseModal(null); reload(); onToast(message); }} onUnauthorized={onUnauthorized} />}

      {routineModalOpen && <RoutineFormModal exercises={exerciseOptions} instructors={instructors} onClose={() => setRoutineModalOpen(false)} onSaved={(message) => { setRoutineModalOpen(false); reload(); onToast(message); }} onUnauthorized={onUnauthorized} />}

      {routineDetailId && <RoutineDetailModal routineId={routineDetailId} exercises={exerciseOptions} canManage={canManage} onClose={() => setRoutineDetailId(null)} onChanged={() => reload()} onToast={onToast} onUnauthorized={onUnauthorized} />}

      {assignmentModalOpen && <AssignmentFormModal routines={routineItems} members={members} instructors={instructors} onClose={() => setAssignmentModalOpen(false)} onSaved={(message) => { setAssignmentModalOpen(false); reload(); onToast(message); }} onUnauthorized={onUnauthorized} />}

      {assignmentDetailId && <AssignmentDetailModal assignmentId={assignmentDetailId} canManage={canManage} onClose={() => setAssignmentDetailId(null)} onChanged={() => reload()} onReviewed={onNotificationsChanged} onToast={onToast} onUnauthorized={onUnauthorized} />}
    </>
  );
}

function ExerciseFormModal({ exercise, equipment, onClose, onSaved, onUnauthorized }: { exercise: BackendExercise | null; equipment: EquipmentChoice[]; onClose: () => void; onSaved: (message: string) => void; onUnauthorized: () => void }) {
  const [name, setName] = useState(exercise?.name ?? "");
  const [muscleGroup, setMuscleGroup] = useState(exercise?.muscle_group ?? "");
  const [category, setCategory] = useState(exercise?.category ?? "");
  const [equipmentName, setEquipmentName] = useState(exercise?.equipment_name ?? "");
  const [equipmentId, setEquipmentId] = useState(exercise?.equipment_id ?? "");
  const [description, setDescription] = useState(exercise?.description ?? "");
  const [videoUrl, setVideoUrl] = useState(exercise?.video_url ?? "");
  const [isActive, setIsActive] = useState(exercise?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim() || !muscleGroup.trim() || !category.trim()) { setError("Nombre, grupo muscular y categoría son obligatorios."); return; }
    setBusy(true);
    setError("");
    const body: Record<string, unknown> = {
      name: name.trim(),
      muscle_group: muscleGroup.trim(),
      category: category.trim(),
      equipment_name: equipmentName.trim() || null,
      equipment_id: equipmentId || null,
      description: description.trim() || null,
      video_url: videoUrl.trim() || null,
    };
    if (exercise) body.is_active = isActive;
    try {
      const response = await fetch(exercise ? `/api/admin/routines/exercises/${exercise.id}` : "/api/admin/routines/exercises", {
        method: exercise ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo guardar el ejercicio."); return; }
      onSaved(exercise ? `Ejercicio actualizado: ${name.trim()}.` : `Ejercicio creado: ${name.trim()}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="exercise-modal-title">
        <div className="modal-header"><span className="modal-icon"><Activity size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">BIBLIOTECA DE EJERCICIOS</p>
        <h2 id="exercise-modal-title">{exercise ? "Editar ejercicio" : "Nuevo ejercicio"}</h2>
        <p className="modal-subtitle">Vincula el ejercicio a su máquina para ver el aviso cuando el equipo entre en mantenimiento o quede fuera de servicio.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Nombre</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Ej. Sentadilla con barra" maxLength={160} autoFocus /></label>
          <div className="form-grid">
            <label className="form-field"><span>Grupo muscular</span><input value={muscleGroup} onChange={(event) => setMuscleGroup(event.target.value)} placeholder="Piernas" maxLength={60} /></label>
            <label className="form-field"><span>Categoría</span><input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="Fuerza" maxLength={60} /></label>
          </div>
          <div className="form-grid">
            <label className="form-field"><span>Equipo vinculado</span><select value={equipmentId} onChange={(event) => setEquipmentId(event.target.value)}><option value="">Sin vincular</option>{equipment.map((choice) => <option key={choice.id} value={choice.id}>{choice.name}{choice.location ? ` · ${choice.location}` : ""}</option>)}</select></label>
            <label className="form-field"><span>Equipo (texto libre)</span><input value={equipmentName} onChange={(event) => setEquipmentName(event.target.value)} placeholder="Opcional" maxLength={120} /></label>
          </div>
          <label className="form-field"><span>Descripción</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={2} placeholder="Opcional" /></label>
          <label className="form-field"><span>Video</span><input value={videoUrl} onChange={(event) => setVideoUrl(event.target.value)} placeholder="Opcional" maxLength={300} /></label>
          {exercise && <label className="form-check"><input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} /><span>Disponible para nuevas rutinas</span></label>}
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : exercise ? "Guardar cambios" : "Crear ejercicio"}</button></div>
        </form>
      </section>
    </div>
  );
}

function RoutineFormModal({ exercises, instructors, onClose, onSaved, onUnauthorized }: { exercises: BackendExercise[]; instructors: BackendInstructor[]; onClose: () => void; onSaved: (message: string) => void; onUnauthorized: () => void }) {
  const [name, setName] = useState("");
  const [trainerId, setTrainerId] = useState("");
  const [objective, setObjective] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([newLineDraft()]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim()) { setError("El nombre es obligatorio."); return; }
    const items = lines.map(lineDraftPayload);
    if (items.some((item) => !item.exercise_id || !item.reps || item.sets < 1)) { setError("Cada línea necesita ejercicio, series válidas y repeticiones."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/routines", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          trainer_id: trainerId || null,
          objective: objective.trim() || null,
          notes: notes.trim() || null,
          items,
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo crear la rutina."); return; }
      onSaved(`Rutina creada: ${name.trim()}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="routine-modal-title">
        <div className="modal-header"><span className="modal-icon"><Dumbbell size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">CATÁLOGO DE RUTINAS</p>
        <h2 id="routine-modal-title">Nueva rutina</h2>
        <p className="modal-subtitle">La rutina es una plantilla reutilizable: se puede asignar a varios socios y cada asignación fija esta versión.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Nombre</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Ej. Fuerza Full Body" maxLength={160} autoFocus /></label>
          <div className="form-grid">
            <label className="form-field"><span>Entrenador</span><select value={trainerId} onChange={(event) => setTrainerId(event.target.value)}><option value="">Por asignar</option>{instructors.map((instructor) => <option key={instructor.id} value={instructor.id}>{instructor.name}</option>)}</select></label>
            <label className="form-field"><span>Objetivo</span><input value={objective} onChange={(event) => setObjective(event.target.value)} placeholder="Opcional" maxLength={200} /></label>
          </div>
          <label className="form-field"><span>Notas</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={2} placeholder="Opcional" /></label>
          <p className="form-section-label">Ejercicios del plan</p>
          <RoutineLineEditor exercises={exercises} lines={lines} disabled={busy} onChange={setLines} />
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : "Crear rutina"}</button></div>
        </form>
      </section>
    </div>
  );
}

function RoutineDetailModal({ routineId, exercises, canManage, onClose, onChanged, onToast, onUnauthorized }: { routineId: string; exercises: BackendExercise[]; canManage: boolean; onClose: () => void; onChanged: () => void; onToast: (message: string) => void; onUnauthorized: () => void }) {
  const [detail, setDetail] = useState<RoutineDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [editing, setEditing] = useState(false);
  const [lines, setLines] = useState<LineDraft[]>([]);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`/api/admin/routines/${routineId}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        if (!active) return;
        const data = await response.json() as RoutineDetail;
        setDetail(data);
        setLines(data.items.map((item) => ({ key: `${item.id}`, exercise_id: item.exercise_id, sets: String(item.sets), reps: item.reps, rest_seconds: item.rest_seconds === null ? "" : String(item.rest_seconds), load_note: item.load_note ?? "", notes: item.notes ?? "" })));
      } catch {
        if (active) setError("No se pudo cargar la rutina.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [routineId, refresh, onUnauthorized]);

  const publish = async () => {
    if (!detail) return;
    const items = lines.map(lineDraftPayload);
    if (items.some((item) => !item.exercise_id || !item.reps || item.sets < 1)) { onToast("Cada línea necesita ejercicio, series válidas y repeticiones."); return; }
    setBusy(true);
    try {
      const response = await fetch(`/api/admin/routines/${routineId}/items`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items, reason: reason.trim() || null }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo publicar la nueva versión."); return; }
      setEditing(false);
      setReason("");
      setRefresh((value) => value + 1);
      onChanged();
      onToast(`Nueva versión publicada (v${(payload as RoutineDetail).routine?.version ?? ""}).`);
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const archive = async () => {
    try {
      const response = await fetch(`/api/admin/routines/${routineId}/archive`, { method: "POST" });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo archivar la rutina."); return; }
      setRefresh((value) => value + 1);
      onChanged();
      onToast("Rutina archivada.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="routine-detail-title">
        <div className="modal-header"><span className="modal-icon"><Dumbbell size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">RUTINA</p>
        <h2 id="routine-detail-title">{detail?.routine.name ?? "Cargando…"}</h2>
        {detail && (
          <p className="modal-subtitle">
            {routineStatusLabels[detail.routine.status]} · v{detail.routine.version} · {detail.routine.trainer_name ?? "Sin entrenador"} · {detail.routine.item_count} ejercicios · {detail.routine.active_assignments} asignaciones activas
          </p>
        )}
        {detail?.routine.objective && <p className="panel-hint">{detail.routine.objective}</p>}
        {loading && !detail && <p className="panel-hint">Cargando rutina…</p>}
        {error && <div className="login-error" role="alert">{error}</div>}

        {detail && !editing && <RoutinePlanList items={detail.items} />}

        {detail && editing && (
          <div className="detail-section">
            <p className="form-section-label">Nueva versión del plan</p>
            <RoutineLineEditor exercises={exercises} lines={lines} disabled={busy} onChange={setLines} />
            <label className="form-field"><span>Motivo del cambio</span><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Opcional" maxLength={300} /></label>
          </div>
        )}

        {detail && detail.revisions.length > 0 && (
          <div className="detail-section">
            <p className="form-section-label">Historial de versiones</p>
            <ul className="revision-list">
              {detail.revisions.map((revision) => (
                <li className="revision-row" key={`${revision.version}-${revision.created_at}`}>
                  <span className="revision-version">v{revision.version}</span>
                  <span className="revision-body"><strong>{revision.item_count} ejercicios</strong><small>{revision.reason ?? "Sin motivo registrado"} · {formatStamp(revision.created_at)}</small></span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="modal-actions">
          {canManage && detail && !editing && detail.routine.status !== "archived" && <button type="button" className="button button-secondary" onClick={() => setEditing(true)}>Editar plan</button>}
          {canManage && detail && !editing && detail.routine.status !== "archived" && <button type="button" className="button button-secondary" onClick={archive}>Archivar</button>}
          {editing && <button type="button" className="button button-secondary" onClick={() => { setEditing(false); setReason(""); }}>Cancelar edición</button>}
          {editing && <button type="button" className="button button-primary" disabled={busy} onClick={publish}><Check size={16} />{busy ? "Publicando…" : "Publicar nueva versión"}</button>}
          <button type="button" className="button button-secondary" onClick={onClose}>Cerrar</button>
        </div>
      </section>
    </div>
  );
}

function AssignmentFormModal({ routines, members, instructors, onClose, onSaved, onUnauthorized }: { routines: BackendRoutine[]; members: BackendMember[]; instructors: BackendInstructor[]; onClose: () => void; onSaved: (message: string) => void; onUnauthorized: () => void }) {
  const [routineId, setRoutineId] = useState("");
  const [memberId, setMemberId] = useState("");
  const [startDate, setStartDate] = useState(todayDateInput());
  const [endDate, setEndDate] = useState("");
  const [frequency, setFrequency] = useState("3");
  const [trainerId, setTrainerId] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const activeRoutines = routines.filter((routine) => routine.status === "active");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!routineId || !memberId) { setError("Selecciona una rutina y un socio."); return; }
    const frequencyValue = frequency.trim() === "" ? null : Number.parseInt(frequency, 10);
    if (frequencyValue !== null && (!Number.isFinite(frequencyValue) || frequencyValue < 1 || frequencyValue > 7)) { setError("La frecuencia semanal debe estar entre 1 y 7."); return; }
    if (endDate && endDate < startDate) { setError("La fecha de fin no puede ser anterior al inicio."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/routines/assignments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          routine_id: routineId,
          member_id: memberId,
          start_date: startDate,
          end_date: endDate || null,
          frequency_per_week: frequencyValue,
          trainer_id: trainerId || null,
          notes: notes.trim() || null,
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo asignar la rutina."); return; }
      onSaved("Rutina asignada.");
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="assignment-modal-title">
        <div className="modal-header"><span className="modal-icon"><UserPlus size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">ASIGNAR RUTINA</p>
        <h2 id="assignment-modal-title">Nueva asignación</h2>
        <p className="modal-subtitle">La asignación fija la versión actual de la rutina; las ediciones posteriores no la modifican.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Rutina</span><select value={routineId} onChange={(event) => setRoutineId(event.target.value)}><option value="">Selecciona…</option>{activeRoutines.map((routine) => <option key={routine.id} value={routine.id}>{routine.name} · v{routine.version}</option>)}</select></label>
          <label className="form-field"><span>Socio</span><select value={memberId} onChange={(event) => setMemberId(event.target.value)}><option value="">Selecciona…</option>{members.map((member) => <option key={member.id} value={member.id}>{member.first_name} {member.last_name}</option>)}</select></label>
          <div className="form-grid">
            <label className="form-field"><span>Inicio</span><input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
            <label className="form-field"><span>Fin</span><input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
          </div>
          <div className="form-grid">
            <label className="form-field"><span>Frecuencia semanal</span><input value={frequency} inputMode="numeric" onChange={(event) => setFrequency(event.target.value)} /></label>
            <label className="form-field"><span>Entrenador</span><select value={trainerId} onChange={(event) => setTrainerId(event.target.value)}><option value="">Por asignar</option>{instructors.map((instructor) => <option key={instructor.id} value={instructor.id}>{instructor.name}</option>)}</select></label>
          </div>
          <label className="form-field"><span>Notas</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={2} placeholder="Opcional" /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Asignando…" : "Asignar rutina"}</button></div>
        </form>
      </section>
    </div>
  );
}

function AssignmentDetailModal({ assignmentId, canManage, onClose, onChanged, onReviewed, onToast, onUnauthorized }: { assignmentId: string; canManage: boolean; onClose: () => void; onChanged: () => void; onReviewed: () => void; onToast: (message: string) => void; onUnauthorized: () => void }) {
  const [detail, setDetail] = useState<AssignmentDetail | null>(null);
  const [workouts, setWorkouts] = useState<BackendWorkout[]>([]);
  const [progress, setProgress] = useState<MemberProgress | null>(null);
  const [measurements, setMeasurements] = useState<BackendMeasurement[]>([]);
  const [goals, setGoals] = useState<BackendGoal[]>([]);
  const [photos, setPhotos] = useState<BackendProgressPhoto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);

  const [performedAt, setPerformedAt] = useState(todayDateInput());
  const [duration, setDuration] = useState("");
  const [effort, setEffort] = useState("");
  const [workoutNotes, setWorkoutNotes] = useState("");
  const [setDrafts, setSetDrafts] = useState<WorkoutSetDraft[]>([]);

  const [measuredAt, setMeasuredAt] = useState(todayDateInput());
  const [weight, setWeight] = useState("");
  const [waist, setWaist] = useState("");
  const [chest, setChest] = useState("");
  const [bodyFat, setBodyFat] = useState("");
  const [measurementNotes, setMeasurementNotes] = useState("");

  const [goalMetric, setGoalMetric] = useState<GoalMetric>("weight_kg");
  const [goalDirection, setGoalDirection] = useState<GoalDirection>("decrease");
  const [goalTarget, setGoalTarget] = useState("");
  const [goalTargetDate, setGoalTargetDate] = useState("");
  const [goalNotes, setGoalNotes] = useState("");
  const [editingGoalId, setEditingGoalId] = useState<string | null>(null);
  const [editGoalTarget, setEditGoalTarget] = useState("");
  const [editGoalTargetDate, setEditGoalTargetDate] = useState("");
  const [editGoalNotes, setEditGoalNotes] = useState("");
  const [trendMetric, setTrendMetric] = useState<GoalMetric>("weight_kg");

  const [photoAngle, setPhotoAngle] = useState<PhotoAngle>("front");
  const [photoCapturedAt, setPhotoCapturedAt] = useState(todayDateInput());
  const [photoNotes, setPhotoNotes] = useState("");
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [viewingPhoto, setViewingPhoto] = useState<BackendProgressPhoto | null>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const detailResponse = await fetch(`/api/admin/routines/assignments/${assignmentId}`, { cache: "no-store" });
        if (detailResponse.status === 401) { onUnauthorized(); return; }
        if (!detailResponse.ok) throw new Error("failed");
        const detailData = await detailResponse.json() as AssignmentDetail;
        if (!active) return;
        setDetail(detailData);
        const memberId = detailData.assignment.member_id;
        const [workoutsResponse, progressResponse, measurementsResponse, goalsResponse, photosResponse] = await Promise.all([
          fetch(`/api/admin/routines/assignments/${assignmentId}/workouts?page_size=50`, { cache: "no-store" }),
          fetch(`/api/admin/routines/members/${memberId}/progress`, { cache: "no-store" }),
          fetch(`/api/admin/routines/members/${memberId}/measurements?page_size=36`, { cache: "no-store" }),
          fetch(`/api/admin/routines/members/${memberId}/goals`, { cache: "no-store" }),
          fetch(`/api/admin/routines/members/${memberId}/photos`, { cache: "no-store" }),
        ]);
        if ([workoutsResponse, progressResponse, measurementsResponse, goalsResponse, photosResponse].some((response) => response.status === 401)) { onUnauthorized(); return; }
        if (!active) return;
        if (workoutsResponse.ok) setWorkouts(await workoutsResponse.json() as BackendWorkout[]);
        if (progressResponse.ok) setProgress(await progressResponse.json() as MemberProgress);
        if (measurementsResponse.ok) setMeasurements(await measurementsResponse.json() as BackendMeasurement[]);
        if (goalsResponse.ok) setGoals(await goalsResponse.json() as BackendGoal[]);
        if (photosResponse.ok) setPhotos(await photosResponse.json() as BackendProgressPhoto[]);
      } catch {
        if (active) setError("No se pudo cargar la asignación.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [assignmentId, refresh, onUnauthorized]);

  const addSetDraft = (line: BackendRoutineLine) => {
    const existing = setDrafts.filter((draft) => draft.exerciseId === line.exercise_id);
    if (setDrafts.length >= MAX_WORKOUT_DRAFT_SETS) { onToast("Un entrenamiento admite hasta 60 series."); return; }
    if (existing.length >= MAX_WORKOUT_DRAFT_SETS_PER_EXERCISE) { onToast("Cada ejercicio admite hasta 20 series por entrenamiento."); return; }
    const nextNumber = existing.reduce((max, draft) => Math.max(max, draft.setNumber), 0) + 1;
    setSetDrafts([...setDrafts, { key: `${line.exercise_id}-${nextNumber}-${setDrafts.length}`, exerciseId: line.exercise_id, setNumber: nextNumber, reps: /^\d+$/.test(line.reps) ? line.reps : "", weight: "" }]);
  };

  const updateSetDraft = (key: string, field: "reps" | "weight", value: string) => {
    setSetDrafts((current) => current.map((draft) => (draft.key === key ? { ...draft, [field]: value } : draft)));
  };

  const removeSetDraft = (key: string) => {
    setSetDrafts((current) => current.filter((draft) => draft.key !== key));
  };

  const logWorkout = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const durationValue = duration.trim() === "" ? null : Number.parseInt(duration, 10);
    const effortValue = effort.trim() === "" ? null : Number.parseInt(effort, 10);
    if (effortValue !== null && (effortValue < 1 || effortValue > 10)) { onToast("El esfuerzo percibido debe estar entre 1 y 10."); return; }
    const sets: { exercise_id: string; set_number: number; reps: number; weight_kg: number | null }[] = [];
    for (const draft of setDrafts) {
      const repsText = draft.reps.trim();
      if (!/^\d{1,3}$/.test(repsText) || Number(repsText) < 1 || Number(repsText) > 100) { onToast(`Serie ${draft.setNumber}: las repeticiones deben ser un entero entre 1 y 100.`); return; }
      const weightText = draft.weight.trim().replace(",", ".");
      if (weightText !== "" && (!/^\d{1,4}(\.\d{1,2})?$/.test(weightText) || Number(weightText) > 1000)) { onToast(`Serie ${draft.setNumber}: el peso debe estar entre 0 y 1000 kg.`); return; }
      sets.push({ exercise_id: draft.exerciseId, set_number: draft.setNumber, reps: Number(repsText), weight_kg: weightText === "" ? null : Number(weightText) });
    }
    setBusy(true);
    try {
      const response = await fetch(`/api/admin/routines/assignments/${assignmentId}/workouts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ performed_at: performedAt, duration_minutes: durationValue, perceived_effort: effortValue, notes: workoutNotes.trim() || null, sets }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo registrar el entrenamiento."); return; }
      setDuration(""); setEffort(""); setWorkoutNotes(""); setSetDrafts([]);
      setRefresh((value) => value + 1);
      onChanged();
      onToast("Entrenamiento registrado.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const recordMeasurement = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!detail) return;
    const toNumber = (value: string) => (value.trim() === "" ? null : Number(value));
    const body = {
      measured_at: new Date(`${measuredAt}T12:00:00`).toISOString(),
      weight_kg: toNumber(weight),
      waist_cm: toNumber(waist),
      chest_cm: toNumber(chest),
      body_fat_percent: toNumber(bodyFat),
      notes: measurementNotes.trim() || null,
    };
    if (body.weight_kg === null && body.waist_cm === null && body.chest_cm === null && body.body_fat_percent === null) { onToast("Registra al menos una medida."); return; }
    setBusy(true);
    try {
      const response = await fetch(`/api/admin/routines/members/${detail.assignment.member_id}/measurements`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo registrar la medición."); return; }
      setWeight(""); setWaist(""); setChest(""); setBodyFat(""); setMeasurementNotes("");
      setRefresh((value) => value + 1);
      onChanged();
      onToast("Medición registrada.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const createGoal = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!detail) return;
    const targetValue = Number(goalTarget);
    if (!goalTarget.trim() || !Number.isFinite(targetValue) || targetValue <= 0) { onToast("Captura un objetivo válido."); return; }
    setBusy(true);
    try {
      const response = await fetch(`/api/admin/routines/members/${detail.assignment.member_id}/goals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          metric: goalMetric,
          direction: goalDirection,
          target_value: targetValue,
          target_date: goalTargetDate || null,
          notes: goalNotes.trim() || null,
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo registrar la meta."); return; }
      setGoalTarget(""); setGoalTargetDate(""); setGoalNotes("");
      setRefresh((value) => value + 1);
      onChanged();
      onToast("Meta registrada.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const startGoalEdit = (goal: BackendGoal) => {
    setEditingGoalId(goal.id);
    setEditGoalTarget(String(goal.target_value));
    setEditGoalTargetDate(toDateInputValue(goal.target_date));
    setEditGoalNotes(goal.notes ?? "");
  };

  const saveGoalEdit = async (event: FormEvent<HTMLFormElement>, goalId: string) => {
    event.preventDefault();
    const targetValue = Number(editGoalTarget);
    if (!editGoalTarget.trim() || !Number.isFinite(targetValue) || targetValue <= 0) { onToast("Captura un objetivo válido."); return; }
    setBusy(true);
    try {
      const response = await fetch(`/api/admin/routines/goals/${goalId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_value: targetValue,
          target_date: editGoalTargetDate || null,
          notes: editGoalNotes.trim() || null,
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo actualizar la meta."); return; }
      setEditingGoalId(null);
      setRefresh((value) => value + 1);
      onChanged();
      onToast("Meta actualizada.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const cancelGoal = async (goalId: string) => {
    try {
      const response = await fetch(`/api/admin/routines/goals/${goalId}/cancel`, { method: "POST" });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo cancelar la meta."); return; }
      setRefresh((value) => value + 1);
      onChanged();
      onToast("Meta cancelada.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    }
  };

  const uploadPhoto = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!detail) return;
    if (!photoFile) { onToast("Selecciona una imagen."); return; }
    if (!["image/jpeg", "image/png", "image/webp"].includes(photoFile.type)) { onToast("La foto debe ser JPEG, PNG o WebP."); return; }
    if (photoFile.size > MAX_PROGRESS_PHOTO_BYTES) { onToast("La imagen no puede superar 8 MB."); return; }
    if (!photoCapturedAt) { onToast("Selecciona la fecha de la foto."); return; }
    const form = new FormData();
    form.append("photo", photoFile);
    form.append("angle", photoAngle);
    form.append("captured_at", new Date(`${photoCapturedAt}T12:00:00`).toISOString());
    if (photoNotes.trim()) form.append("notes", photoNotes.trim());
    setBusy(true);
    try {
      const response = await fetch(`/api/admin/routines/members/${detail.assignment.member_id}/photos`, {
        method: "POST",
        body: form,
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo subir la foto."); return; }
      setPhotoFile(null);
      setPhotoNotes("");
      setPhotoCapturedAt(todayDateInput());
      if (photoInputRef.current) photoInputRef.current.value = "";
      setRefresh((value) => value + 1);
      onChanged();
      onToast("Foto de progreso subida.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const deletePhoto = async (photo: BackendProgressPhoto) => {
    if (!window.confirm(`¿Eliminar la foto del ${formatDateOnly(photo.captured_at)}? Esta acción no se puede deshacer.`)) return;
    try {
      const response = await fetch(`/api/admin/routines/photos/${photo.id}`, { method: "DELETE" });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        onToast(payload.detail || "No se pudo eliminar la foto.");
        return;
      }
      if (viewingPhoto?.id === photo.id) setViewingPhoto(null);
      setRefresh((value) => value + 1);
      onChanged();
      onToast("Foto eliminada.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    }
  };

  const reviewWorkout = async (workout: BackendWorkout) => {    try {
      const response = await fetch(`/api/admin/routines/workouts/${workout.id}/review`, { method: "POST" });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo marcar el entrenamiento como revisado."); return; }
      setRefresh((value) => value + 1);
      // Reviewing closes the trainer's pending notice, so the badge is stale now.
      onReviewed();
      onToast("Entrenamiento revisado.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    }
  };

  const closeAssignment = async (action: "complete" | "cancel") => {
    try {
      const response = await fetch(`/api/admin/routines/assignments/${assignmentId}/${action}`, { method: "POST" });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo cerrar la asignación."); return; }
      setRefresh((value) => value + 1);
      onChanged();
      onToast(action === "complete" ? "Asignación completada." : "Asignación cancelada.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    }
  };

  const isActive = detail?.assignment.status === "active";

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="assignment-detail-title">
        <div className="modal-header"><span className="modal-icon"><Dumbbell size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">SEGUIMIENTO</p>
        <h2 id="assignment-detail-title">{detail?.assignment.member_name ?? "Cargando…"}</h2>
        {detail && (
          <p className="modal-subtitle">
            {detail.assignment.routine_name} · v{detail.routine_version} · desde {formatDateOnly(detail.assignment.start_date)} · {detail.assignment.frequency_per_week ? `${detail.assignment.frequency_per_week}×/sem` : "sin frecuencia"} · {detail.assignment.trainer_name ?? "sin entrenador"}
          </p>
        )}
        {detail && <div className="detail-tags"><span className={`status-badge ${assignmentStatusBadges[detail.assignment.status]}`}><i />{assignmentStatusLabels[detail.assignment.status]}</span></div>}
        {loading && !detail && <p className="panel-hint">Cargando asignación…</p>}
        {error && <div className="login-error" role="alert">{error}</div>}

        {detail && (
          <div className="detail-columns">
            <div className="detail-section">
              <p className="form-section-label">Plan asignado</p>
              <RoutinePlanList items={detail.plan} />
            </div>
            <div className="detail-section">
              <p className="form-section-label">Progreso del socio</p>
              <div className="progress-stat-grid">
                <div className="progress-stat"><span>Asignaciones activas</span><strong>{progress?.active_assignments ?? 0}</strong></div>
                <div className="progress-stat"><span>Entrenos totales</span><strong>{progress?.workouts_total ?? 0}</strong></div>
                <div className="progress-stat"><span>Últimos 30 días</span><strong>{progress?.workouts_last_30_days ?? 0}</strong></div>
                <div className="progress-stat"><span>Último entreno</span><strong>{formatDateOnly(progress?.last_workout_at ?? null)}</strong></div>
              </div>
              <p className="panel-hint">
                {progress?.latest_measurement
                  ? `Última medición: ${formatStamp(progress.latest_measurement.measured_at)} · ${formatMeasurementValue(progress.latest_measurement.weight_kg, " kg")} · cintura ${formatMeasurementValue(progress.latest_measurement.waist_cm, " cm")}`
                  : "Todavía no hay mediciones registradas."}
              </p>
            </div>
          </div>
        )}

        {detail && (
          <div className="detail-section">
            <p className="form-section-label">Entrenamientos ({workouts.length})</p>
            {canManage && isActive && (
              <form className="inline-form" onSubmit={logWorkout}>
                <label className="form-field"><span>Fecha</span><input type="date" value={performedAt} onChange={(event) => setPerformedAt(event.target.value)} /></label>
                <label className="form-field"><span>Duración (min)</span><input value={duration} inputMode="numeric" placeholder="Opcional" onChange={(event) => setDuration(event.target.value)} /></label>
                <label className="form-field"><span>Esfuerzo (1-10)</span><input value={effort} inputMode="numeric" placeholder="Opcional" onChange={(event) => setEffort(event.target.value)} /></label>
                <label className="form-field inline-grow"><span>Notas</span><input value={workoutNotes} placeholder="Opcional" onChange={(event) => setWorkoutNotes(event.target.value)} /></label>
                <button type="submit" className="button button-primary" disabled={busy}><Plus size={16} />Registrar</button>
                <div className="workout-set-editor">
                  <p className="workout-set-title">Series (opcional)</p>
                  <p className="panel-hint">Repeticiones y peso por serie; se guardan con el entrenamiento.</p>
                  {detail.plan.map((line) => {
                    const drafts = setDrafts.filter((draft) => draft.exerciseId === line.exercise_id);
                    return (
                      <div className="workout-set-group" key={line.id}>
                        <div className="workout-set-head">
                          <strong>{line.exercise_name}</strong>
                          <button type="button" className="text-button" onClick={() => addSetDraft(line)}>+ Añadir serie</button>
                        </div>
                        {drafts.map((draft) => (
                          <div className="workout-set-line" key={draft.key}>
                            <span className="workout-set-number">S{draft.setNumber}</span>
                            <label className="workout-set-field"><span>Reps</span><input value={draft.reps} inputMode="numeric" aria-label={`Repeticiones de la serie ${draft.setNumber} de ${line.exercise_name}`} onChange={(event) => updateSetDraft(draft.key, "reps", event.target.value)} /></label>
                            <label className="workout-set-field"><span>kg</span><input value={draft.weight} inputMode="decimal" placeholder="—" aria-label={`Peso de la serie ${draft.setNumber} de ${line.exercise_name}`} onChange={(event) => updateSetDraft(draft.key, "weight", event.target.value)} /></label>
                            <button type="button" className="text-button" onClick={() => removeSetDraft(draft.key)}>Quitar</button>
                          </div>
                        ))}
                      </div>
                    );
                  })}
                </div>
              </form>
            )}
            {workouts.length === 0 ? <p className="panel-hint">Sin entrenamientos registrados.</p> : (
              <ul className="workout-list">
                {workouts.map((workout) => (
                  <li className="workout-row" key={workout.id}>
                    <span className="workout-date"><strong>{formatDateOnly(workout.performed_at)}</strong><small>{workout.duration_minutes ? `${workout.duration_minutes} min` : "sin duración"}{workout.perceived_effort ? ` · esfuerzo ${workout.perceived_effort}/10` : ""} · {recordOriginLabels[workout.origin]}</small></span>
                    <span className="workout-notes">
                      {workout.notes ?? "—"}
                      {workout.sets.length > 0 && <small className="workout-set-summary">{summarizeWorkoutSets(workout.sets)}</small>}
                    </span>
                    <span className={`status-badge ${workoutStatusBadges[workout.status]}`}><i />{workoutStatusLabels[workout.status]}</span>
                    {canManage && workout.status === "logged" && <button type="button" className="text-button" onClick={() => reviewWorkout(workout)}>Revisar</button>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {detail && (
          <div className="detail-section">
            <p className="form-section-label">Mediciones ({measurements.length})</p>
            {canManage && (
              <form className="inline-form" onSubmit={recordMeasurement}>
                <label className="form-field"><span>Fecha</span><input type="date" value={measuredAt} onChange={(event) => setMeasuredAt(event.target.value)} /></label>
                <label className="form-field"><span>Peso (kg)</span><input value={weight} inputMode="decimal" placeholder="Opcional" onChange={(event) => setWeight(event.target.value)} /></label>
                <label className="form-field"><span>Cintura (cm)</span><input value={waist} inputMode="decimal" placeholder="Opcional" onChange={(event) => setWaist(event.target.value)} /></label>
                <label className="form-field"><span>Pecho (cm)</span><input value={chest} inputMode="decimal" placeholder="Opcional" onChange={(event) => setChest(event.target.value)} /></label>
                <label className="form-field"><span>Grasa (%)</span><input value={bodyFat} inputMode="decimal" placeholder="Opcional" onChange={(event) => setBodyFat(event.target.value)} /></label>
                <button type="submit" className="button button-primary" disabled={busy}><Plus size={16} />Registrar</button>
              </form>
            )}
            <MeasurementTrendChart measurements={measurements} goals={goals} metric={trendMetric} onMetricChange={setTrendMetric} />
            {measurements.length === 0 ? <p className="panel-hint">Sin mediciones registradas.</p> : (
              <table className="data-table compact-table">
                <thead><tr><th>FECHA</th><th>PESO</th><th>CINTURA</th><th>PECHO</th><th>GRASA</th><th>ORIGEN</th><th>NOTAS</th></tr></thead>
                <tbody>
                  {measurements.map((measurement) => (
                    <tr key={measurement.id}>
                      <td>{formatStamp(measurement.measured_at)}</td>
                      <td>{formatMeasurementValue(measurement.weight_kg, " kg")}</td>
                      <td>{formatMeasurementValue(measurement.waist_cm, " cm")}</td>
                      <td>{formatMeasurementValue(measurement.chest_cm, " cm")}</td>
                      <td>{formatMeasurementValue(measurement.body_fat_percent, "%")}</td>
                      <td>{recordOriginLabels[measurement.origin]}</td>
                      <td>{measurement.notes ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {detail && (
          <div className="detail-section">
            <p className="form-section-label">Fotos de progreso ({photos.length})</p>
            {canManage && (
              <form className="inline-form" onSubmit={uploadPhoto}>
                <label className="form-field photo-file-field"><span>Imagen</span><input ref={photoInputRef} type="file" accept="image/jpeg,image/png,image/webp" onChange={(event: ChangeEvent<HTMLInputElement>) => setPhotoFile(event.target.files?.[0] ?? null)} /></label>
                <label className="form-field"><span>Ángulo</span><select value={photoAngle} onChange={(event) => setPhotoAngle(event.target.value as PhotoAngle)}>{PHOTO_ANGLES.map((angle) => <option key={angle} value={angle}>{photoAngleLabels[angle]}</option>)}</select></label>
                <label className="form-field"><span>Fecha</span><input type="date" value={photoCapturedAt} onChange={(event) => setPhotoCapturedAt(event.target.value)} /></label>
                <label className="form-field inline-grow"><span>Nota</span><input value={photoNotes} placeholder="Opcional" onChange={(event) => setPhotoNotes(event.target.value)} /></label>
                <button type="submit" className="button button-primary" disabled={busy || !photoFile}><Upload size={16} />Subir foto</button>
              </form>
            )}
            <p className="panel-hint photo-hint">JPEG, PNG o WebP · máximo 8 MB. Las ve el personal con acceso a Rutinas y el propio socio en su app.</p>
            {photos.length === 0 ? <p className="panel-hint">Sin fotos de progreso.</p> : (
              <ul className="photo-grid">
                {photos.map((photo) => (
                  <li className="photo-card" key={photo.id}>
                    <button type="button" className="photo-thumb" onClick={() => setViewingPhoto(photo)} aria-label={`Ver foto ${photoAngleLabels[photo.angle]} del ${formatDateOnly(photo.captured_at)}`}>
                      <img src={`/api/admin/routines/photos/${photo.id}/file`} alt={`Foto ${photoAngleLabels[photo.angle]} del ${formatDateOnly(photo.captured_at)}`} loading="lazy" decoding="async" />
                    </button>
                    <div className="photo-info">
                      <span className="photo-meta"><strong>{photoAngleLabels[photo.angle]}</strong><small>{formatDateOnly(photo.captured_at)} · {formatFileSize(photo.byte_size)} · {recordOriginLabels[photo.origin]}</small></span>
                      {canManage && <button type="button" className="icon-button photo-delete" aria-label="Eliminar foto" onClick={() => deletePhoto(photo)}><Trash2 size={15} /></button>}
                    </div>
                    {photo.notes && <p className="photo-note">{photo.notes}</p>}
                  </li>
                ))}
              </ul>
            )}
            {viewingPhoto && (
              <div className="photo-viewer" role="dialog" aria-modal="true" aria-label="Foto de progreso" onClick={() => setViewingPhoto(null)}>
                <div className="photo-viewer-content" onClick={(event) => event.stopPropagation()}>
                  <button type="button" className="icon-button photo-viewer-close" aria-label="Cerrar" onClick={() => setViewingPhoto(null)}><X size={18} /></button>
                  <img src={`/api/admin/routines/photos/${viewingPhoto.id}/file`} alt={`Foto ${photoAngleLabels[viewingPhoto.angle]} del ${formatDateOnly(viewingPhoto.captured_at)}`} />
                  <div className="photo-viewer-meta">
                    <strong>{photoAngleLabels[viewingPhoto.angle]} · {formatDateOnly(viewingPhoto.captured_at)}</strong>
                    <span>{formatFileSize(viewingPhoto.byte_size)} · {recordOriginLabels[viewingPhoto.origin]}</span>
                    {viewingPhoto.notes && <p>{viewingPhoto.notes}</p>}
                    {canManage && <button type="button" className="text-button" onClick={() => deletePhoto(viewingPhoto)}>Eliminar foto</button>}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {detail && (
          <div className="detail-section">
            <p className="form-section-label">Metas del socio ({goals.length})</p>
            {canManage && (
              <form className="inline-form" onSubmit={createGoal}>
                <label className="form-field"><span>Medida</span><select value={goalMetric} onChange={(event) => setGoalMetric(event.target.value as GoalMetric)}>{GOAL_METRICS.map((metric) => <option key={metric} value={metric}>{goalMetricLabels[metric]}</option>)}</select></label>
                <label className="form-field"><span>Dirección</span><select value={goalDirection} onChange={(event) => setGoalDirection(event.target.value as GoalDirection)}>{GOAL_DIRECTIONS.map((direction) => <option key={direction} value={direction}>{goalDirectionLabels[direction]}</option>)}</select></label>
                <label className="form-field"><span>Objetivo</span><input value={goalTarget} inputMode="decimal" placeholder="Ej. 68" onChange={(event) => setGoalTarget(event.target.value)} /></label>
                <label className="form-field"><span>Fecha objetivo</span><input type="date" value={goalTargetDate} onChange={(event) => setGoalTargetDate(event.target.value)} /></label>
                <label className="form-field inline-grow"><span>Nota</span><input value={goalNotes} placeholder="Opcional" onChange={(event) => setGoalNotes(event.target.value)} /></label>
                <button type="submit" className="button button-primary" disabled={busy}><Plus size={16} />Agregar meta</button>
              </form>
            )}
            {goals.length === 0 ? <p className="panel-hint">Sin metas registradas.</p> : (
              <ul className="goal-list">
                {goals.map((goal) => (
                  <li className={`goal-row${goal.status === "active" ? "" : " goal-row-muted"}`} key={goal.id}>
                    <div className="goal-head">
                      <span className="goal-title">
                        <strong>{goalMetricLabels[goal.metric]}</strong>
                        <small>{goalDirectionLabels[goal.direction]} a {formatMeasurementValue(goal.target_value, goalMetricUnits[goal.metric])}{goal.target_date ? ` · antes del ${formatDateOnly(goal.target_date)}` : ""} · {recordOriginLabels[goal.origin]}</small>
                      </span>
                      <span className={`status-badge ${goalStatusBadges[goal.status]}`}><i />{goalStatusLabels[goal.status]}</span>
                    </div>
                    <div className="goal-meta">
                      <span>Inicio <strong>{formatMeasurementValue(goal.baseline_value, goalMetricUnits[goal.metric])}</strong></span>
                      <span>Actual <strong>{formatMeasurementValue(goal.current_value, goalMetricUnits[goal.metric])}</strong></span>
                      <span>{goal.progress_percent === null ? "Sin avance calculable" : `${goal.progress_percent}% de avance`}</span>
                    </div>
                    {goal.progress_percent !== null && (
                      <div className="goal-progress" aria-hidden="true"><span style={{ width: `${goal.progress_percent}%` }} /></div>
                    )}
                    {goal.notes && <p className="goal-note">{goal.notes}</p>}
                    {canManage && goal.status === "active" && editingGoalId !== goal.id && (
                      <div className="goal-actions">
                        <button type="button" className="text-button" onClick={() => startGoalEdit(goal)}>Editar</button>
                        <button type="button" className="text-button" onClick={() => cancelGoal(goal.id)}>Cancelar meta</button>
                      </div>
                    )}
                    {canManage && goal.status === "active" && editingGoalId === goal.id && (
                      <form className="inline-form goal-edit-form" onSubmit={(event) => saveGoalEdit(event, goal.id)}>
                        <label className="form-field"><span>Objetivo</span><input value={editGoalTarget} inputMode="decimal" onChange={(event) => setEditGoalTarget(event.target.value)} /></label>
                        <label className="form-field"><span>Fecha objetivo</span><input type="date" value={editGoalTargetDate} onChange={(event) => setEditGoalTargetDate(event.target.value)} /></label>
                        <label className="form-field inline-grow"><span>Nota</span><input value={editGoalNotes} placeholder="Opcional" onChange={(event) => setEditGoalNotes(event.target.value)} /></label>
                        <button type="submit" className="button button-primary" disabled={busy}>Guardar</button>
                        <button type="button" className="button button-secondary" onClick={() => setEditingGoalId(null)}>Cerrar</button>
                      </form>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="modal-actions">
          {canManage && isActive && <button type="button" className="button button-secondary" onClick={() => closeAssignment("complete")}>Finalizar</button>}
          {canManage && isActive && <button type="button" className="button button-secondary" onClick={() => closeAssignment("cancel")}>Cancelar asignación</button>}
          <button type="button" className="button button-secondary" onClick={onClose}>Cerrar</button>
        </div>
      </section>
    </div>
  );
}

type MeasurementPoint = { label: string; at: number; value: number };

const TREND_CHART_WIDTH = 600;
const TREND_CHART_HEIGHT = 190;

function measurementPoints(measurements: BackendMeasurement[], metric: GoalMetric): MeasurementPoint[] {
  return measurements
    .map((measurement) => {
      const value = measurement[metric];
      if (value === null || !Number.isFinite(value)) return null;
      const at = new Date(measurement.measured_at).getTime();
      if (Number.isNaN(at)) return null;
      return { label: formatDateOnly(measurement.measured_at), at, value };
    })
    .filter((point): point is MeasurementPoint => point !== null)
    .sort((a, b) => a.at - b.at);
}

function formatTrendDelta(delta: number, unit: string): string {
  if (Math.abs(delta) < 0.05) return "sin cambio";
  return `${delta > 0 ? "+" : ""}${delta.toFixed(1)}${unit}`;
}

function MeasurementTrendChart({ measurements, goals, metric, onMetricChange }: { measurements: BackendMeasurement[]; goals: BackendGoal[]; metric: GoalMetric; onMetricChange: (metric: GoalMetric) => void }) {
  const unit = goalMetricUnits[metric];
  const points = measurementPoints(measurements, metric);
  const goal = goals.find((item) => item.metric === metric && item.status === "active") ?? null;
  const first = points[0] ?? null;
  const latest = points[points.length - 1] ?? null;

  return (
    <div className="trend-panel">
      <div className="trend-toolbar">
        <div className="trend-tabs" aria-label="Medida de la gráfica">
          {GOAL_METRICS.map((option) => (
            <button key={option} type="button" className="trend-tab" aria-pressed={option === metric} onClick={() => onMetricChange(option)}>{goalMetricLabels[option]}</button>
          ))}
        </div>
        {first && latest && points.length >= 2 ? (
          <p className="trend-summary">
            <strong>{formatMeasurementValue(first.value, unit)} → {formatMeasurementValue(latest.value, unit)}</strong>
            <span>{formatTrendDelta(latest.value - first.value, unit)} desde {first.label}</span>
          </p>
        ) : (
          <p className="trend-summary"><span>{goal ? `Meta activa: ${formatMeasurementValue(goal.target_value, unit)}` : "Sin meta activa"}</span></p>
        )}
      </div>
      {points.length < 2 ? (
        <p className="panel-hint">
          {points.length === 0
            ? `Aún no hay mediciones de ${goalMetricLabels[metric].toLowerCase()} para graficar.`
            : `Registra al menos dos mediciones de ${goalMetricLabels[metric].toLowerCase()} para ver la evolución.`}
        </p>
      ) : (
        <MeasurementTrendSvg points={points} goal={goal} metric={metric} />
      )}
    </div>
  );
}

function MeasurementTrendSvg({ points, goal, metric }: { points: MeasurementPoint[]; goal: BackendGoal | null; metric: GoalMetric }) {
  const unit = goalMetricUnits[metric];
  const padLeft = 42;
  const padRight = 14;
  const padTop = 16;
  const padBottom = 24;
  const plotWidth = TREND_CHART_WIDTH - padLeft - padRight;
  const plotHeight = TREND_CHART_HEIGHT - padTop - padBottom;
  const first = points[0];
  const last = points[points.length - 1];
  const values = points.map((point) => point.value);
  if (goal) values.push(goal.target_value);
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  const span = dataMax - dataMin;
  const padding = span < 0.1 ? 1 : span * 0.12;
  const min = dataMin - padding;
  const max = dataMax + padding;
  const x = (at: number) => padLeft + ((at - first.at) / (last.at - first.at || 1)) * plotWidth;
  const y = (value: number) => padTop + (1 - (value - min) / (max - min)) * plotHeight;
  const tickValues = span < 0.1 ? [dataMin] : [0, 1 / 3, 2 / 3, 1].map((fraction) => dataMin + span * fraction);
  const linePath = points.map((point, index) => `${index === 0 ? "M" : "L"}${x(point.at).toFixed(2)} ${y(point.value).toFixed(2)}`).join(" ");
  const middleIndex = Math.floor((points.length - 1) / 2);
  const showMiddleLabel = middleIndex > 0 && middleIndex < points.length - 1;
  const goalY = goal ? y(goal.target_value) : null;
  const goalLabelY = goalY === null ? null : goalY - padTop < 10 ? goalY + 10 : goalY - 4;

  return (
    <svg className="trend-chart" viewBox={`0 0 ${TREND_CHART_WIDTH} ${TREND_CHART_HEIGHT}`} role="img" aria-label={`Evolución de ${goalMetricLabels[metric].toLowerCase()}: de ${formatMeasurementValue(first.value, unit)} el ${first.label} a ${formatMeasurementValue(last.value, unit)} el ${last.label}${goal ? `, meta ${formatMeasurementValue(goal.target_value, unit)}` : ""}.`}>
      {tickValues.map((tick) => (
        <g key={tick}>
          <line className="trend-grid" x1={padLeft} x2={TREND_CHART_WIDTH - padRight} y1={y(tick)} y2={y(tick)} />
          <text className="trend-axis" x={padLeft - 6} y={y(tick) + 3} textAnchor="end">{tick.toFixed(1)}</text>
        </g>
      ))}
      {goalY !== null && goalLabelY !== null && (
        <g>
          <line className="trend-goal" x1={padLeft} x2={TREND_CHART_WIDTH - padRight} y1={goalY} y2={goalY} />
          <text className="trend-goal-label" x={TREND_CHART_WIDTH - padRight} y={goalLabelY} textAnchor="end">Meta {formatMeasurementValue(goal?.target_value ?? null, unit)}</text>
        </g>
      )}
      <path className="trend-line" d={linePath} />
      {points.map((point, index) => (
        <circle className="trend-point" key={`${point.at}-${index}`} cx={x(point.at)} cy={y(point.value)} r={3.2}>
          <title>{`${point.label}: ${formatMeasurementValue(point.value, unit)}`}</title>
        </circle>
      ))}
      <text className="trend-axis" x={x(first.at)} y={TREND_CHART_HEIGHT - 6} textAnchor="start">{first.label}</text>
      {showMiddleLabel && <text className="trend-axis" x={x(points[middleIndex].at)} y={TREND_CHART_HEIGHT - 6} textAnchor="middle">{points[middleIndex].label}</text>}
      <text className="trend-axis" x={x(last.at)} y={TREND_CHART_HEIGHT - 6} textAnchor="end">{last.label}</text>
    </svg>
  );
}

const REPORT_TABS: { value: ReportName; label: string }[] = [
  { value: "overview", label: "Resumen" },
  { value: "revenue", label: "Ingresos" },
  { value: "memberships", label: "Socios" },
  { value: "operations", label: "Operación" },
  { value: "maintenance", label: "Mantenimiento" },
  { value: "inventory", label: "Inventario" },
];

const reportMovementLabels: Record<string, string> = {
  intake: "Entradas",
  sale: "Ventas",
  adjustment: "Ajustes",
  waste: "Mermas",
  return: "Devoluciones",
};

const reportStateLabels: Record<string, string> = {
  active: "Activos",
  inactive: "Inactivos",
  pending: "Pendientes",
  frozen: "Congelados",
  cancelled: "Cancelados",
  suspended: "Suspendidos",
  expired: "Vencidos",
  pending_payment: "Pago pendiente",
  operational: "Operativos",
  maintenance: "En mantenimiento",
  out_of_service: "Fuera de servicio",
  inspection: "En revisión",
  retired: "Retirados",
  open: "Abiertos",
  assigned: "Asignados",
  in_progress: "En proceso",
  resolved: "Resueltos",
  low: "Baja",
  medium: "Media",
  high: "Alta",
  critical: "Crítica",
  preventive: "Preventivo",
  corrective: "Correctivo",
  cleaning: "Limpieza",
  calibration: "Calibración",
  payment_confirmed: "Pagos confirmados",
  manual_activation: "Altas manuales",
  created_pending_payment: "Altas pendientes de cobro",
};

function reportLabel(key: string): string {
  return reportStateLabels[key] ?? key;
}

function reportDayLabel(iso: string, total: number): string {
  return total <= 31 ? iso.slice(8, 10) : "";
}

function reportMethodLabel(key: string): string {
  return paymentMethodLabels[key] ?? reportLabel(key);
}

function ReportStat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="report-stat">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  );
}

function ReportBarChart({ points }: { points: { label: string; value: number; hint: string }[] }) {
  // Net revenue can be negative on a refund-heavy day, so the chart plots a
  // signed range around a zero line instead of assuming every value is positive.
  const max = Math.max(1, ...points.map((point) => point.value));
  const min = Math.min(0, ...points.map((point) => point.value));
  const span = max - min;
  const zero = (max / span) * 100;
  return (
    <div className="report-chart" role="img" aria-label="Serie del periodo">
      {points.map((point, index) => {
        const negative = point.value < 0;
        const height = Math.min(100, Math.max(3, (Math.abs(point.value) / span) * 100));
        return (
          <div className="chart-column" key={`${point.label}-${index}`} title={point.hint}>
            <div className="chart-track">
              {min < 0 && <div className="chart-zero" style={{ top: `${zero}%` }} />}
              <div
                className={`chart-bar ${negative ? "chart-bar-negative" : ""} ${point.value > 0 && point.value >= max ? "chart-bar-highlight" : ""}`}
                style={{ height: `${height}%`, top: negative ? `${zero}%` : `${zero - height}%` }}
              />
            </div>
            <span>{point.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function ReportList({ title, rows }: { title: string; rows: { label: string; value: string }[] }) {
  return (
    <div className="report-list">
      <p className="section-kicker">{title}</p>
      {rows.length === 0 ? (
        <p className="empty-row">Sin registros en el periodo.</p>
      ) : (
        <ul>
          {rows.map((row) => (
            <li key={row.label}>
              <span>{row.label}</span>
              <strong>{row.value}</strong>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReportPpdPanel({ data }: { data: ReportPpdReceivables }) {
  const aging = [
    { label: "Corriente (0-30 días)", value: data.aging.current_cents },
    { label: "31-60 días", value: data.aging.days_31_60_cents },
    { label: "61-90 días", value: data.aging.days_61_90_cents },
    { label: "Más de 90 días", value: data.aging.over_90_cents },
  ];
  return (
    <section className="panel full-panel">
      <div className="panel-header access-list-heading">
        <div><p className="section-kicker">CARTERA PPD</p><h2>Saldos por cobrar</h2></div>
        <span className="table-hint">Corte al {formatDateOnly(data.as_of)} · no depende del periodo seleccionado</span>
      </div>
      <div className="report-stat-grid">
        <ReportStat label="Saldo pendiente" value={formatMoney(data.outstanding_cents)} hint={`${data.invoices} ${data.invoices === 1 ? "factura abierta" : "facturas abiertas"}`} />
        <ReportStat label="Total facturado" value={formatMoney(data.total_cents)} hint="Importe original de las facturas abiertas" />
        <ReportStat label="Cobrado con complementos" value={formatMoney(data.paid_cents)} hint={`${data.stamped_complements} ${data.stamped_complements === 1 ? "complemento timbrado" : "complementos timbrados"}`} />
        <ReportStat label="Por timbrar" value={formatMoney(data.requested_complement_cents)} hint={`${data.requested_complements} ${data.requested_complements === 1 ? "complemento solicitado" : "complementos solicitados"}`} />
        <ReportStat label="Con error de timbrado" value={formatMoney(data.failed_complement_cents)} hint={`${data.failed_complements} ${data.failed_complements === 1 ? "complemento fallido" : "complementos fallidos"}`} />
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead><tr><th>ANTIGÜEDAD DESDE EL TIMBRADO</th><th>IMPORTE</th></tr></thead>
          <tbody>
            {aging.map((bucket) => (
              <tr key={bucket.label}>
                <td>{bucket.label}</td>
                <td>{formatMoney(bucket.value)}</td>
              </tr>
            ))}
            <tr>
              <td><strong>Total</strong></td>
              <td><strong>{formatMoney(data.outstanding_cents)}</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
      {data.invoices === 0 && <p className="empty-row">No hay facturas PPD timbradas con saldo pendiente.</p>}
      {data.oldest_stamped_at && (
        <p className="table-hint">Factura abierta más antigua timbrada el {formatDateOnly(data.oldest_stamped_at)}.</p>
      )}
    </section>
  );
}

function ReportFallback({ loading, error }: { loading: boolean; error: string }) {
  return (
    <section className="panel full-panel">
      <p className="empty-row">{error || (loading ? "Cargando reporte…" : "Sin datos para el periodo seleccionado.")}</p>
    </section>
  );
}

function ReportsView({ permissions, onUnauthorized, onToast }: { permissions: string[]; onUnauthorized: () => void; onToast: (message: string) => void }) {
  const canExport = permissions.includes("finance.read");

  const [tab, setTab] = useState<ReportName>("overview");
  const [range, setRange] = useState<"7" | "30" | "90" | "custom">("30");
  const today = todayDateInput();
  const [customFrom, setCustomFrom] = useState(() => shiftDateInput(today, -29));
  const [customTo, setCustomTo] = useState(today);
  const [refresh, setRefresh] = useState(0);

  const period = useMemo(() => {
    if (range === "custom") return { date_from: customFrom, date_to: customTo };
    return { date_from: shiftDateInput(today, -(Number(range) - 1)), date_to: today };
  }, [range, customFrom, customTo, today]);

  const periodDays = useMemo(() => {
    const from = new Date(`${period.date_from}T00:00:00`);
    const to = new Date(`${period.date_to}T00:00:00`);
    return Math.max(1, Math.round((to.getTime() - from.getTime()) / 86400000) + 1);
  }, [period.date_from, period.date_to]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [overview, setOverview] = useState<ReportOverview | null>(null);
  const [revenue, setRevenue] = useState<RevenueReport | null>(null);
  const [memberStats, setMemberStats] = useState<MembershipReport | null>(null);
  const [operations, setOperations] = useState<OperationsReport | null>(null);
  const [maintenanceStats, setMaintenanceStats] = useState<MaintenanceReport | null>(null);
  const [inventoryStats, setInventoryStats] = useState<InventoryReport | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      const params = new URLSearchParams({ date_from: period.date_from, date_to: period.date_to });
      try {
        const response = await fetch(`/api/admin/reports/${tab}?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        const payload = await response.json();
        if (!active) return;
        if (tab === "overview") setOverview(payload as ReportOverview);
        if (tab === "revenue") setRevenue(payload as RevenueReport);
        if (tab === "memberships") setMemberStats(payload as MembershipReport);
        if (tab === "operations") setOperations(payload as OperationsReport);
        if (tab === "maintenance") setMaintenanceStats(payload as MaintenanceReport);
        if (tab === "inventory") setInventoryStats(payload as InventoryReport);
      } catch {
        if (active) setError("No se pudo cargar el reporte para el periodo seleccionado.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [tab, period.date_from, period.date_to, refresh, onUnauthorized]);

  let bandStats: { label: string; value: string }[] = [];
  if (tab === "overview" && overview) {
    bandStats = [
      { label: "INGRESOS COBRADOS", value: formatMoney(overview.pos_cents + overview.membership_cents) },
      { label: "INGRESO RECURRENTE", value: formatMoney(overview.mrr_expected_cents) },
      { label: "COSTO DE MANTENIMIENTO", value: formatMoney(overview.maintenance_cost_cents) },
      { label: "TICKETS ABIERTOS", value: String(overview.tickets_open) },
    ];
  } else if (tab === "revenue" && revenue) {
    bandStats = [
      { label: "MOSTRADOR NETO", value: formatMoney(revenue.pos_cents) },
      { label: "DEVOLUCIONES", value: formatMoney(revenue.refunds_cents) },
      { label: "TOTAL COBRADO", value: formatMoney(revenue.pos_cents + revenue.membership_cents) },
      { label: "VENTAS", value: String(revenue.sales_count) },
    ];
  } else if (tab === "memberships" && memberStats) {
    bandStats = [
      { label: "SOCIOS", value: String(memberStats.members_total) },
      { label: "NUEVOS EN EL PERIODO", value: String(memberStats.new_members) },
      { label: "POR VENCER (7 DÍAS)", value: String(memberStats.members_expiring) },
      { label: "INGRESO RECURRENTE", value: formatMoney(memberStats.mrr_expected_cents) },
    ];
  } else if (tab === "operations" && operations) {
    bandStats = [
      { label: "ACCESOS", value: String(operations.access_total) },
      { label: "DENEGADOS", value: String(operations.access_denied) },
      { label: "OCUPACIÓN DE CLASES", value: `${operations.class_occupancy_percent}%` },
      { label: "ENTRENAMIENTOS", value: String(operations.workouts) },
    ];
  } else if (tab === "maintenance" && maintenanceStats) {
    bandStats = [
      { label: "COSTO DEL PERIODO", value: formatMoney(maintenanceStats.cost_cents) },
      { label: "SERVICIOS", value: String(maintenanceStats.records_count) },
      { label: "TICKETS CREADOS", value: String(maintenanceStats.tickets_created) },
      { label: "PREVENTIVOS VENCIDOS", value: String(maintenanceStats.preventives_due) },
    ];
  } else if (tab === "inventory" && inventoryStats) {
    bandStats = [
      { label: "VALOR AL COSTO", value: formatMoney(inventoryStats.stock_value_cents) },
      { label: "A PRECIO DE VENTA", value: formatMoney(inventoryStats.retail_value_cents) },
      { label: "BAJO MÍNIMO", value: String(inventoryStats.low_stock) },
      { label: "AGOTADOS", value: String(inventoryStats.out_of_stock) },
    ];
  }

  const exportHref = `/api/admin/reports/export?report=${tab}&date_from=${period.date_from}&date_to=${period.date_to}`;
  const reportTimezone =
    overview?.period.timezone ?? revenue?.period.timezone ?? memberStats?.period.timezone ?? operations?.period.timezone ?? maintenanceStats?.period.timezone ?? inventoryStats?.period.timezone ?? "";

  return (
    <>
      <section className="access-summary-band pos-cash-band">
        <div className="access-summary-main">
          <span className="summary-icon"><BarChart3 size={18} /></span>
          <div>
            <span>PANEL DE ANALÍTICA</span>
            <strong>{`${periodDays} días · ${formatDateOnly(period.date_from)} a ${formatDateOnly(period.date_to)}`}</strong>
            {reportTimezone && <small className="report-timezone">Días y horas en {reportTimezone}</small>}
          </div>
        </div>
        <div className="summary-divider" />
        {bandStats.map((stat) => <div className="summary-stat" key={stat.label}><span>{stat.label}</span><strong>{stat.value}</strong></div>)}
        {canExport && (
          <a
            className="button button-primary"
            href={exportHref}
            onClick={() => onToast("Preparando la descarga del reporte en CSV.")}
          >
            Exportar CSV
          </a>
        )}
      </section>

      <div className="staff-tabs pos-tabs">
        {REPORT_TABS.map(({ value, label }) => (
          <button key={value} type="button" className={tab === value ? "staff-tab-active" : ""} onClick={() => setTab(value)}>{label}</button>
        ))}
        <span className="staff-tabs-note"><ShieldCheck size={14} />Solo lectura: los reportes no modifican la operación</span>
      </div>

      <div className="report-controls">
        <div className="report-range">
          {(["7", "30", "90"] as const).map((value) => (
            <button key={value} type="button" className={range === value ? "staff-tab-active" : ""} onClick={() => setRange(value)}>{`${value} días`}</button>
          ))}
          <button type="button" className={range === "custom" ? "staff-tab-active" : ""} onClick={() => setRange("custom")}>Personalizado</button>
        </div>
        {range === "custom" && (
          <div className="report-dates">
            <label>Desde<input type="date" value={customFrom} max={customTo} onChange={(event) => setCustomFrom(event.target.value)} /></label>
            <label>Hasta<input type="date" value={customTo} min={customFrom} onChange={(event) => setCustomTo(event.target.value)} /></label>
          </div>
        )}
        <button type="button" className="button button-secondary" onClick={() => setRefresh((value) => value + 1)} disabled={loading}>Actualizar</button>
      </div>

      {tab === "overview" && (overview ? (
        <>
          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">INDICADORES DEL PERIODO</p><h2>Resumen</h2></div></div>
            <div className="report-stat-grid">
              <ReportStat label="Ingresos cobrados" value={formatMoney(overview.pos_cents + overview.membership_cents)} hint={`Mostrador neto ${formatMoney(overview.pos_cents)} · Membresías ${formatMoney(overview.membership_cents)}`} />
              <ReportStat label="Ventas de mostrador" value={String(overview.sales_count)} hint={`Ticket promedio ${formatMoney(overview.average_ticket_cents)} · Devoluciones ${formatMoney(overview.refunds_cents)}`} />
              <ReportStat label="Cobros de membresía" value={String(overview.payments_count)} hint={formatMoney(overview.membership_cents)} />
              <ReportStat label="Ingreso recurrente esperado" value={formatMoney(overview.mrr_expected_cents)} hint="Valor mensual de las membresías activas; no es un cobro" />
              <ReportStat label="Costo de mantenimiento" value={formatMoney(overview.maintenance_cost_cents)} hint={`${overview.maintenance_records} servicios registrados`} />
              <ReportStat label="Accesos" value={String(overview.access_total)} hint={`${overview.access_denied} denegados · ${overview.access_manual} manuales`} />
              <ReportStat label="Ocupación de clases" value={`${overview.class_occupancy_percent}%`} hint={`${overview.class_sessions} clases · ${overview.class_attended} asistencias · ${overview.class_no_show} inasistencias`} />
              <ReportStat label="Entrenamientos" value={String(overview.workouts)} hint={`${overview.measurements} mediciones registradas`} />
            </div>
          </section>

          <section className="panel full-panel">
            <div className="panel-header access-list-heading">
              <div><p className="section-kicker">INGRESOS COBRADOS</p><h2>Por día</h2></div>
              <span className="chart-legend"><i />Mostrador + membresías</span>
            </div>
            <ReportBarChart points={overview.revenue_by_day.map((day) => ({ label: reportDayLabel(day.day, overview.revenue_by_day.length), value: day.total_cents, hint: `${formatDateOnly(day.day)} · ${formatMoney(day.total_cents)}${day.refunds_cents > 0 ? ` (${formatMoney(day.refunds_cents)} devuelto)` : ""}` }))} />
            <div className="chart-foot"><span>{formatDateOnly(period.date_from)}</span><span>MXN NETO</span><span>{formatDateOnly(period.date_to)}</span></div>
          </section>

          <section className="panel full-panel">
            <div className="panel-header access-list-heading">
              <div><p className="section-kicker">CONTROL DE ACCESO</p><h2>Accesos por día</h2></div>
            </div>
            <ReportBarChart points={overview.access_by_day.map((day) => ({ label: reportDayLabel(day.day, overview.access_by_day.length), value: day.total, hint: `${formatDateOnly(day.day)} · ${day.total} accesos (${day.denied} denegados)` }))} />
          </section>

          <section className="report-columns">
            <ReportList title="SOCIOS POR ESTADO" rows={overview.members_by_status.map((row) => ({ label: reportLabel(row.label), value: String(row.count) }))} />
            <ReportList title="MEMBRESÍAS POR ESTADO" rows={overview.memberships_by_status.map((row) => ({ label: reportLabel(row.label), value: String(row.count) }))} />
            <ReportList title="FLOTA POR ESTADO" rows={overview.equipment_by_status.map((row) => ({ label: reportLabel(row.label), value: `${row.count} de ${overview.equipment_total}` }))} />
            <ReportList title="ALERTAS" rows={[
              { label: "Nuevos socios en el periodo", value: String(overview.new_members) },
              { label: "Membresías por vencer (7 días)", value: String(overview.members_expiring) },
              { label: "Tickets abiertos", value: String(overview.tickets_open) },
              { label: "Tickets críticos abiertos", value: String(overview.tickets_critical) },
            ]} />
          </section>
        </>
      ) : <ReportFallback loading={loading} error={error} />)}

      {tab === "revenue" && (revenue ? (
        <>
          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">DINERO COBRADO</p><h2>Ingresos</h2></div></div>
            <div className="report-stat-grid">
              <ReportStat label="Mostrador (neto)" value={formatMoney(revenue.pos_cents)} hint={`${formatMoney(revenue.pos_gross_cents)} brutos − ${formatMoney(revenue.refunds_cents)} devueltos`} />
              <ReportStat label="Devoluciones" value={formatMoney(revenue.refunds_cents)} hint={`${revenue.refunds_count} devoluciones en el periodo`} />
              <ReportStat label="Membresías" value={formatMoney(revenue.membership_cents)} hint={`${revenue.payments_count} cobros confirmados`} />
              <ReportStat label="Total cobrado" value={formatMoney(revenue.pos_cents + revenue.membership_cents)} hint="Mostrador neto + membresías" />
              <ReportStat label="Ticket promedio" value={formatMoney(revenue.average_ticket_cents)} hint={`${revenue.sales_count} ventas brutas`} />
              <ReportStat label="Turnos de caja" value={String(revenue.cash_sessions_closed)} hint={`${revenue.cash_sessions_opened} abiertos en el periodo`} />
              <ReportStat label="Diferencia de caja" value={formatMoney(revenue.cash_difference_cents)} hint="Valor absoluto de los cierres del periodo" />
            </div>
          </section>

          <section className="panel full-panel">
            <div className="panel-header access-list-heading">
              <div><p className="section-kicker">INGRESOS COBRADOS</p><h2>Por día</h2></div>
              <span className="chart-legend"><i />Neto: mostrador + membresías</span>
            </div>
            <ReportBarChart points={revenue.by_day.map((day) => ({ label: reportDayLabel(day.day, revenue.by_day.length), value: day.total_cents, hint: `${formatDateOnly(day.day)} · ${formatMoney(day.total_cents)} (${day.sales_count} ventas${day.refunds_cents > 0 ? `, ${formatMoney(day.refunds_cents)} devuelto` : ""})` }))} />
            <div className="chart-foot"><span>{formatDateOnly(period.date_from)}</span><span>MXN NETO</span><span>{formatDateOnly(period.date_to)}</span></div>
          </section>

          <section className="report-columns">
            <ReportList title="MOSTRADOR NETO POR MÉTODO" rows={revenue.pos_by_method.map((row) => ({ label: `${reportMethodLabel(row.label)} (${row.count})`, value: formatMoney(row.amount_cents) }))} />
            <ReportList title="MEMBRESÍAS POR MÉTODO" rows={revenue.membership_by_method.map((row) => ({ label: `${reportMethodLabel(row.label)} (${row.count})`, value: formatMoney(row.amount_cents) }))} />
            <ReportList title="VENTAS NETAS POR CATEGORÍA" rows={revenue.by_category.map((row) => ({ label: `${row.label} (${row.count} pzs)`, value: formatMoney(row.amount_cents) }))} />
            <ReportList title="CAJA" rows={[
              { label: "Turnos abiertos", value: String(revenue.cash_sessions_opened) },
              { label: "Turnos cerrados", value: String(revenue.cash_sessions_closed) },
              { label: "Diferencia acumulada", value: formatMoney(revenue.cash_difference_cents) },
            ]} />
          </section>

          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">PRODUCTOS</p><h2>Más vendidos (neto)</h2></div></div>
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr><th>PRODUCTO</th><th>SKU</th><th>PIEZAS</th><th>IMPORTE</th></tr></thead>
                <tbody>
                  {revenue.top_products.length === 0
                    ? <tr><td colSpan={4} className="empty-row">Sin ventas de mostrador en el periodo.</td></tr>
                    : revenue.top_products.map((product) => (
                      <tr key={product.product_id}>
                        <td><strong>{product.name}</strong></td>
                        <td>{product.sku}</td>
                        <td>{product.quantity}</td>
                        <td>{formatMoney(product.amount_cents)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </section>

          <ReportPpdPanel data={revenue.ppd_receivables} />
        </>
      ) : <ReportFallback loading={loading} error={error} />)}

      {tab === "memberships" && (memberStats ? (
        <>
          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">CARTERA DE SOCIOS</p><h2>Socios</h2></div></div>
            <div className="report-stat-grid">
              <ReportStat label="Socios registrados" value={String(memberStats.members_total)} />
              <ReportStat label="Nuevos en el periodo" value={String(memberStats.new_members)} />
              <ReportStat label="Por vencer (7 días)" value={String(memberStats.members_expiring)} />
              <ReportStat label="Cobros del periodo" value={formatMoney(memberStats.payments_cents)} hint={`${memberStats.payments_count} cobros`} />
              <ReportStat label="Ingreso recurrente esperado" value={formatMoney(memberStats.mrr_expected_cents)} hint="Valor mensual equivalente de planes activos" />
            </div>
          </section>

          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">MEMBRESÍAS ACTIVAS</p><h2>Por plan</h2></div></div>
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr><th>PLAN</th><th>DURACIÓN</th><th>PRECIO</th><th>ACTIVAS</th><th>MENSUAL EQUIVALENTE</th></tr></thead>
                <tbody>
                  {memberStats.by_plan.length === 0
                    ? <tr><td colSpan={5} className="empty-row">No hay membresías activas.</td></tr>
                    : memberStats.by_plan.map((plan) => (
                      <tr key={plan.plan_id}>
                        <td><strong>{plan.name}</strong></td>
                        <td>{plan.duration_days === 1 ? "1 día" : `${plan.duration_days} días`}</td>
                        <td>{formatMoney(plan.price_cents)}</td>
                        <td>{plan.active_count}</td>
                        <td>{plan.recurring ? formatMoney(plan.monthly_cents) : "No recurrente"}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="report-columns">
            <ReportList title="SOCIOS POR ESTADO" rows={memberStats.members_by_status.map((row) => ({ label: reportLabel(row.label), value: String(row.count) }))} />
            <ReportList title="MEMBRESÍAS POR ESTADO" rows={memberStats.memberships_by_status.map((row) => ({ label: reportLabel(row.label), value: String(row.count) }))} />
            <ReportList title="MOVIMIENTOS DEL PERIODO" rows={memberStats.events.map((row) => ({ label: reportLabel(row.label), value: String(row.count) }))} />
            <ReportList title="ALTAS Y BAJAS POR DÍA" rows={memberStats.events_by_day
              .filter((day) => day.activations > 0 || day.terminations > 0)
              .map((day) => ({ label: formatDateOnly(day.day), value: `+${day.activations} / -${day.terminations}` }))} />
          </section>
        </>
      ) : <ReportFallback loading={loading} error={error} />)}

      {tab === "operations" && (operations ? (
        <>
          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">OPERACIÓN</p><h2>Actividad del periodo</h2></div></div>
            <div className="report-stat-grid">
              <ReportStat label="Accesos" value={String(operations.access_total)} hint={`${operations.access_authorized} autorizados · ${operations.access_denied} denegados`} />
              <ReportStat label="Accesos manuales" value={String(operations.access_manual)} hint="Registrados por recepción" />
              <ReportStat label="Clases programadas" value={String(operations.class_sessions)} hint={`Cupo ofrecido ${operations.class_capacity}`} />
              <ReportStat label="Ocupación de clases" value={`${operations.class_occupancy_percent}%`} hint={`${operations.class_reserved} reservadas · ${operations.class_attended} asistencias`} />
              <ReportStat label="Inasistencias" value={String(operations.class_no_show)} hint={`${operations.class_cancelled} canceladas · ${operations.class_waitlist} en espera`} />
              <ReportStat label="Entrenamientos" value={String(operations.workouts)} hint={`${operations.workout_minutes} minutos registrados`} />
              <ReportStat label="Mediciones corporales" value={String(operations.measurements)} hint="Registros de progreso" />
            </div>
          </section>

          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">CONTROL DE ACCESO</p><h2>Accesos por día</h2></div></div>
            <ReportBarChart points={operations.access_by_day.map((day) => ({ label: reportDayLabel(day.day, operations.access_by_day.length), value: day.total, hint: `${formatDateOnly(day.day)} · ${day.total} accesos (${day.denied} denegados)` }))} />
          </section>

          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">CONTROL DE ACCESO</p><h2>Accesos por hora</h2></div></div>
            <ReportBarChart points={operations.access_by_hour.map((row) => ({ label: row.label, value: row.count, hint: `${row.label}:00 · ${row.count} accesos` }))} />
            <div className="chart-foot"><span>00:00</span><span>HORA LOCAL</span><span>23:00</span></div>
          </section>

          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">ENTRENAMIENTO</p><h2>Entrenamientos por día</h2></div></div>
            <ReportBarChart points={operations.workouts_by_day.map((row) => ({ label: reportDayLabel(row.label, operations.workouts_by_day.length), value: row.count, hint: `${formatDateOnly(row.label)} · ${row.count} entrenamientos` }))} />
          </section>
        </>
      ) : <ReportFallback loading={loading} error={error} />)}

      {tab === "maintenance" && (maintenanceStats ? (
        <>
          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">EQUIPO E INSTALACIONES</p><h2>Mantenimiento</h2></div></div>
            <div className="report-stat-grid">
              <ReportStat label="Costo del periodo" value={formatMoney(maintenanceStats.cost_cents)} hint={`${maintenanceStats.records_count} servicios registrados`} />
              <ReportStat label="Tickets creados" value={String(maintenanceStats.tickets_created)} />
              <ReportStat label="Preventivos vencidos" value={String(maintenanceStats.preventives_due)} hint="Equipos activos con fecha vencida" />
              <ReportStat label="Equipos con costo" value={String(maintenanceStats.by_equipment.length)} hint="Equipos atendidos en el periodo" />
            </div>
          </section>

          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">COSTO POR EQUIPO</p><h2>Detalle</h2></div></div>
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr><th>EQUIPO</th><th>UBICACIÓN</th><th>ESTADO</th><th>SERVICIOS</th><th>COSTO</th><th>TICKETS ABIERTOS</th></tr></thead>
                <tbody>
                  {maintenanceStats.by_equipment.length === 0
                    ? <tr><td colSpan={6} className="empty-row">Sin servicios registrados en el periodo.</td></tr>
                    : maintenanceStats.by_equipment.map((equipment) => (
                      <tr key={equipment.equipment_id}>
                        <td><div className="person-cell"><span className="pos-row-icon"><Wrench size={15} /></span><span><strong>{equipment.name}</strong><small>{equipment.category}</small></span></div></td>
                        <td>{equipment.location ?? "—"}</td>
                        <td><span className={`status-badge ${equipmentStatusBadges[equipment.status as EquipmentState] ?? "status-neutral"}`}><i />{reportLabel(equipment.status)}</span></td>
                        <td>{equipment.records_count}</td>
                        <td>{formatMoney(equipment.cost_cents)}</td>
                        <td>{equipment.open_tickets > 0 ? <span className="status-badge status-warn"><i />{equipment.open_tickets}</span> : "—"}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="report-columns">
            <ReportList title="COSTO POR TIPO DE TRABAJO" rows={maintenanceStats.by_kind.map((row) => ({ label: `${reportLabel(row.label)} (${row.count})`, value: formatMoney(row.amount_cents) }))} />
            <ReportList title="TICKETS POR SEVERIDAD" rows={maintenanceStats.tickets_by_severity.map((row) => ({ label: reportLabel(row.label), value: String(row.count) }))} />
            <ReportList title="TICKETS POR ESTADO" rows={maintenanceStats.tickets_by_status.map((row) => ({ label: reportLabel(row.label), value: String(row.count) }))} />
            <ReportList title="FLOTA POR ESTADO" rows={maintenanceStats.equipment_by_status.map((row) => ({ label: reportLabel(row.label), value: String(row.count) }))} />
          </section>
        </>
      ) : <ReportFallback loading={loading} error={error} />)}

      {tab === "inventory" && (inventoryStats ? (
        <>
          <section className="panel full-panel">
            <div className="panel-header access-list-heading">
              <div><p className="section-kicker">INVENTARIO</p><h2>Valor del inventario</h2></div>
              <span className="chart-legend">Corte actual: el periodo aplica a movimientos y compras</span>
            </div>
            <div className="report-stat-grid">
              <ReportStat label="Valor al costo" value={formatMoney(inventoryStats.stock_value_cents)} hint={`${inventoryStats.stock_units} unidades en existencia`} />
              <ReportStat label="Valor a precio de venta" value={formatMoney(inventoryStats.retail_value_cents)} hint="Potencial si se vende todo el stock" />
              <ReportStat label="Productos activos" value={String(inventoryStats.products_active)} hint={`${inventoryStats.products_inactive} inactivos de ${inventoryStats.products_total}`} />
              <ReportStat label="Bajo mínimo" value={String(inventoryStats.low_stock)} hint="Activos en o por debajo de su mínimo" />
              <ReportStat label="Agotados" value={String(inventoryStats.out_of_stock)} hint="Activos sin existencia" />
              <ReportStat label="Proveedores" value={String(inventoryStats.suppliers_active)} hint={`${inventoryStats.suppliers_total} registrados`} />
              <ReportStat label="Órdenes abiertas" value={String(inventoryStats.open_orders)} hint={`${formatMoney(inventoryStats.open_orders_value_cents)} comprometidos`} />
            </div>
          </section>

          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">DEL PERIODO</p><h2>Movimientos y compras</h2></div></div>
            <div className="report-stat-grid">
              <ReportStat label="Movimientos de inventario" value={String(inventoryStats.movements_count)} hint={`${inventoryStats.units_in} unidades entraron · ${inventoryStats.units_out} salieron`} />
              <ReportStat label="Órdenes creadas" value={String(inventoryStats.orders_created)} hint={formatMoney(inventoryStats.orders_value_cents)} />
              <ReportStat label="Órdenes recibidas" value={String(inventoryStats.orders_received)} hint={formatMoney(inventoryStats.orders_received_value_cents)} />
            </div>
          </section>

          <section className="panel full-panel">
            <div className="panel-header access-list-heading"><div><p className="section-kicker">VALOR POR PRODUCTO</p><h2>Existencias</h2></div></div>
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr><th>PRODUCTO</th><th>CATEGORÍA</th><th>EXISTENCIA</th><th>COSTO</th><th>VALOR AL COSTO</th><th>VALOR A VENTA</th></tr></thead>
                <tbody>
                  {inventoryStats.by_product.length === 0
                    ? <tr><td colSpan={6} className="empty-row">Aún no hay productos registrados.</td></tr>
                    : inventoryStats.by_product.map((item) => (
                      <tr key={item.product_id}>
                        <td><div className="person-cell"><span className="pos-row-icon"><Package size={15} /></span><span><strong>{item.name}</strong><small>{item.sku}</small></span></div></td>
                        <td>{item.category}</td>
                        <td>{item.quantity <= 0 ? <span className="status-badge status-bad"><i />Agotado</span> : item.quantity}</td>
                        <td>{formatMoney(item.cost_cents)}</td>
                        <td>{formatMoney(item.cost_value_cents)}</td>
                        <td>{formatMoney(item.retail_value_cents)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            {inventoryStats.by_product.length > 0 && (
              <div className="table-bottom">
                <span>{inventoryStats.by_product.length} productos valorizados</span>
                <span>Al costo {formatMoney(inventoryStats.stock_value_cents)} · a venta {formatMoney(inventoryStats.retail_value_cents)}</span>
              </div>
            )}
          </section>

          <section className="report-columns">
            <ReportList title="VALOR POR CATEGORÍA" rows={inventoryStats.by_category.map((row) => ({ label: `${row.label} (${row.count} u.)`, value: formatMoney(row.amount_cents) }))} />
            <ReportList title="MOVIMIENTOS DEL PERIODO" rows={inventoryStats.movements_by_type.map((row) => ({ label: `${reportMovementLabels[row.label] ?? row.label} (${row.movements})`, value: row.units >= 0 ? `+${row.units}` : String(row.units) }))} />
            <ReportList title="ÓRDENES POR ESTADO" rows={inventoryStats.orders_by_status.map((row) => ({ label: purchaseOrderStatusLabels[row.label] ?? row.label, value: String(row.count) }))} />
            <ReportList title="COMPRAS POR PROVEEDOR" rows={inventoryStats.by_supplier.map((row) => ({ label: `${row.label} (${row.count})`, value: formatMoney(row.amount_cents) }))} />
          </section>
        </>
      ) : <ReportFallback loading={loading} error={error} />)}
    </>
  );
}

function billingEventLabel(eventType: string): string {
  const labels: Record<string, string> = {
    invoice_requested: "Solicitud registrada",
    invoice_stamped: "Comprobante timbrado",
    invoice_stamp_failed: "Intento de timbrado fallido",
    invoice_cancelled: "Comprobante cancelado",
    invoice_cancellation_pending: "Cancelación en proceso en el SAT",
    invoice_cancellation_confirmed: "Cancelación confirmada por el SAT",
    invoice_cancellation_cleared: "El SAT no canceló el comprobante",
    invoice_email_sent: "Factura enviada por correo",
    invoice_email_failed: "Envío de factura fallido",
  };
  return labels[eventType] ?? eventType;
}

function billingEventValue(event: BillingInvoiceEvent, key: string): string | null {
  const value = event.detail?.[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : null;
}

function BillingView({ permissions, onUnauthorized, onToast }: { permissions: string[]; onUnauthorized: () => void; onToast: (message: string) => void }) {
  const canRequest = permissions.includes("billing.request");
  const canManage = permissions.includes("billing.manage");

  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [directory, setDirectory] = useState<BillingInvoicePage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | BillingInvoiceStatus>("");
  const [originFilter, setOriginFilter] = useState<"" | BillingOriginType>("");
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [newInvoiceOpen, setNewInvoiceOpen] = useState(false);
  const [activeInvoiceId, setActiveInvoiceId] = useState<string | null>(null);
  const [stampingId, setStampingId] = useState<string | null>(null);
  const [tab, setTab] = useState<"invoices" | "global" | "receivables">("invoices");

  useEffect(() => {
    const handle = window.setTimeout(() => setQuery(search.trim()), 300);
    return () => window.clearTimeout(handle);
  }, [search]);

  useEffect(() => { setPage(1); }, [query, statusFilter, originFilter]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ page: String(page), page_size: String(BILLING_PAGE_SIZE) });
        if (query) params.set("search", query);
        if (statusFilter) params.set("status", statusFilter);
        if (originFilter) params.set("origin_type", originFilter);
        const [summaryResponse, listResponse] = await Promise.all([
          fetch("/api/admin/billing/summary", { cache: "no-store" }),
          fetch(`/api/admin/billing/invoices?${params.toString()}`, { cache: "no-store" }),
        ]);
        if (summaryResponse.status === 401 || listResponse.status === 401) { onUnauthorized(); return; }
        if (!summaryResponse.ok || !listResponse.ok) throw new Error("No se pudo consultar la facturación.");
        const summaryPayload = await summaryResponse.json() as BillingSummary;
        const listPayload = await listResponse.json() as BillingInvoicePage;
        if (!active) return;
        setSummary(summaryPayload);
        setDirectory(listPayload);
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "Error al cargar la facturación.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [onUnauthorized, originFilter, page, query, refresh, statusFilter]);

  const invoices = directory?.items ?? [];
  const total = directory?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / BILLING_PAGE_SIZE));

  const stampInvoice = async (invoice: BillingInvoice) => {
    setStampingId(invoice.id);
    setError("");
    try {
      const response = await fetch(`/api/admin/billing/invoices/${encodeURIComponent(invoice.id)}/stamp`, { method: "POST" });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo timbrar el comprobante."));
        return;
      }
      const updated = await response.json() as BillingInvoice;
      setRefresh((value) => value + 1);
      onToast(updated.is_simulated ? `Comprobante ${updated.folio_label} timbrado en modo simulación.` : `Comprobante ${updated.folio_label} timbrado.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setStampingId(null);
    }
  };

  const statusFilters: { value: "" | BillingInvoiceStatus; label: string }[] = [
    { value: "", label: "Todas" },
    { value: "requested", label: "Solicitadas" },
    { value: "stamped", label: "Timbradas" },
    { value: "failed", label: "Con error" },
    { value: "cancelled", label: "Canceladas" },
  ];

  return (
    <>
      <section className="access-summary-band pos-cash-band">
        <div className="access-summary-main">
          <span className="summary-icon"><Receipt size={18} /></span>
          <div>
            <span>FACTURACIÓN ELECTRÓNICA</span>
            <strong>{summary ? `${summary.total} comprobantes · ${summary.stamped} timbrados · ${summary.cancelled} cancelados` : "Consultando comprobantes…"}</strong>
            <small className="report-timezone">CFDI 4.0 · el timbrado en vista previa es simulado y no tiene validez fiscal</small>
          </div>
        </div>
        <div className="summary-divider" />
        <div className="summary-stat"><span>POR TIMBRAR</span><strong>{summary ? summary.requested + summary.failed : "—"}</strong></div>
        <div className="summary-stat"><span>TIMBRADAS</span><strong>{summary?.stamped ?? "—"}</strong></div>
        <div className="summary-stat"><span>NOTAS DE CRÉDITO</span><strong>{summary?.credit_notes ?? "—"}</strong></div>
        <div className="summary-stat"><span>IMPORTE NETO</span><strong title={summary ? `Timbrado ${formatMoney(summary.stamped_cents)} − notas ${formatMoney(summary.credit_note_cents)}` : undefined}>{summary ? formatMoney(summary.net_stamped_cents) : "—"}</strong>{summary && summary.credit_note_cents > 0 && <small>Notas por {formatMoney(summary.credit_note_cents)}</small>}</div>
        {canRequest && tab === "invoices" && <button className="button button-primary" onClick={() => setNewInvoiceOpen(true)}><Plus size={17} />Nueva factura</button>}
      </section>

      <div className="staff-tabs pos-tabs billing-view-tabs">
        <button type="button" className={tab === "invoices" ? "staff-tab-active" : ""} onClick={() => setTab("invoices")}>Comprobantes</button>
        <button type="button" className={tab === "global" ? "staff-tab-active" : ""} onClick={() => setTab("global")}>Factura global</button>
        <button type="button" className={tab === "receivables" ? "staff-tab-active" : ""} onClick={() => setTab("receivables")}>Cartera PPD</button>
        <span className="staff-tabs-note"><ShieldCheck size={14} />{tab === "invoices" ? "Solicitud, timbrado, entrega y cancelación" : tab === "global" ? "Un CFDI mensual para ventas al público en general" : "Saldo por antigüedad y complementos timbrados frente a solicitados"}</span>
      </div>

      {tab === "invoices" ? (
        <>
          {error && <div className="billing-alert" role="alert">{error}</div>}

          <section className="panel full-panel">
        <div className="panel-header access-list-heading">
          <div><p className="section-kicker">COMPROBANTES FISCALES</p><h2>Facturas</h2></div>
          {summary !== null && summary.simulated > 0 && <span className="status-badge status-warn"><i />{summary.simulated} simuladas</span>}
          {summary !== null && summary.pending_cancellations > 0 && <span className="status-badge status-warn"><i />{summary.pending_cancellations} en proceso en el SAT</span>}
        </div>
        <div className="table-toolbar">
          <label className="table-search"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar por receptor, RFC u operación" /></label>
          <label className="table-select"><span>Estado</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as "" | BillingInvoiceStatus)}>{statusFilters.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
          <label className="table-select"><span>Tipo</span><select value={originFilter} onChange={(event) => setOriginFilter(event.target.value as "" | BillingOriginType)}><option value="">Todos</option>{(Object.keys(billingOriginLabels) as BillingOriginType[]).map((type) => <option key={type} value={type}>{billingOriginLabels[type]}</option>)}</select></label>
          <span className="table-hint">Una factura cancelada conserva su folio y libera la operación para un reemplazo</span>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>FOLIO</th><th>RECEPTOR</th><th>OPERACIÓN</th><th>FECHA</th><th>TOTAL</th><th>ESTADO</th><th /></tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={7} className="empty-row">Cargando comprobantes…</td></tr>
                : invoices.length === 0 ? <tr><td colSpan={7} className="empty-row">{query || statusFilter ? "No hay comprobantes que coincidan con el filtro." : "Aún no se ha solicitado ninguna factura."}</td></tr>
                : invoices.map((invoice) => {
                  const status = billingInvoiceStatus(invoice.status);
                  return (
                    <tr key={invoice.id}>
                      <td><strong>{invoice.folio_label}</strong>{invoice.is_simulated && <small className="billing-inline-note">Simulada</small>}</td>
                      <td><div className="person-cell"><span className="pos-row-icon"><Receipt size={15} /></span><span><strong>{invoice.receptor_name}</strong><small>{invoice.receptor_rfc}</small></span></div></td>
                      <td><strong>{billingOriginLabels[invoice.origin_type]}</strong><small className="billing-inline-note">{invoice.origin_type === "credit_note" && invoice.related_invoice_folio_label ? `Sobre ${invoice.related_invoice_folio_label}` : invoice.origin_reference}</small></td>
                      <td className="time-cell">{formatMoment(invoice.created_at)}</td>
                      <td>{invoice.origin_type === "credit_note" ? `−${formatMoney(invoice.total_cents)}` : formatMoney(invoice.total_cents)}</td>
                      <td><span className={`status-badge ${billingStatusBadges[status]}`}><i />{billingStatusLabels[status]}</span>{invoice.cancellation_pending && <small className="billing-inline-note">Cancelación en proceso</small>}</td>
                      <td>
                        <div className="pos-row-actions">
                          <button className="button button-secondary button-small" onClick={() => setActiveInvoiceId(invoice.id)}>Ver</button>
                          {canManage && (status === "requested" || status === "failed") && (
                            <button className="button button-primary button-small" disabled={stampingId === invoice.id} onClick={() => void stampInvoice(invoice)}>{stampingId === invoice.id ? "Timbrando…" : "Timbrar"}</button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
        <div className="table-bottom">
          <span>{total} {total === 1 ? "comprobante" : "comprobantes"}</span>
          {pages > 1 && (
            <span className="member-pagination">
              <span>Página {page} de {pages}</span>
              <button type="button" aria-label="Página anterior" disabled={page <= 1} onClick={() => setPage(Math.max(1, page - 1))}>‹</button>
              <button type="button" aria-label="Página siguiente" disabled={page >= pages} onClick={() => setPage(Math.min(pages, page + 1))}>›</button>
            </span>
          )}
        </div>
      </section>
        </>
      ) : tab === "global" ? (
        <GlobalInvoicePanel
          canManage={canManage}
          refreshToken={refresh}
          onOpenInvoice={setActiveInvoiceId}
          onChanged={() => setRefresh((value) => value + 1)}
          onUnauthorized={onUnauthorized}
          onToast={onToast}
        />
      ) : (
        <PpdReceivablesPanel
          refreshToken={refresh}
          onOpenInvoice={setActiveInvoiceId}
          onUnauthorized={onUnauthorized}
        />
      )}
      <footer className="page-footer"><span>Centro Fit · Facturación CFDI 4.0</span><span>{tab === "global" ? "FACTURA GLOBAL MENSUAL · PÚBLICO EN GENERAL" : tab === "receivables" ? "CARTERA PPD · SALDO POR ANTIGÜEDAD" : canManage ? "SOLICITUD, TIMBRADO Y CANCELACIÓN" : "CONSULTA DE COMPROBANTES"}</span></footer>

      {newInvoiceOpen && (
        <NewInvoiceModal
          canManage={canManage}
          onClose={() => setNewInvoiceOpen(false)}
          onCreated={(message, invoice) => {
            setNewInvoiceOpen(false);
            setRefresh((value) => value + 1);
            if (invoice) setActiveInvoiceId(invoice.id);
            onToast(message);
          }}
          onUnauthorized={onUnauthorized}
        />
      )}
      {activeInvoiceId && (
        <InvoiceDetailModal
          key={activeInvoiceId}
          invoiceId={activeInvoiceId}
          canManage={canManage}
          canRequest={canRequest}
          onOpenInvoice={setActiveInvoiceId}
          onClose={() => setActiveInvoiceId(null)}
          onChanged={(message) => { setRefresh((value) => value + 1); onToast(message); }}
          onUnauthorized={onUnauthorized}
        />
      )}
    </>
  );
}

function PpdReceivablesPanel({ refreshToken, onOpenInvoice, onUnauthorized }: { refreshToken: number; onOpenInvoice: (invoiceId: string) => void; onUnauthorized: () => void }) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [bucket, setBucket] = useState<"" | BillingPpdAgingBucket>("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<BillingPpdReceivablePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const handle = window.setTimeout(() => setQuery(search.trim()), 300);
    return () => window.clearTimeout(handle);
  }, [search]);

  useEffect(() => { setPage(1); }, [bucket, query]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ page: String(page), page_size: String(BILLING_PPD_PAGE_SIZE) });
        if (query) params.set("search", query);
        if (bucket) params.set("aging_bucket", bucket);
        const response = await fetch(`/api/admin/billing/receivables?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(billingErrorDetail(payload, "No se pudo consultar la cartera PPD."));
        }
        const payload = await response.json() as BillingPpdReceivablePage;
        if (active) setData(payload);
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "Error al consultar la cartera PPD.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [bucket, onUnauthorized, page, query, refreshToken]);

  const rows = data?.items ?? [];
  const summary = data?.summary ?? null;
  const aging = summary?.aging;
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / BILLING_PPD_PAGE_SIZE));
  const pendingComplements = summary ? summary.requested_complements + summary.failed_complements : 0;
  const pendingCents = summary ? summary.requested_complement_cents + summary.failed_complement_cents : 0;

  return (
    <section className="panel full-panel billing-ppd-panel">
      <div className="panel-header access-list-heading">
        <div><p className="section-kicker">COBRANZA PPD · SALDO POR ANTIGÜEDAD</p><h2>Cartera de complementos de pago</h2></div>
        {summary && <span className="status-badge status-neutral"><i />Al {formatDateOnly(summary.as_of)}</span>}
      </div>
      <p className="panel-hint">Solo se listan facturas PPD timbradas con saldo pendiente. La antigüedad corre desde el timbrado y el saldo baja únicamente con complementos timbrados; los solicitados o con error se muestran aparte.</p>

      {error && <div className="billing-alert" role="alert">{error}</div>}

      <div className="billing-totals billing-ppd-summary">
        <div><span>FACTURAS CON SALDO</span><strong>{summary ? summary.invoices : "—"}</strong><small>PPD timbradas y vigentes</small></div>
        <div><span>SALDO PENDIENTE</span><strong>{summary ? formatMoney(summary.outstanding_cents) : "—"}</strong><small>IVA incluido · cobrado + saldo = facturado</small></div>
        <div><span>COBRADO</span><strong>{summary ? formatMoney(summary.paid_cents) : "—"}</strong><small>{summary ? `${summary.stamped_complements} ${summary.stamped_complements === 1 ? "complemento timbrado" : "complementos timbrados"}` : "En facturas con saldo"}</small></div>
        <div><span>POR TIMBRAR</span><strong>{summary ? pendingComplements : "—"}</strong><small>{summary ? `${formatMoney(pendingCents)} · ${summary.requested_complements} solicitados · ${summary.failed_complements} con error` : "Complementos pendientes"}</small></div>
        <div><span>FACTURADO VIGENTE</span><strong>{summary ? formatMoney(summary.total_cents) : "—"}</strong><small>Facturas abiertas de la cartera</small></div>
        <div><span>ANTIGÜEDAD MÁXIMA</span><strong>{summary?.oldest_stamped_at ? formatDateOnly(summary.oldest_stamped_at) : "—"}</strong><small>{summary?.oldest_stamped_at ? "Timbrado más antiguo con saldo" : "Sin facturas con saldo"}</small></div>
      </div>

      <div className="pos-aging-grid" role="group" aria-label="Antigüedad de la cartera PPD">
        <div className="summary-stat"><span>0–30 DÍAS</span><strong>{formatMoney(aging?.current_cents ?? 0)}</strong><small>corriente</small></div>
        <div className="summary-stat"><span>31–60 DÍAS</span><strong>{formatMoney(aging?.days_31_60_cents ?? 0)}</strong><small>por vencer</small></div>
        <div className="summary-stat"><span>61–90 DÍAS</span><strong>{formatMoney(aging?.days_61_90_cents ?? 0)}</strong><small>atrasado</small></div>
        <div className="summary-stat"><span>+90 DÍAS</span><strong className="stat-orange">{formatMoney(aging?.over_90_cents ?? 0)}</strong><small>antigüedad crítica</small></div>
        <div className="summary-stat"><span>TOTAL CARTERA</span><strong>{formatMoney(summary?.outstanding_cents ?? 0)}</strong><small>suma de los tramos</small></div>
      </div>

      <div className="table-toolbar">
        <label className="table-search"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar por receptor, RFC, folio u operación" /></label>
        <label className="table-select"><span>Tramo</span><select value={bucket} onChange={(event) => setBucket(event.target.value as "" | BillingPpdAgingBucket)}>{BILLING_PPD_AGING_FILTERS.map(([value, label]) => <option key={value || "all"} value={value}>{label}</option>)}</select></label>
        <span className="table-hint">Los complementos solicitados o con error no reducen el saldo hasta timbrarse</span>
      </div>
      <div className="table-scroll">
        <table className="data-table compact-table">
          <thead><tr><th>FOLIO</th><th>RECEPTOR</th><th>OPERACIÓN</th><th>TIMBRADO</th><th>ANTIGÜEDAD</th><th>TOTAL</th><th>COBRADO</th><th>SALDO</th><th>COMPLEMENTOS</th><th /></tr></thead>
          <tbody>
            {loading ? <tr><td colSpan={10} className="empty-row">Cargando cartera PPD…</td></tr>
              : rows.length === 0 ? <tr><td colSpan={10} className="empty-row">{query || bucket ? "No hay facturas PPD que coincidan con el filtro." : "No hay facturas PPD timbradas con saldo pendiente."}</td></tr>
              : rows.map((row) => (
                <tr key={row.invoice_id}>
                  <td><strong>{row.folio_label}</strong>{row.is_simulated && <small className="billing-inline-note">Simulada</small>}</td>
                  <td><div className="person-cell"><span className="pos-row-icon"><Receipt size={15} /></span><span><strong>{row.receptor_name}</strong><small>{row.receptor_rfc}</small></span></div></td>
                  <td><strong>{billingOriginLabels[row.origin_type]}</strong><small className="billing-inline-note">{row.origin_reference}</small></td>
                  <td className="time-cell">{formatMoment(row.stamped_at)}</td>
                  <td><span className={`status-badge ${billingPpdAgingBadges[row.aging_bucket]}`}><i />{row.age_days} días · {billingPpdAgingLabels[row.aging_bucket]}</span></td>
                  <td>{formatMoney(row.total_cents)}</td>
                  <td>{formatMoney(row.paid_cents)}{row.last_payment_on && <small className="billing-inline-note">Último {formatDateOnly(row.last_payment_on)}</small>}</td>
                  <td><strong>{formatMoney(row.balance_cents)}</strong></td>
                  <td><strong>{row.stamped_complements}</strong> timbrados<small className="billing-inline-note">{row.requested_complements + row.failed_complements > 0 ? `${row.requested_complements} solicitados · ${row.failed_complements} con error` : "Sin pendientes"}</small></td>
                  <td><div className="pos-row-actions"><button className="button button-secondary button-small" onClick={() => onOpenInvoice(row.invoice_id)}>Ver</button></div></td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <div className="table-bottom">
        <span>{total} {total === 1 ? "factura con saldo" : "facturas con saldo"}</span>
        {pages > 1 && (
          <span className="member-pagination">
            <span>Página {page} de {pages}</span>
            <button type="button" aria-label="Página anterior" disabled={page <= 1} onClick={() => setPage(Math.max(1, page - 1))}>‹</button>
            <button type="button" aria-label="Página siguiente" disabled={page >= pages} onClick={() => setPage(Math.min(pages, page + 1))}>›</button>
          </span>
        )}
      </div>
    </section>
  );
}

function GlobalInvoicePanel({ canManage, refreshToken, onOpenInvoice, onChanged, onUnauthorized, onToast }: { canManage: boolean; refreshToken: number; onOpenInvoice: (invoiceId: string) => void; onChanged: () => void; onUnauthorized: () => void; onToast: (message: string) => void }) {
  const periods = useMemo(() => billingGlobalPeriodOptions(), []);
  const [period, setPeriod] = useState(() => {
    const initial = defaultBillingGlobalPeriod();
    return billingGlobalPeriodValue(initial.year, initial.month);
  });
  const [page, setPage] = useState(1);
  const [data, setData] = useState<BillingGlobalEligibility | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [stampNow, setStampNow] = useState(true);
  const [idempotencyKey, setIdempotencyKey] = useState(() => globalThis.crypto.randomUUID());
  const [history, setHistory] = useState<BillingInvoice[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");

  const periodYear = Number(period.slice(0, 4));
  const periodMonth = Number(period.slice(5, 7));

  const changePeriod = (value: string) => {
    setPeriod(value);
    setPage(1);
    setIdempotencyKey(globalThis.crypto.randomUUID());
  };

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ year: String(periodYear), month: String(periodMonth), page: String(page), page_size: "10" });
        const response = await fetch(`/api/admin/billing/global-invoices/eligible?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(billingErrorDetail(payload, "No se pudieron consultar las ventas del periodo."));
        }
        const payload = await response.json() as BillingGlobalEligibility;
        if (active) setData(payload);
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "Error al consultar el periodo.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [onUnauthorized, page, periodMonth, periodYear, refreshToken]);

  useEffect(() => {
    if (!data) return;
    const lastPage = Math.max(1, Math.ceil(data.eligible_count / data.page_size));
    if (page > lastPage) setPage(lastPage);
  }, [data, page]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setHistoryLoading(true);
      setHistoryError("");
      try {
        const response = await fetch("/api/admin/billing/invoices?search=global&page=1&page_size=50", { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("No se pudo consultar el historial de facturas globales.");
        const payload = await response.json() as BillingInvoicePage;
        if (active) setHistory(payload.items.filter((invoice) => invoice.origin_type === "global"));
      } catch (caught) {
        if (active) setHistoryError(caught instanceof Error ? caught.message : "Error al consultar el historial.");
      } finally {
        if (active) setHistoryLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [onUnauthorized, refreshToken]);

  const createGlobalInvoice = async () => {
    if (!data) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/billing/global-invoices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ year: data.year, month: data.month, idempotency_key: idempotencyKey }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo emitir la factura global."));
        return;
      }
      const body = await response.json() as { invoice: BillingInvoice; idempotent_replay: boolean };
      let invoice = body.invoice;
      let message = body.idempotent_replay
        ? `La factura global ${invoice.folio_label} ya existía; se muestra el comprobante original.`
        : `Factura global ${invoice.folio_label} solicitada para ${billingGlobalPeriodLabel(data.year, data.month)}.`;

      if (stampNow && (invoice.status === "requested" || invoice.status === "failed")) {
        const stampResponse = await fetch(`/api/admin/billing/invoices/${encodeURIComponent(invoice.id)}/stamp`, { method: "POST" });
        if (stampResponse.status === 401) { onUnauthorized(); return; }
        if (stampResponse.ok) {
          invoice = await stampResponse.json() as BillingInvoice;
          message = invoice.is_simulated
            ? `Factura global ${invoice.folio_label} timbrada en modo simulación.`
            : `Factura global ${invoice.folio_label} timbrada.`;
        } else {
          const payload = await stampResponse.json().catch(() => ({}));
          message = `Factura global ${invoice.folio_label} solicitada, pero no se pudo timbrar: ${billingErrorDetail(payload, "error del PAC.")}`;
        }
      }
      setIdempotencyKey(globalThis.crypto.randomUUID());
      onToast(message);
      onChanged();
      onOpenInvoice(invoice.id);
    } catch {
      setError("No se pudo conectar con el backend. Reintenta con la misma solicitud.");
    } finally {
      setBusy(false);
    }
  };

  const pages = Math.max(1, Math.ceil((data?.eligible_count ?? 0) / (data?.page_size ?? 10)));
  const excluded = Object.entries(data?.excluded_counts ?? {}).filter(([, count]) => count > 0);
  const canCreate = canManage && data !== null && data.period_closed && data.eligible_count > 0 && data.existing_invoice === null;

  return (
    <>
      <section className="panel full-panel billing-global-panel">
        <div className="panel-header access-list-heading">
          <div><p className="section-kicker">CFDI 4.0 · PÚBLICO EN GENERAL</p><h2>Factura global mensual</h2></div>
          {data && <span className={`status-badge ${data.period_closed ? "status-neutral" : "status-warn"}`}><i />{data.period_closed ? "Periodo cerrado" : "Periodo en curso"}</span>}
        </div>
        <p className="panel-hint">Agrupa en un solo comprobante las ventas de mostrador sin socio, sin devolución y sin factura individual. La elegibilidad se recalcula al emitir, así que una venta facturada por separado queda fuera.</p>
        <div className="table-toolbar billing-global-toolbar">
          <label className="table-select">
            <span>Periodo</span>
            <select value={period} onChange={(event) => changePeriod(event.target.value)}>
              {periods.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <span className="table-hint">Receptor fijo: XAXX010101000 · Público en general · Uso S01</span>
        </div>

        {error && <div className="billing-alert" role="alert">{error}</div>}
        {loading ? <p className="billing-empty">Consultando ventas del periodo…</p> : !data ? null : (
          <>
            <div className="billing-totals billing-global-summary">
              <div><span>VENTAS DEL PERIODO</span><strong>{data.total_candidates}</strong><small>{billingGlobalPeriodLabel(data.year, data.month)}</small></div>
              <div><span>ELEGIBLES</span><strong>{data.eligible_count}</strong><small>Público en general</small></div>
              <div><span>TOTAL A FACTURAR</span><strong>{formatMoney(data.eligible_total_cents)}</strong><small>IVA incluido</small></div>
              <div><span>SUBTOTAL</span><strong>{formatMoney(data.subtotal_cents)}</strong><small>Base gravable</small></div>
              <div><span>IVA</span><strong>{formatMoney(data.tax_cents)}</strong><small>Traslado federal</small></div>
              <div><span>ESTADO</span><strong>{data.period_closed ? "Cerrado" : "Abierto"}</strong><small>{data.period_closed ? "Listo para emitir" : "Espera el cierre del mes"}</small></div>
            </div>

            {!data.period_closed && (
              <div className="billing-simulated-note"><Clock3 size={16} /><span>Solo se puede emitir la factura global de un mes ya cerrado. Este periodo estará disponible a partir del {formatMoment(data.period_end)}</span></div>
            )}

            {data.existing_invoice && (
              <div className="billing-global-existing">
                <ShieldCheck size={16} />
                <div>
                  <strong>El periodo ya tiene una factura global vigente: {data.existing_invoice.folio_label}.</strong>
                  <small>Para rehacerla, cancela ese comprobante; el periodo y sus ventas quedarán libres para una sustitución.</small>
                </div>
                <button type="button" className="button button-secondary button-small" onClick={() => onOpenInvoice(data.existing_invoice!.invoice_id)}>Ver comprobante</button>
              </div>
            )}

            {excluded.length > 0 && (
              <div className="billing-global-exclusions">
                <span>Excluidas del periodo</span>
                {excluded.map(([key, count]) => <span className="billing-global-chip" key={key}>{billingGlobalExclusionLabels[key] ?? key} · {count}</span>)}
              </div>
            )}

            <div className="table-scroll">
              <table className="data-table compact-table">
                <thead><tr><th>FOLIO</th><th>FECHA</th><th>DESCRIPCIÓN</th><th>MÉTODO</th><th>TOTAL</th></tr></thead>
                <tbody>
                  {data.items.length === 0 ? <tr><td colSpan={5} className="empty-row">{data.period_closed ? "No hay ventas elegibles en este periodo." : "Aún no hay ventas elegibles en el mes en curso."}</td></tr>
                    : data.items.map((sale) => (
                      <tr key={sale.sale_id}>
                        <td><strong>{sale.folio}</strong></td>
                        <td className="time-cell">{formatMoment(sale.sold_at)}</td>
                        <td>{sale.description}</td>
                        <td>{billingPaymentMethodLabels[sale.payment_method] ?? sale.payment_method}</td>
                        <td>{formatMoney(sale.total_cents)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <div className="table-bottom">
              <span>{data.eligible_count} {data.eligible_count === 1 ? "venta elegible" : "ventas elegibles"} de {data.total_candidates} del periodo</span>
              {pages > 1 && (
                <span className="member-pagination">
                  <span>Página {page} de {pages}</span>
                  <button type="button" aria-label="Página anterior" disabled={page <= 1} onClick={() => setPage(Math.max(1, page - 1))}>‹</button>
                  <button type="button" aria-label="Página siguiente" disabled={page >= pages} onClick={() => setPage(Math.min(pages, page + 1))}>›</button>
                </span>
              )}
            </div>

            <div className="billing-global-actionbar">
              {canManage ? (
                <label className="form-check"><input type="checkbox" checked={stampNow} onChange={(event) => setStampNow(event.target.checked)} /><span>Solicitar y timbrar ahora. En vista previa el comprobante queda marcado como simulado y sin validez fiscal.</span></label>
              ) : (
                <p className="billing-empty">La emisión requiere el permiso de gestión fiscal. Puedes revisar el periodo y consultar los comprobantes existentes.</p>
              )}
              {canManage && (
                <button type="button" className="button button-primary" onClick={() => void createGlobalInvoice()} disabled={!canCreate || busy}>
                  <Receipt size={16} />{busy ? "Procesando…" : "Emitir factura global"}
                </button>
              )}
            </div>
          </>
        )}
      </section>

      <section className="panel full-panel billing-global-history">
        <div className="panel-header access-list-heading">
          <div><p className="section-kicker">HISTORIAL</p><h2>Facturas globales</h2></div>
          {historyLoading && <span className="billing-empty">Consultando…</span>}
        </div>
        {historyError && <div className="billing-alert" role="alert">{historyError}</div>}
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>FOLIO</th><th>PERIODO</th><th>RECEPTOR</th><th>EMITIDA</th><th>TOTAL</th><th>ESTADO</th><th /></tr></thead>
            <tbody>
              {historyLoading ? <tr><td colSpan={7} className="empty-row">Cargando facturas globales…</td></tr>
                : history.length === 0 ? <tr><td colSpan={7} className="empty-row">Aún no se ha emitido ninguna factura global.</td></tr>
                : history.map((invoice) => {
                  const status = billingInvoiceStatus(invoice.status);
                  return (
                    <tr key={invoice.id}>
                      <td><strong>{invoice.folio_label}</strong>{invoice.is_simulated && <small className="billing-inline-note">Simulada</small>}</td>
                      <td><strong>{invoice.global_year && invoice.global_month ? billingGlobalPeriodLabel(invoice.global_year, invoice.global_month) : invoice.origin_reference}</strong></td>
                      <td>{invoice.receptor_name}<small className="billing-inline-note">{invoice.receptor_rfc}</small></td>
                      <td className="time-cell">{formatMoment(invoice.created_at)}</td>
                      <td>{formatMoney(invoice.total_cents)}</td>
                      <td><span className={`status-badge ${billingStatusBadges[status]}`}><i />{billingStatusLabels[status]}</span></td>
                      <td><div className="pos-row-actions"><button className="button button-secondary button-small" onClick={() => onOpenInvoice(invoice.id)}>Ver</button></div></td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function NewInvoiceModal({ canManage, onClose, onCreated, onUnauthorized }: { canManage: boolean; onClose: () => void; onCreated: (message: string, invoice: BillingInvoice | null) => void; onUnauthorized: () => void }) {
  const [originType, setOriginType] = useState<BillingOrigin["origin_type"]>("sale");
  const [originSearch, setOriginSearch] = useState("");
  const [originQuery, setOriginQuery] = useState("");
  const [originPage, setOriginPage] = useState(1);
  const [origins, setOrigins] = useState<BillingOriginPage | null>(null);
  const [originsLoading, setOriginsLoading] = useState(false);
  const [originsError, setOriginsError] = useState("");
  const [selectedOrigin, setSelectedOrigin] = useState<BillingOrigin | null>(null);

  const [rfc, setRfc] = useState("");
  const [legalName, setLegalName] = useState("");
  const [taxRegime, setTaxRegime] = useState("612");
  const [postalCode, setPostalCode] = useState("");
  const [cfdiUse, setCfdiUse] = useState("G03");
  const [email, setEmail] = useState("");
  const [paymentForm, setPaymentForm] = useState("01");
  const [paymentMethod, setPaymentMethod] = useState<"PUE" | "PPD">("PUE");
  const [profileState, setProfileState] = useState<"idle" | "loading" | "found" | "empty">("idle");
  const [saveProfile, setSaveProfile] = useState(false);
  const [stampNow, setStampNow] = useState(canManage);
  const [idempotencyKey, setIdempotencyKey] = useState(() => globalThis.crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const rotateKey = () => setIdempotencyKey(globalThis.crypto.randomUUID());

  useEffect(() => {
    const handle = window.setTimeout(() => setOriginQuery(originSearch.trim()), 300);
    return () => window.clearTimeout(handle);
  }, [originSearch]);

  useEffect(() => { setOriginPage(1); }, [originQuery, originType]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setOriginsLoading(true);
      setOriginsError("");
      try {
        const params = new URLSearchParams({ origin_type: originType, page: String(originPage), page_size: "10" });
        if (originQuery) params.set("search", originQuery);
        const response = await fetch(`/api/admin/billing/origins?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("No se pudieron consultar las operaciones facturables.");
        const payload = await response.json() as BillingOriginPage;
        if (active) setOrigins(payload);
      } catch (caught) {
        if (active) setOriginsError(caught instanceof Error ? caught.message : "Error al consultar las operaciones.");
      } finally {
        if (active) setOriginsLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [onUnauthorized, originPage, originQuery, originType]);

  useEffect(() => {
    if (!selectedOrigin) return;
    setPaymentForm(BILLING_PAYMENT_FORM_BY_METHOD[selectedOrigin.payment_method] ?? "01");
    setSaveProfile(false);
    rotateKey();
    if (!selectedOrigin.member_id) {
      setRfc("");
      setLegalName("");
      setTaxRegime("612");
      setPostalCode("");
      setCfdiUse("G03");
      setEmail("");
      setProfileState("empty");
      return;
    }
    let active = true;
    setProfileState("loading");
    fetch(`/api/admin/members/${encodeURIComponent(selectedOrigin.member_id)}/fiscal-profile`, { cache: "no-store" })
      .then(async (response) => {
        if (response.status === 401) { onUnauthorized(); return null; }
        if (response.status === 404) return null;
        if (!response.ok) throw new Error("profile");
        return await response.json() as BillingFiscalProfile;
      })
      .then((profile) => {
        if (!active) return;
        if (profile) {
          setRfc(profile.rfc);
          setLegalName(profile.legal_name);
          setTaxRegime(profile.tax_regime);
          setPostalCode(profile.postal_code);
          setCfdiUse(profile.cfdi_use);
          setEmail(profile.email ?? "");
          setProfileState("found");
        } else {
          setRfc("");
          setLegalName(selectedOrigin.member_name ?? "");
          setTaxRegime("612");
          setPostalCode("");
          setCfdiUse("G03");
          setEmail("");
          setProfileState("empty");
        }
      })
      .catch(() => {
        if (!active) return;
        setLegalName(selectedOrigin.member_name ?? "");
        setProfileState("empty");
      });
    return () => { active = false; };
  }, [onUnauthorized, selectedOrigin]);

  const changeOriginType = (type: BillingOrigin["origin_type"]) => {
    setOriginType(type);
    setSelectedOrigin(null);
    setProfileState("idle");
    rotateKey();
  };

  const usePublicGeneral = () => {
    setRfc("XAXX010101000");
    setLegalName("PÚBLICO EN GENERAL");
    setTaxRegime("616");
    setPostalCode("01000");
    setCfdiUse("S01");
    setEmail("");
    setSaveProfile(false);
    rotateKey();
  };

  const receptorPayload = () => ({
    rfc: rfc.trim(),
    legal_name: legalName.trim(),
    tax_regime: taxRegime,
    postal_code: postalCode.trim(),
    cfdi_use: cfdiUse,
    email: email.trim() || null,
  });

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedOrigin) {
      setError("Selecciona la venta o el cobro que se va a facturar.");
      return;
    }
    if (!rfc.trim() || !legalName.trim() || !postalCode.trim()) {
      setError("Completa el RFC, la razón social y el código postal del receptor.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/billing/invoices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin_type: selectedOrigin.origin_type,
          origin_id: selectedOrigin.origin_id,
          idempotency_key: idempotencyKey,
          payment_method: paymentMethod,
          payment_form: paymentMethod === "PPD" ? "99" : paymentForm,
          receptor: receptorPayload(),
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo solicitar la factura."));
        return;
      }
      const body = await response.json() as { invoice: BillingInvoice; idempotent_replay: boolean };
      let invoice = body.invoice;
      let message = body.idempotent_replay
        ? `La factura ${invoice.folio_label} ya existía; se muestra el comprobante original.`
        : `Factura ${invoice.folio_label} solicitada.`;

      if (saveProfile && selectedOrigin.member_id) {
        const profileResponse = await fetch(`/api/admin/members/${encodeURIComponent(selectedOrigin.member_id)}/fiscal-profile`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(receptorPayload()),
        });
        if (profileResponse.status === 401) { onUnauthorized(); return; }
        if (!profileResponse.ok) message += " Los datos fiscales no se guardaron en la ficha del socio.";
      }

      if (stampNow && canManage && (invoice.status === "requested" || invoice.status === "failed")) {
        const stampResponse = await fetch(`/api/admin/billing/invoices/${encodeURIComponent(invoice.id)}/stamp`, { method: "POST" });
        if (stampResponse.status === 401) { onUnauthorized(); return; }
        if (stampResponse.ok) {
          invoice = await stampResponse.json() as BillingInvoice;
          message = invoice.is_simulated
            ? `Comprobante ${invoice.folio_label} timbrado en modo simulación.`
            : `Comprobante ${invoice.folio_label} timbrado.`;
        } else {
          const payload = await stampResponse.json().catch(() => ({}));
          message = `Factura ${invoice.folio_label} solicitada, pero no se pudo timbrar: ${billingErrorDetail(payload, "error del PAC.")}`;
        }
      }
      onCreated(message, invoice);
    } catch {
      setError("No se pudo conectar con el backend. Reintenta con la misma solicitud.");
    } finally {
      setBusy(false);
    }
  };

  const originPages = Math.max(1, Math.ceil((origins?.total ?? 0) / 10));

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide billing-modal" role="dialog" aria-modal="true" aria-labelledby="new-invoice-title">
        <div className="modal-header"><span className="modal-icon"><Receipt size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">CFDI 4.0 · NUEVA SOLICITUD</p><h2 id="new-invoice-title">Nueva factura</h2>
        <p className="modal-subtitle">Elige una operación cobrada, confirma los datos fiscales y solicita el comprobante. Solo aparecen ventas completadas sin devoluciones y cobros de membresía confirmados.</p>
        <form onSubmit={submit}>
          <div className="staff-tabs pos-tabs">
            <button type="button" className={originType === "sale" ? "staff-tab-active" : ""} onClick={() => changeOriginType("sale")}>Ventas en mostrador</button>
            <button type="button" className={originType === "membership_payment" ? "staff-tab-active" : ""} onClick={() => changeOriginType("membership_payment")}>Cobros de membresía</button>
            <span className="staff-tabs-note"><ShieldCheck size={14} />Solo operaciones sin factura vigente</span>
          </div>
          <div className="billing-create-grid">
            <div className="billing-origin-panel">
              <div className="modal-section-title"><span>OPERACIONES POR FACTURAR</span><span>{origins?.total ?? 0}</span></div>
              <label className="table-search"><Search size={17} /><input value={originSearch} onChange={(event) => setOriginSearch(event.target.value)} placeholder={originType === "sale" ? "Buscar folio o socio" : "Buscar socio o plan"} /></label>
              {originsError && <div className="member-modal-error" role="alert">{originsError}</div>}
              <div className="billing-origin-list">
                {originsLoading ? <p className="billing-empty">Consultando operaciones…</p>
                  : (origins?.items.length ?? 0) === 0 ? <p className="billing-empty">No hay operaciones por facturar con este filtro.</p>
                  : origins?.items.map((origin) => (
                    <button type="button" key={`${origin.origin_type}-${origin.origin_id}`} className={`billing-origin ${selectedOrigin?.origin_id === origin.origin_id ? "billing-origin-selected" : ""}`} onClick={() => setSelectedOrigin(origin)}>
                      <span className="billing-origin-main">
                        <strong>{origin.reference}</strong>
                        <small>{origin.member_name ?? "Sin socio registrado"}</small>
                        <small>{origin.description}</small>
                      </span>
                      <span className="billing-origin-side">
                        <strong>{formatMoney(origin.total_cents)}</strong>
                        <small>{formatMoment(origin.occurred_at)}</small>
                        <small>{billingPaymentMethodLabels[origin.payment_method] ?? origin.payment_method}</small>
                      </span>
                    </button>
                  ))}
              </div>
              {originPages > 1 && (
                <span className="member-pagination billing-origin-pagination">
                  <span>Página {originPage} de {originPages}</span>
                  <button type="button" aria-label="Página anterior" disabled={originPage <= 1} onClick={() => setOriginPage(Math.max(1, originPage - 1))}>‹</button>
                  <button type="button" aria-label="Página siguiente" disabled={originPage >= originPages} onClick={() => setOriginPage(Math.min(originPages, originPage + 1))}>›</button>
                </span>
              )}
            </div>
            <div className="billing-receptor-panel">
              <div className="modal-section-title"><span>DATOS FISCALES DEL RECEPTOR</span>{profileState === "loading" && <small>Consultando perfil…</small>}</div>
              {profileState === "found" && <p className="billing-profile-hint"><ShieldCheck size={13} />Se cargaron los datos fiscales guardados del socio.</p>}
              {selectedOrigin && !selectedOrigin.member_id && <p className="billing-profile-hint">La venta no tiene socio: captura los datos del receptor o usa «público en general».</p>}
              <div className="form-row">
                <label className="form-field"><span>RFC *</span><input value={rfc} onChange={(event) => { setRfc(event.target.value.toUpperCase()); rotateKey(); }} maxLength={13} placeholder="XAXX010101000" required /></label>
                <label className="form-field"><span>Razón social *</span><input value={legalName} onChange={(event) => { setLegalName(event.target.value); rotateKey(); }} maxLength={254} placeholder="Nombre o razón social" required /></label>
              </div>
              <div className="form-row">
                <label className="form-field"><span>Régimen fiscal *</span><select value={taxRegime} onChange={(event) => { setTaxRegime(event.target.value); rotateKey(); }}>{BILLING_TAX_REGIMES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label className="form-field"><span>Uso del CFDI *</span><select value={cfdiUse} onChange={(event) => { setCfdiUse(event.target.value); rotateKey(); }}>{BILLING_CFDI_USES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              </div>
              <div className="form-row">
                <label className="form-field"><span>Código postal fiscal *</span><input value={postalCode} onChange={(event) => { setPostalCode(event.target.value.replace(/\D/g, "").slice(0, 5)); rotateKey(); }} inputMode="numeric" maxLength={5} placeholder="06700" required /></label>
                <label className="form-field"><span>Correo de entrega</span><input type="email" value={email} onChange={(event) => { setEmail(event.target.value); rotateKey(); }} placeholder="fiscal@correo.com" /></label>
              </div>
              <div className="form-row">
                <label className="form-field"><span>Método de pago SAT *</span><select value={paymentMethod} onChange={(event) => { setPaymentMethod(event.target.value as "PUE" | "PPD"); rotateKey(); }}>{BILLING_INVOICE_PAYMENT_METHODS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label className="form-field"><span>Forma de pago SAT *</span><select value={paymentMethod === "PPD" ? "99" : paymentForm} disabled={paymentMethod === "PPD"} onChange={(event) => { setPaymentForm(event.target.value); rotateKey(); }}>{BILLING_PAYMENT_FORMS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              </div>
              {paymentMethod === "PPD" && <p className="billing-profile-hint"><ShieldAlert size={13} />PPD difiere el cobro: la factura se emite con forma 99 y cada pago se registra después con un complemento de pago.</p>}
              <button type="button" className="text-button" onClick={usePublicGeneral}>Usar público en general</button>
              {selectedOrigin?.member_id && (
                <label className="form-check"><input type="checkbox" checked={saveProfile} onChange={(event) => setSaveProfile(event.target.checked)} /><span>Guardar estos datos fiscales en la ficha del socio para la próxima factura.</span></label>
              )}
              {canManage && (
                <label className="form-check"><input type="checkbox" checked={stampNow} onChange={(event) => setStampNow(event.target.checked)} /><span>Solicitar y timbrar ahora. En vista previa el comprobante queda marcado como simulado y sin validez fiscal.</span></label>
              )}
              {error && <div className="login-error" role="alert">{error}</div>}
              <div className="modal-note"><ShieldAlert size={16} /><span>La factura guarda una copia de los datos fiscales: editar el perfil del socio después no altera un comprobante ya emitido.</span></div>
              <div className="modal-actions">
                <button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button>
                <button type="submit" className="button button-primary" disabled={busy || !selectedOrigin}><Check size={16} />{busy ? "Procesando…" : (stampNow && canManage ? "Solicitar y timbrar" : "Solicitar factura")}</button>
              </div>
            </div>
          </div>
        </form>
      </section>
    </div>
  );
}

function InvoiceDetailModal({ invoiceId, canManage, canRequest, onOpenInvoice, onClose, onChanged, onUnauthorized }: { invoiceId: string; canManage: boolean; canRequest: boolean; onOpenInvoice: (invoiceId: string) => void; onClose: () => void; onChanged: (message: string) => void; onUnauthorized: () => void }) {
  const [invoice, setInvoice] = useState<BillingInvoice | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"stamp" | "cancel" | "cancellation-check" | "send" | "credit" | "payment" | "payment-stamp" | "payment-cancel" | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reasonCode, setReasonCode] = useState("02");
  const [replacementUuid, setReplacementUuid] = useState("");
  const [note, setNote] = useState("");
  const [emailOpen, setEmailOpen] = useState(false);
  const [emailTo, setEmailTo] = useState("");
  const [emailNotice, setEmailNotice] = useState("");
  const [creditOpen, setCreditOpen] = useState(false);
  const [creditAmount, setCreditAmount] = useState("");
  const [creditReason, setCreditReason] = useState<BillingCreditNoteReason>("return");
  const [creditNote, setCreditNote] = useState("");
  const [creditStampNow, setCreditStampNow] = useState(true);
  const [creditIdempotencyKey, setCreditIdempotencyKey] = useState(() => globalThis.crypto.randomUUID());
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentForm, setPaymentForm] = useState("03");
  const [paymentPaidOn, setPaymentPaidOn] = useState(() => todayDateInput());
  const [paymentStampNow, setPaymentStampNow] = useState(true);
  const [paymentIdempotencyKey, setPaymentIdempotencyKey] = useState(() => globalThis.crypto.randomUUID());
  const [paymentCancelId, setPaymentCancelId] = useState<string | null>(null);
  const [paymentCancelReason, setPaymentCancelReason] = useState("02");
  const [paymentCancelReplacement, setPaymentCancelReplacement] = useState("");
  const [paymentCancelNote, setPaymentCancelNote] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/billing/invoices/${encodeURIComponent(invoiceId)}`, { cache: "no-store" });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(billingErrorDetail(payload, "No se pudo consultar el comprobante."));
      }
      setInvoice(await response.json() as BillingInvoice);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No se pudo consultar el comprobante.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [invoiceId]);

  const stamp = async () => {
    if (!invoice) return;
    setBusy("stamp");
    setError("");
    try {
      const response = await fetch(`/api/admin/billing/invoices/${encodeURIComponent(invoice.id)}/stamp`, { method: "POST" });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo timbrar el comprobante."));
        return;
      }
      const updated = await response.json() as BillingInvoice;
      setInvoice(updated);
      onChanged(updated.is_simulated ? `Comprobante ${updated.folio_label} timbrado en modo simulación.` : `Comprobante ${updated.folio_label} timbrado.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(null);
    }
  };

  const cancel = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!invoice) return;
    if (reasonCode === "01") {
      const uuid = replacementUuid.trim();
      if (!uuid) {
        setError("El motivo 01 exige el UUID del comprobante que sustituye.");
        return;
      }
      if (!BILLING_UUID_PATTERN.test(uuid)) {
        setError("El UUID del comprobante que sustituye no tiene un formato válido.");
        return;
      }
    }
    setBusy("cancel");
    setError("");
    try {
      const response = await fetch(`/api/admin/billing/invoices/${encodeURIComponent(invoice.id)}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason_code: reasonCode,
          replacement_uuid: replacementUuid.trim() || null,
          note: note.trim() || null,
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo cancelar el comprobante."));
        return;
      }
      const updated = await response.json() as BillingInvoice;
      setInvoice(updated);
      setCancelOpen(false);
      onChanged(
        updated.cancellation_pending
          ? `Cancelación de ${updated.folio_label} en proceso en el SAT; consulta el estado más tarde.`
          : `Comprobante ${updated.folio_label} cancelado.`,
      );
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(null);
    }
  };

  const checkCancellation = async () => {
    if (!invoice) return;
    setBusy("cancellation-check");
    setError("");
    try {
      const response = await fetch(`/api/admin/billing/invoices/${encodeURIComponent(invoice.id)}/cancellation-check`, {
        method: "POST",
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo consultar el estado en el SAT."));
        return;
      }
      const result = await response.json() as { invoice: BillingInvoice; sat_status: { estado: string; estatus_cancelacion: string } };
      setInvoice(result.invoice);
      const estatus = result.sat_status.estatus_cancelacion ? ` · ${result.sat_status.estatus_cancelacion}` : "";
      onChanged(`SAT: ${result.sat_status.estado}${estatus}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(null);
    }
  };

  const openCreditForm = () => {
    if (!invoice) return;
    setCreditAmount((invoice.credit_balance_cents / 100).toFixed(2));
    setCreditReason("return");
    setCreditNote("");
    setCreditStampNow(true);
    setCreditIdempotencyKey(globalThis.crypto.randomUUID());
    setCreditOpen(true);
    setError("");
  };

  const issueCreditNote = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!invoice) return;
    const amountCents = parseMoneyToCents(creditAmount);
    if (amountCents === null || amountCents <= 0) {
      setError("Captura un importe mayor que cero para la nota de crédito.");
      return;
    }
    if (amountCents > invoice.credit_balance_cents) {
      setError(`El importe excede el saldo acreditable (${formatMoney(invoice.credit_balance_cents)}).`);
      return;
    }
    setBusy("credit");
    setError("");
    try {
      const response = await fetch(`/api/admin/billing/invoices/${encodeURIComponent(invoice.id)}/credit-notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          amount_cents: amountCents,
          reason: creditReason,
          note: creditNote.trim() || null,
          idempotency_key: creditIdempotencyKey,
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo solicitar la nota de crédito."));
        return;
      }
      const body = await response.json() as { invoice: BillingInvoice; idempotent_replay: boolean };
      let creditInvoice = body.invoice;
      let message = body.idempotent_replay
        ? `La nota de crédito ${creditInvoice.folio_label} ya existía; se muestra el comprobante original.`
        : `Nota de crédito ${creditInvoice.folio_label} solicitada por ${formatMoney(amountCents)}.`;

      if (creditStampNow && (creditInvoice.status === "requested" || creditInvoice.status === "failed")) {
        const stampResponse = await fetch(`/api/admin/billing/invoices/${encodeURIComponent(creditInvoice.id)}/stamp`, { method: "POST" });
        if (stampResponse.status === 401) { onUnauthorized(); return; }
        if (stampResponse.ok) {
          creditInvoice = await stampResponse.json() as BillingInvoice;
          message = creditInvoice.is_simulated
            ? `Nota de crédito ${creditInvoice.folio_label} timbrada en modo simulación.`
            : `Nota de crédito ${creditInvoice.folio_label} timbrada.`;
        } else {
          const payload = await stampResponse.json().catch(() => ({}));
          message = `Nota de crédito ${creditInvoice.folio_label} solicitada, pero no se pudo timbrar: ${billingErrorDetail(payload, "error del PAC.")}`;
        }
      }
      setCreditOpen(false);
      setCreditIdempotencyKey(globalThis.crypto.randomUUID());
      onChanged(message);
      onOpenInvoice(creditInvoice.id);
    } catch {
      setError("No se pudo conectar con el backend. Reintenta con la misma solicitud.");
    } finally {
      setBusy(null);
    }
  };

  const openPaymentForm = () => {
    if (!invoice) return;
    setPaymentAmount((invoice.payment_balance_cents / 100).toFixed(2));
    setPaymentForm("03");
    setPaymentPaidOn(todayDateInput());
    setPaymentStampNow(true);
    setPaymentIdempotencyKey(globalThis.crypto.randomUUID());
    setPaymentCancelId(null);
    setPaymentOpen(true);
    setError("");
  };

  const createPayment = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!invoice) return;
    const amountCents = parseMoneyToCents(paymentAmount);
    if (amountCents === null || amountCents <= 0) {
      setError("Captura un importe mayor que cero para el complemento de pago.");
      return;
    }
    if (amountCents > invoice.payment_balance_cents) {
      setError(`El importe excede el saldo pendiente (${formatMoney(invoice.payment_balance_cents)}).`);
      return;
    }
    if (!paymentPaidOn) {
      setError("Captura la fecha en que se recibió el pago.");
      return;
    }
    setBusy("payment");
    setError("");
    try {
      const response = await fetch(`/api/admin/billing/invoices/${encodeURIComponent(invoice.id)}/payment-complements`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          amount_cents: amountCents,
          payment_form: paymentForm,
          paid_on: paymentPaidOn,
          idempotency_key: paymentIdempotencyKey,
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo solicitar el complemento de pago."));
        return;
      }
      const body = await response.json() as { payment: BillingPaymentComplement; idempotent_replay: boolean };
      let payment = body.payment;
      let message = body.idempotent_replay
        ? `El complemento ${payment.folio_label} ya existía; se muestra el comprobante original.`
        : `Complemento ${payment.folio_label} solicitado por ${formatMoney(amountCents)}.`;

      if (paymentStampNow && (payment.status === "requested" || payment.status === "failed")) {
        const stampResponse = await fetch(`/api/admin/billing/payment-complements/${encodeURIComponent(payment.id)}/stamp`, { method: "POST" });
        if (stampResponse.status === 401) { onUnauthorized(); return; }
        if (stampResponse.ok) {
          payment = await stampResponse.json() as BillingPaymentComplement;
          message = payment.is_simulated
            ? `Complemento ${payment.folio_label} timbrado en modo simulación.`
            : `Complemento ${payment.folio_label} timbrado.`;
        } else {
          const payload = await stampResponse.json().catch(() => ({}));
          message = `Complemento ${payment.folio_label} solicitado, pero no se pudo timbrar: ${billingErrorDetail(payload, "error del PAC.")}`;
        }
      }
      setPaymentOpen(false);
      setPaymentIdempotencyKey(globalThis.crypto.randomUUID());
      await load();
      onChanged(message);
    } catch {
      setError("No se pudo conectar con el backend. Reintenta con la misma solicitud.");
    } finally {
      setBusy(null);
    }
  };

  const stampPayment = async (payment: BillingPaymentComplementRef) => {
    setBusy("payment-stamp");
    setError("");
    try {
      const response = await fetch(`/api/admin/billing/payment-complements/${encodeURIComponent(payment.payment_id)}/stamp`, { method: "POST" });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo timbrar el complemento de pago."));
        return;
      }
      const updated = await response.json() as BillingPaymentComplement;
      const message = updated.is_simulated
        ? `Complemento ${updated.folio_label} timbrado en modo simulación.`
        : `Complemento ${updated.folio_label} timbrado.`;
      await load();
      onChanged(message);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(null);
    }
  };

  const openPaymentCancel = (paymentId: string) => {
    setPaymentCancelId(paymentId);
    setPaymentCancelReason("02");
    setPaymentCancelReplacement("");
    setPaymentCancelNote("");
    setPaymentOpen(false);
    setError("");
  };

  const cancelPayment = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!paymentCancelId) return;
    if (paymentCancelReason === "01") {
      const uuid = paymentCancelReplacement.trim();
      if (!uuid) {
        setError("El motivo 01 exige el UUID del comprobante que sustituye.");
        return;
      }
      if (!BILLING_UUID_PATTERN.test(uuid)) {
        setError("El UUID del comprobante que sustituye no tiene un formato válido.");
        return;
      }
    }
    setBusy("payment-cancel");
    setError("");
    try {
      const response = await fetch(`/api/admin/billing/payment-complements/${encodeURIComponent(paymentCancelId)}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason_code: paymentCancelReason,
          replacement_uuid: paymentCancelReplacement.trim() || null,
          note: paymentCancelNote.trim() || null,
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo cancelar el complemento de pago."));
        return;
      }
      const updated = await response.json() as BillingPaymentComplement;
      setPaymentCancelId(null);
      await load();
      onChanged(`Complemento ${updated.folio_label} cancelado; el saldo pendiente de la factura se actualizó.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(null);
    }
  };

  const sendInvoiceEmail = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!invoice) return;
    const recipient = emailTo.trim();
    if (!recipient) {
      setError("Captura el correo del destinatario.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipient)) {
      setError("El correo del destinatario no es válido.");
      return;
    }
    setBusy("send");
    setError("");
    setEmailNotice("");
    try {
      const response = await fetch(`/api/admin/billing/invoices/${encodeURIComponent(invoice.id)}/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: recipient }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo enviar la factura."));
        return;
      }
      const delivery = await response.json() as BillingDelivery;
      setEmailOpen(false);
      const message = delivery.status === "simulated"
        ? `Envío simulado a ${delivery.recipient}.`
        : `Factura enviada a ${delivery.recipient}.`;
      setEmailNotice(delivery.status === "simulated"
        ? `${message} En vista previa no se contactó un servidor SMTP.`
        : message);
      onChanged(message);
      await load();
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(null);
    }
  };

  const status = invoice ? billingInvoiceStatus(invoice.status) : "requested";
  const canStamp = invoice !== null && canManage && (invoice.status === "requested" || invoice.status === "failed");
  const canDeliver = invoice !== null && (invoice.status === "stamped" || invoice.status === "cancelled");
  const isCreditNote = invoice?.origin_type === "credit_note";
  const isSourceInvoice = invoice?.origin_type === "sale" || invoice?.origin_type === "membership_payment";
  const isPpdInvoice = invoice?.payment_method === "PPD";
  const stampedCreditNoteCount = invoice?.credit_notes.filter((entry) => entry.status === "stamped").length ?? 0;
  const stampedPaymentComplements = invoice?.payment_complements.filter((entry) => entry.status === "stamped") ?? [];
  const latestStampedPayment = stampedPaymentComplements.reduce<BillingPaymentComplementRef | null>(
    (latest, entry) => (latest === null || entry.partiality_number > latest.partiality_number ? entry : latest),
    null,
  );
  const canIssueCreditNote = invoice !== null && canManage && invoice.status === "stamped" && isSourceInvoice && !isPpdInvoice && invoice.credit_balance_cents > 0;
  const canAddPayment = invoice !== null && canManage && invoice.status === "stamped" && isSourceInvoice && isPpdInvoice && invoice.payment_balance_cents > 0;
  const canCancelInvoice = invoice !== null && canManage && invoice.status === "stamped" && !invoice.cancellation_pending && stampedCreditNoteCount === 0 && stampedPaymentComplements.length === 0;

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide billing-modal" role="dialog" aria-modal="true" aria-labelledby="invoice-detail-title">
        <div className="modal-header"><span className="modal-icon"><Receipt size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        {loading ? <p className="billing-empty">Cargando comprobante…</p> : !invoice ? (
          <><p className="section-kicker">FACTURACIÓN</p><h2 id="invoice-detail-title">Comprobante no disponible</h2>{error && <div className="login-error" role="alert">{error}</div>}<div className="modal-actions"><button className="button button-secondary" onClick={onClose}>Cerrar</button></div></>
        ) : (
          <>
            <p className="section-kicker">CFDI 4.0 · {invoice.folio_label}</p>
            <h2 id="invoice-detail-title">{invoice.receptor_name}</h2>
            <p className="modal-subtitle">{invoice.receptor_rfc} · {billingOriginLabels[invoice.origin_type]} {isCreditNote && invoice.related_invoice_folio_label ? `sobre ${invoice.related_invoice_folio_label}` : invoice.origin_reference}</p>
            <div className="billing-detail-status">
              <span className={`status-badge ${billingStatusBadges[status]}`}><i />{billingStatusLabels[status]}</span>
              {invoice.origin_type === "global" && invoice.global_year && invoice.global_month && <span className="status-badge status-neutral"><i />{billingGlobalPeriodLabel(invoice.global_year, invoice.global_month)}</span>}
              {isCreditNote && <span className="status-badge status-neutral"><i />CFDI de egreso</span>}
              {isPpdInvoice && invoice.status === "stamped" && <span className={`status-badge ${billingPaymentBalanceBadges[invoice.payment_status]}`}><i />{billingPaymentBalanceLabels[invoice.payment_status]}</span>}
              {invoice.is_simulated && <span className="status-badge status-warn"><i />Simulada · sin validez fiscal</span>}
              <span className="billing-detail-date">Creada {formatMoment(invoice.created_at)}</span>
            </div>
            {invoice.is_simulated && (
              <div className="billing-simulated-note"><ShieldAlert size={16} /><span>Este comprobante se generó con el PAC simulado de la vista previa. No está timbrado ante el SAT y no debe entregarse como factura.</span></div>
            )}

            <div className="billing-totals">
              <div><span>{isCreditNote ? "TOTAL ACREDITADO" : "TOTAL"}</span><strong>{formatMoney(invoice.total_cents)}</strong></div>
              <div><span>SUBTOTAL</span><strong>{formatMoney(invoice.subtotal_cents)}</strong></div>
              <div><span>IVA ({invoice.tax_rate_percent}%)</span><strong>{formatMoney(invoice.tax_cents)}</strong></div>
              <div><span>FORMA DE PAGO</span><strong>{invoice.payment_form}</strong><small>{billingPaymentFormLabel(invoice.payment_form)}</small></div>
              <div><span>MÉTODO</span><strong>{invoice.payment_method}</strong><small>{billingInvoicePaymentMethodLabel(invoice.payment_method)}</small></div>
              <div><span>MONEDA</span><strong>{invoice.currency}</strong><small>Importes con IVA incluido</small></div>
            </div>

            <div className="detail-section">
              <div className="modal-section-title"><span>CONCEPTOS</span><span>{invoice.items.length}</span></div>
              <div className="table-scroll">
                <table className="data-table compact-table">
                  <thead><tr><th>DESCRIPCIÓN</th><th>CLAVE SAT</th><th>CANTIDAD</th><th>UNITARIO</th><th>SUBTOTAL</th><th>IVA</th><th>TOTAL</th></tr></thead>
                  <tbody>
                    {invoice.items.map((item) => (
                      <tr key={item.position}>
                        <td><strong>{item.description}</strong><small className="billing-inline-note">{item.sat_unit_code} · {item.unit_name}</small></td>
                        <td>{item.sat_product_code}</td>
                        <td>{item.quantity}</td>
                        <td>{formatMoney(item.subtotal_cents / item.quantity)}</td>
                        <td>{formatMoney(item.subtotal_cents)}</td>
                        <td>{formatMoney(item.tax_cents)}</td>
                        <td>{formatMoney(item.total_cents)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {isCreditNote && (
              <div className="detail-section">
                <div className="modal-section-title"><span>RELACIÓN FISCAL</span><span>TipoRelación 01</span></div>
                <div className="billing-detail-grid">
                  <div><span>FACTURA ORIGINAL</span><strong>{invoice.related_invoice_folio_label ?? "—"}</strong></div>
                  <div><span>ESTADO DE LA ORIGINAL</span><strong>{invoice.related_invoice_status ? billingStatusLabels[billingInvoiceStatus(invoice.related_invoice_status)] : "—"}</strong></div>
                  <div><span>MOTIVO</span><strong>{invoice.credit_note_reason ? billingCreditNoteReasonLabels[invoice.credit_note_reason] : "—"}</strong></div>
                  <div><span>NOTA</span><strong>{invoice.credit_note_note ?? "—"}</strong></div>
                </div>
                {invoice.related_invoice_id && <button type="button" className="text-button" onClick={() => onOpenInvoice(invoice.related_invoice_id!)}>Ver factura original {invoice.related_invoice_folio_label ?? ""}</button>}
              </div>
            )}

            {isSourceInvoice && invoice.status === "stamped" && !isPpdInvoice && (
              <div className="detail-section">
                <div className="modal-section-title"><span>NOTAS DE CRÉDITO</span><span>{invoice.credit_notes.length}</span></div>
                <div className="billing-totals">
                  <div><span>IMPORTE FACTURA</span><strong>{formatMoney(invoice.total_cents)}</strong></div>
                  <div><span>ACREDITADO</span><strong>{formatMoney(invoice.credited_cents)}</strong></div>
                  <div><span>SALDO ACREDITABLE</span><strong>{formatMoney(invoice.credit_balance_cents)}</strong><small>IVA incluido</small></div>
                </div>
                <div className="table-scroll">
                  <table className="data-table compact-table">
                    <thead><tr><th>FOLIO</th><th>FECHA</th><th>MOTIVO</th><th>IMPORTE</th><th>ESTADO</th></tr></thead>
                    <tbody>
                      {invoice.credit_notes.length === 0 ? <tr><td colSpan={5} className="empty-row">Sin notas de crédito para esta factura.</td></tr>
                        : invoice.credit_notes.map((entry) => {
                          const noteStatus = billingInvoiceStatus(entry.status);
                          return (
                            <tr key={entry.invoice_id}>
                              <td><button type="button" className="text-button" onClick={() => onOpenInvoice(entry.invoice_id)}>{entry.folio_label}</button></td>
                              <td className="time-cell">{formatMoment(entry.created_at)}</td>
                              <td>{billingCreditNoteReasonLabels[entry.reason] ?? entry.reason}</td>
                              <td>−{formatMoney(entry.total_cents)}</td>
                              <td><span className={`status-badge ${billingStatusBadges[noteStatus]}`}><i />{billingStatusLabels[noteStatus]}</span></td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
                {stampedCreditNoteCount > 0 && <p className="billing-empty">Para cancelar la factura primero cancela sus {stampedCreditNoteCount} {stampedCreditNoteCount === 1 ? "nota de crédito timbrada" : "notas de crédito timbradas"}.</p>}
                {canIssueCreditNote && !creditOpen && (
                  <div className="modal-actions"><button type="button" className="button button-secondary" onClick={openCreditForm} disabled={busy !== null}>Emitir nota de crédito</button></div>
                )}
                {creditOpen && (
                  <form className="billing-credit-form" onSubmit={issueCreditNote}>
                    <div className="modal-section-title"><span>NUEVA NOTA DE CRÉDITO</span><span>Saldo {formatMoney(invoice.credit_balance_cents)}</span></div>
                    <p className="billing-empty">Se emitirá un CFDI de egreso relacionado con {invoice.folio_label}. El importe se descuenta del saldo acreditable cuando la nota se timbra.</p>
                    <div className="form-row">
                      <label className="form-field"><span>Importe (IVA incluido) *</span><input value={creditAmount} onChange={(event) => { setCreditAmount(event.target.value); setError(""); }} inputMode="decimal" placeholder="0.00" /></label>
                      <label className="form-field"><span>Motivo *</span><select value={creditReason} onChange={(event) => { setCreditReason(event.target.value as BillingCreditNoteReason); setError(""); }}>{BILLING_CREDIT_NOTE_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                    </div>
                    <label className="form-field"><span>Nota</span><input value={creditNote} onChange={(event) => setCreditNote(event.target.value)} maxLength={300} placeholder="Detalle opcional de la nota de crédito" /></label>
                    <label className="form-check"><input type="checkbox" checked={creditStampNow} onChange={(event) => setCreditStampNow(event.target.checked)} /><span>Solicitar y timbrar ahora. En vista previa el comprobante queda marcado como simulado y sin validez fiscal.</span></label>
                    <div className="modal-actions">
                      <button type="button" className="button button-secondary" onClick={() => setCreditOpen(false)}>Volver</button>
                      <button type="submit" className="button button-primary" disabled={busy === "credit"}>{busy === "credit" ? "Procesando…" : "Emitir nota de crédito"}</button>
                    </div>
                  </form>
                )}
              </div>
            )}

            {isSourceInvoice && isPpdInvoice && (invoice.status === "stamped" || invoice.status === "cancelled" || invoice.payment_complements.length > 0) && (
              <div className="detail-section">
                <div className="modal-section-title"><span>COMPLEMENTOS DE PAGO PPD</span><span>{invoice.payment_complements.length}</span></div>
                <div className="billing-totals">
                  <div><span>IMPORTE FACTURA</span><strong>{formatMoney(invoice.total_cents)}</strong></div>
                  <div><span>PAGADO</span><strong>{formatMoney(invoice.paid_cents)}</strong></div>
                  <div><span>SALDO PENDIENTE</span><strong>{formatMoney(invoice.payment_balance_cents)}</strong><small>IVA incluido · {billingPaymentBalanceLabels[invoice.payment_status]}</small></div>
                </div>
                <p className="billing-empty">Cada parcialidad se emite como un CFDI de pago (tipo P) relacionado con {invoice.folio_label}. El saldo solo disminuye cuando el complemento se timbra.</p>
                <div className="table-scroll">
                  <table className="data-table compact-table">
                    <thead><tr><th>FOLIO</th><th>PARC.</th><th>FECHA PAGO</th><th>FORMA</th><th>IMPORTE</th><th>SALDO</th><th>ESTADO</th><th /></tr></thead>
                    <tbody>
                      {invoice.payment_complements.length === 0 ? <tr><td colSpan={8} className="empty-row">Sin complementos de pago registrados.</td></tr>
                        : invoice.payment_complements.map((entry) => {
                          const paymentStatus = billingInvoiceStatus(entry.status);
                          const downloadable = entry.status === "stamped" || entry.status === "cancelled";
                          const cancellable = canManage && entry.status === "stamped" && latestStampedPayment?.payment_id === entry.payment_id;
                          return (
                            <tr key={entry.payment_id}>
                              <td><strong>{entry.folio_label}</strong>{entry.is_simulated && <small className="billing-inline-note">Simulado</small>}</td>
                              <td>{entry.partiality_number}</td>
                              <td>{formatDateOnly(entry.paid_on)}</td>
                              <td>{billingPaymentFormLabel(entry.payment_form)}</td>
                              <td>{formatMoney(entry.amount_cents)}</td>
                              <td>{formatMoney(entry.outstanding_balance_cents)}</td>
                              <td><span className={`status-badge ${billingStatusBadges[paymentStatus]}`}><i />{billingPaymentStatusLabels[paymentStatus]}</span></td>
                              <td>
                                <div className="pos-row-actions">
                                  {canManage && (entry.status === "requested" || entry.status === "failed") && (
                                    <button type="button" className="button button-primary button-small" disabled={busy !== null} onClick={() => void stampPayment(entry)}>{busy === "payment-stamp" ? "Timbrando…" : "Timbrar"}</button>
                                  )}
                                  {downloadable && <a className="button button-secondary button-small" href={`/api/admin/billing/payment-complements/${encodeURIComponent(entry.payment_id)}/xml`} download>XML</a>}
                                  {downloadable && <a className="button button-secondary button-small" href={`/api/admin/billing/payment-complements/${encodeURIComponent(entry.payment_id)}/pdf`} download>PDF</a>}
                                  {cancellable && paymentCancelId !== entry.payment_id && <button type="button" className="button button-secondary button-small" disabled={busy !== null} onClick={() => openPaymentCancel(entry.payment_id)}>Cancelar</button>}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
                {stampedPaymentComplements.length > 0 && <p className="billing-empty">Para cancelar la factura primero cancela su último complemento timbrado ({latestStampedPayment?.folio_label}).</p>}
                <p className="billing-empty">Las facturas PPD no admiten notas de crédito en esta versión; cualquier ajuste de importe se registra con un complemento de pago.</p>
                {canAddPayment && !paymentOpen && (
                  <div className="modal-actions"><button type="button" className="button button-secondary" onClick={openPaymentForm} disabled={busy !== null}>Registrar pago</button></div>
                )}
                {paymentOpen && invoice.status === "stamped" && (
                  <form className="billing-credit-form" onSubmit={createPayment}>
                    <div className="modal-section-title"><span>NUEVO COMPLEMENTO DE PAGO</span><span>Saldo {formatMoney(invoice.payment_balance_cents)}</span></div>
                    <p className="billing-empty">Registra una parcialidad o el pago total del saldo. El importe se descuenta hasta que el complemento se timbra.</p>
                    <div className="form-row">
                      <label className="form-field"><span>Importe pagado (IVA incluido) *</span><input value={paymentAmount} onChange={(event) => { setPaymentAmount(event.target.value); setError(""); }} inputMode="decimal" placeholder="0.00" /></label>
                      <label className="form-field"><span>Fecha de pago *</span><input type="date" value={paymentPaidOn} max={todayDateInput()} min={toDateInputValue(invoice.issued_at ?? invoice.created_at)} onChange={(event) => { setPaymentPaidOn(event.target.value); setError(""); }} /></label>
                    </div>
                    <label className="form-field"><span>Forma de pago SAT *</span><select value={paymentForm} onChange={(event) => { setPaymentForm(event.target.value); setError(""); }}>{BILLING_PAYMENT_COMPLEMENT_FORMS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                    <label className="form-check"><input type="checkbox" checked={paymentStampNow} onChange={(event) => setPaymentStampNow(event.target.checked)} /><span>Solicitar y timbrar ahora. En vista previa el complemento queda marcado como simulado y sin validez fiscal.</span></label>
                    <div className="modal-actions">
                      <button type="button" className="button button-secondary" onClick={() => setPaymentOpen(false)}>Volver</button>
                      <button type="submit" className="button button-primary" disabled={busy === "payment"}>{busy === "payment" ? "Procesando…" : "Registrar complemento"}</button>
                    </div>
                  </form>
                )}
                {paymentCancelId && (
                  <form className="billing-cancel-form" onSubmit={cancelPayment}>
                    <div className="modal-section-title"><span>CANCELAR COMPLEMENTO DE PAGO</span></div>
                    <p className="billing-empty">La cancelación conserva el folio y libera el importe en el saldo pendiente de la factura.</p>
                    <div className="form-row">
                      <label className="form-field"><span>Motivo SAT *</span><select value={paymentCancelReason} onChange={(event) => { setPaymentCancelReason(event.target.value); setError(""); }}>{BILLING_CANCELLATION_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                      {paymentCancelReason === "01" && <label className="form-field"><span>UUID que sustituye *</span><input value={paymentCancelReplacement} onChange={(event) => setPaymentCancelReplacement(event.target.value)} maxLength={36} placeholder="00000000-0000-0000-0000-000000000000" /></label>}
                    </div>
                    <label className="form-field"><span>Nota</span><input value={paymentCancelNote} onChange={(event) => setPaymentCancelNote(event.target.value)} maxLength={300} placeholder="Detalle opcional de la cancelación" /></label>
                    <div className="modal-actions">
                      <button type="button" className="button button-secondary" onClick={() => setPaymentCancelId(null)}>Volver</button>
                      <button type="submit" className="button button-danger" disabled={busy === "payment-cancel"}>{busy === "payment-cancel" ? "Cancelando…" : "Confirmar cancelación"}</button>
                    </div>
                  </form>
                )}
              </div>
            )}

            {invoice.origin_type === "global" && (
              <div className="detail-section">
                <div className="modal-section-title"><span>VENTAS INCLUIDAS</span><span>{invoice.global_sales.length}</span></div>
                <div className="table-scroll">
                  <table className="data-table compact-table">
                    <thead><tr><th>FOLIO</th><th>FECHA</th><th>TOTAL</th></tr></thead>
                    <tbody>
                      {invoice.global_sales.length === 0 ? <tr><td colSpan={3} className="empty-row">Sin ventas registradas en el lote.</td></tr>
                        : invoice.global_sales.map((sale) => (
                          <tr key={sale.sale_id}>
                            <td><strong>{sale.sale_folio}</strong></td>
                            <td className="time-cell">{formatMoment(sale.sold_at)}</td>
                            <td>{formatMoney(sale.total_cents)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div className="detail-section">
              <div className="modal-section-title"><span>RECEPTOR</span></div>
              <div className="billing-detail-grid">
                <div><span>RFC</span><strong>{invoice.receptor_rfc}</strong></div>
                <div><span>RÉGIMEN FISCAL</span><strong>{billingTaxRegimeLabel(invoice.receptor_tax_regime)}</strong></div>
                <div><span>CÓDIGO POSTAL</span><strong>{invoice.receptor_postal_code}</strong></div>
                <div><span>USO DEL CFDI</span><strong>{billingCfdiUseLabel(invoice.receptor_cfdi_use)}</strong></div>
                <div><span>CORREO</span><strong>{invoice.receptor_email ?? "—"}</strong></div>
                <div><span>{invoice.origin_type === "global" ? "VENTAS INCLUIDAS" : "SOCIO"}</span><strong>{invoice.origin_type === "global" ? invoice.global_sales.length : (invoice.member_name ?? "Sin socio")}</strong></div>
              </div>
            </div>

            {(invoice.uuid || invoice.provider_reference || invoice.provider) && (
              <div className="detail-section">
                <div className="modal-section-title"><span>TIMBRADO</span></div>
                <div className="billing-detail-grid">
                  <div><span>UUID SAT</span><strong>{invoice.uuid ?? "Sin UUID (simulación)"}</strong></div>
                  <div><span>PROVEEDOR</span><strong>{invoice.provider ?? "—"}</strong></div>
                  <div><span>REFERENCIA</span><strong>{invoice.provider_reference ?? "—"}</strong></div>
                  <div><span>TIMBRADO</span><strong>{formatMoment(invoice.stamped_at)}</strong></div>
                </div>
              </div>
            )}

            {invoice.cancellation_pending && (
              <div className="detail-section">
                <div className="modal-section-title"><span>CANCELACIÓN EN PROCESO</span></div>
                <p className="billing-empty">El SAT recibió la solicitud y aún la está procesando: el comprobante sigue vigente hasta que la resuelva.</p>
                <div className="billing-detail-grid">
                  <div><span>SOLICITADA</span><strong>{formatMoment(invoice.cancellation_requested_at)}</strong></div>
                  <div><span>ÚLTIMA CONSULTA</span><strong>{formatMoment(invoice.cancellation_checked_at)}</strong></div>
                  <div><span>MOTIVO SAT</span><strong>{invoice.cancellation_reason_code ?? "—"}</strong></div>
                  <div><span>NOTA</span><strong>{invoice.cancellation_note ?? "—"}</strong></div>
                </div>
                {canManage && (
                  <div className="modal-actions">
                    <button type="button" className="button button-secondary" onClick={checkCancellation} disabled={busy === "cancellation-check"}>
                      {busy === "cancellation-check" ? "Consultando…" : "Consultar estado en el SAT"}
                    </button>
                  </div>
                )}
              </div>
            )}

            {invoice.status === "cancelled" && (
              <div className="detail-section">
                <div className="modal-section-title"><span>CANCELACIÓN</span></div>
                <div className="billing-detail-grid">
                  <div><span>MOTIVO SAT</span><strong>{invoice.cancellation_reason_code ?? "—"}</strong></div>
                  <div><span>UUID DE SUSTITUCIÓN</span><strong>{invoice.cancellation_replacement_uuid ?? "—"}</strong></div>
                  <div><span>FECHA</span><strong>{formatMoment(invoice.cancelled_at)}</strong></div>
                  <div><span>NOTA</span><strong>{invoice.cancellation_note ?? "—"}</strong></div>
                </div>
              </div>
            )}

            <div className="detail-section">
              <div className="modal-section-title"><span>TRAZABILIDAD</span><span>{invoice.events.length} eventos</span></div>
              <div className="billing-timeline">
                {invoice.events.map((event, index) => (
                  <div className="billing-event" key={`${event.event_type}-${index}`}>
                    <span className="billing-event-dot" />
                    <div>
                      <strong>{billingEventLabel(event.event_type)}</strong>
                      <small>{formatMoment(event.occurred_at)}{event.to_status && billingStatusLabels[billingInvoiceStatus(event.to_status)] ? ` · ${billingStatusLabels[billingInvoiceStatus(event.to_status)]}` : ""}</small>
                      {billingEventValue(event, "provider_reference") && <small>Referencia: {billingEventValue(event, "provider_reference")}</small>}
                      {billingEventValue(event, "reason_code") && <small>Motivo SAT: {billingEventValue(event, "reason_code")}</small>}
                      {billingEventValue(event, "recipient") && <small>Destinatario: {billingEventValue(event, "recipient")}</small>}
                      {billingEventValue(event, "delivery_status") && <small>{billingEventValue(event, "delivery_status") === "simulated" ? "Entrega simulada en vista previa" : "Entrega confirmada por SMTP"}</small>}
                      {billingEventValue(event, "error") && <small>{billingEventValue(event, "error")}</small>}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {emailNotice && <div className="billing-delivery-success" role="status">{emailNotice}</div>}
            {error && <div className="login-error" role="alert">{error}</div>}

            {emailOpen && (
              <form className="billing-cancel-form billing-email-form" onSubmit={sendInvoiceEmail}>
                <div className="modal-section-title"><span>ENVIAR POR CORREO</span></div>
                <p className="billing-empty">Se adjuntarán el PDF y el XML del comprobante. En vista previa el envío se registra como simulado.</p>
                <label className="form-field"><span>Correo del destinatario *</span><input type="email" value={emailTo} onChange={(event) => { setEmailTo(event.target.value); setError(""); }} maxLength={254} placeholder="facturas@example.com" /></label>
                <div className="modal-actions">
                  <button type="button" className="button button-secondary" onClick={() => setEmailOpen(false)}>Volver</button>
                  <button type="submit" className="button button-primary" disabled={busy === "send"}>{busy === "send" ? "Enviando…" : "Enviar factura"}</button>
                </div>
              </form>
            )}

            {cancelOpen && (
              <form className="billing-cancel-form" onSubmit={cancel}>
                <div className="modal-section-title"><span>{isCreditNote ? "CANCELAR NOTA DE CRÉDITO" : "CANCELAR COMPROBANTE"}</span></div>
                <p className="billing-empty">{isCreditNote ? "La cancelación conserva la nota y su folio; libera el importe acreditado en la factura original." : `La cancelación conserva la factura y su folio; ${invoice.origin_type === "global" ? "libera el periodo y sus ventas para emitir un reemplazo." : "libera la operación para emitir un reemplazo."}`}</p>
                <div className="form-row">
                  <label className="form-field"><span>Motivo SAT *</span><select value={reasonCode} onChange={(event) => { setReasonCode(event.target.value); setError(""); }}>{BILLING_CANCELLATION_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                  {reasonCode === "01" && <label className="form-field"><span>UUID que sustituye *</span><input value={replacementUuid} onChange={(event) => setReplacementUuid(event.target.value)} maxLength={36} placeholder="00000000-0000-0000-0000-000000000000" /></label>}
                </div>
                <label className="form-field"><span>Nota</span><input value={note} onChange={(event) => setNote(event.target.value)} maxLength={300} placeholder="Detalle opcional de la cancelación" /></label>
                <div className="modal-actions">
                  <button type="button" className="button button-secondary" onClick={() => setCancelOpen(false)}>Volver</button>
                  <button type="submit" className="button button-danger" disabled={busy === "cancel"}>{busy === "cancel" ? "Cancelando…" : "Confirmar cancelación"}</button>
                </div>
              </form>
            )}

            <div className="modal-actions billing-detail-actions">
              {canDeliver && <a className="button button-secondary" href={`/api/admin/billing/invoices/${encodeURIComponent(invoice.id)}/pdf`} download><Download size={16} />Descargar PDF</a>}
              <a className="button button-secondary" href={`/api/admin/billing/invoices/${encodeURIComponent(invoice.id)}/xml`} download><Download size={16} />Descargar XML</a>
              {canRequest && invoice.status === "stamped" && invoice.origin_type !== "global" && !emailOpen && <button className="button button-secondary" onClick={() => { setEmailOpen(true); setEmailTo(invoice.receptor_email ?? ""); setEmailNotice(""); setError(""); }} disabled={busy !== null}><Mail size={16} />Enviar por correo</button>}
              {canStamp && <button className="button button-primary" onClick={() => void stamp()} disabled={busy !== null}><ShieldCheck size={16} />{busy === "stamp" ? "Timbrando…" : invoice.status === "failed" ? "Reintentar timbrado" : "Timbrar ahora"}</button>}
              {canCancelInvoice && !cancelOpen && <button className="button button-danger" onClick={() => setCancelOpen(true)} disabled={busy !== null}>{isCreditNote ? "Cancelar nota de crédito" : "Cancelar factura"}</button>}
              <button className="button button-secondary" onClick={onClose}>Cerrar</button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function MaintenanceView({ permissions, onUnauthorized, onToast }: { permissions: string[]; onUnauthorized: () => void; onToast: (message: string) => void }) {
  const canManage = permissions.includes("maintenance.manage");
  const canReport = permissions.includes("maintenance.report");

  const [tab, setTab] = useState<"equipos" | "tickets" | "bitacora" | "rondas">("equipos");
  const [overview, setOverview] = useState<MaintenanceOverview | null>(null);
  const [areas, setAreas] = useState<AreaServiceStatus[]>([]);
  const [refresh, setRefresh] = useState(0);
  const reload = () => setRefresh((value) => value + 1);

  const [equipmentDirectory, setEquipmentDirectory] = useState<EquipmentDirectory | null>(null);
  const [equipmentSearch, setEquipmentSearch] = useState("");
  const [equipmentQuery, setEquipmentQuery] = useState("");
  const [equipmentStatus, setEquipmentStatus] = useState<"" | EquipmentState>("");
  const [equipmentPage, setEquipmentPage] = useState(1);
  const [equipmentLoading, setEquipmentLoading] = useState(false);
  const [equipmentError, setEquipmentError] = useState("");

  const [ticketDirectory, setTicketDirectory] = useState<TicketDirectory | null>(null);
  const [ticketSearch, setTicketSearch] = useState("");
  const [ticketQuery, setTicketQuery] = useState("");
  const [ticketStatus, setTicketStatus] = useState<"" | TicketState>("");
  const [ticketSeverity, setTicketSeverity] = useState<"" | TicketSeverity>("");
  const [ticketPage, setTicketPage] = useState(1);
  const [ticketLoading, setTicketLoading] = useState(false);
  const [ticketError, setTicketError] = useState("");

  const [recordDirectory, setRecordDirectory] = useState<MaintenanceRecordDirectory | null>(null);
  const [recordKind, setRecordKind] = useState("");
  const [recordPage, setRecordPage] = useState(1);
  const [recordLoading, setRecordLoading] = useState(false);
  const [recordError, setRecordError] = useState("");

  const [checklistDirectory, setChecklistDirectory] = useState<ChecklistDirectory | null>(null);
  const [checklistArea, setChecklistArea] = useState("");
  const [checklistQuery, setChecklistQuery] = useState("");
  const [checklistResult, setChecklistResult] = useState("");
  const [checklistPage, setChecklistPage] = useState(1);
  const [checklistLoading, setChecklistLoading] = useState(false);
  const [checklistError, setChecklistError] = useState("");

  const [equipmentChoices, setEquipmentChoices] = useState<EquipmentChoice[]>([]);
  const [technicians, setTechnicians] = useState<BackendEmployee[]>([]);

  const [equipmentModal, setEquipmentModal] = useState<{ equipment: BackendEquipment | null } | null>(null);
  const [equipmentDetailId, setEquipmentDetailId] = useState<string | null>(null);
  const [recordModalEquipment, setRecordModalEquipment] = useState<BackendEquipment | null>(null);
  const [ticketModalOpen, setTicketModalOpen] = useState(false);
  const [ticketDetailId, setTicketDetailId] = useState<string | null>(null);
  const [checklistModalOpen, setChecklistModalOpen] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [overviewResponse, areasResponse] = await Promise.all([
          fetch("/api/admin/maintenance/overview", { cache: "no-store" }),
          fetch("/api/admin/maintenance/service-status", { cache: "no-store" }),
        ]);
        if (overviewResponse.status === 401 || areasResponse.status === 401) { onUnauthorized(); return; }
        if (!active) return;
        if (overviewResponse.ok) setOverview(await overviewResponse.json() as MaintenanceOverview);
        if (areasResponse.ok) setAreas(await areasResponse.json() as AreaServiceStatus[]);
      } catch {
        // The summary band is decorative.
      }
    };
    void load();
    return () => { active = false; };
  }, [refresh, onUnauthorized]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [equipmentResponse, staffResponse] = await Promise.all([
          fetch("/api/admin/maintenance/equipment/options", { cache: "no-store" }),
          fetch("/api/admin/staff", { cache: "no-store" }),
        ]);
        if (equipmentResponse.status === 401 || staffResponse.status === 401) { onUnauthorized(); return; }
        if (!active) return;
        if (equipmentResponse.ok) setEquipmentChoices(await equipmentResponse.json() as EquipmentChoice[]);
        if (staffResponse.ok) {
          const payload = await staffResponse.json() as BackendEmployee[] | { items?: BackendEmployee[] };
          setTechnicians(Array.isArray(payload) ? payload : payload.items ?? []);
        }
      } catch {
        // The selects only feed the forms.
      }
    };
    void load();
    return () => { active = false; };
  }, [refresh, onUnauthorized]);

  useEffect(() => {
    const handle = window.setTimeout(() => { setEquipmentQuery(equipmentSearch.trim()); setEquipmentPage(1); }, 250);
    return () => window.clearTimeout(handle);
  }, [equipmentSearch]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setEquipmentLoading(true);
      setEquipmentError("");
      const params = new URLSearchParams({ page: String(equipmentPage), page_size: String(EQUIPMENT_PAGE_SIZE) });
      if (equipmentQuery) params.set("search", equipmentQuery);
      if (equipmentStatus) params.set("status", equipmentStatus);
      try {
        const response = await fetch(`/api/admin/maintenance/equipment?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        if (active) setEquipmentDirectory(await response.json() as EquipmentDirectory);
      } catch {
        if (active) setEquipmentError("No se pudo cargar la flota de equipos.");
      } finally {
        if (active) setEquipmentLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [equipmentPage, equipmentQuery, equipmentStatus, refresh, onUnauthorized]);

  useEffect(() => {
    const handle = window.setTimeout(() => { setTicketQuery(ticketSearch.trim()); setTicketPage(1); }, 250);
    return () => window.clearTimeout(handle);
  }, [ticketSearch]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setTicketLoading(true);
      setTicketError("");
      const params = new URLSearchParams({ page: String(ticketPage), page_size: String(TICKETS_PAGE_SIZE) });
      if (ticketQuery) params.set("search", ticketQuery);
      if (ticketStatus) params.set("status", ticketStatus);
      if (ticketSeverity) params.set("severity", ticketSeverity);
      try {
        const response = await fetch(`/api/admin/maintenance/tickets?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        if (active) setTicketDirectory(await response.json() as TicketDirectory);
      } catch {
        if (active) setTicketError("No se pudo cargar los tickets de mantenimiento.");
      } finally {
        if (active) setTicketLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [ticketPage, ticketQuery, ticketStatus, ticketSeverity, refresh, onUnauthorized]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setRecordLoading(true);
      setRecordError("");
      const params = new URLSearchParams({ page: String(recordPage), page_size: String(RECORDS_PAGE_SIZE) });
      if (recordKind) params.set("kind", recordKind);
      try {
        const response = await fetch(`/api/admin/maintenance/records?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        if (active) setRecordDirectory(await response.json() as MaintenanceRecordDirectory);
      } catch {
        if (active) setRecordError("No se pudo cargar el historial técnico.");
      } finally {
        if (active) setRecordLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [recordPage, recordKind, refresh, onUnauthorized]);

  useEffect(() => {
    const handle = window.setTimeout(() => { setChecklistQuery(checklistArea.trim()); setChecklistPage(1); }, 250);
    return () => window.clearTimeout(handle);
  }, [checklistArea]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setChecklistLoading(true);
      setChecklistError("");
      const params = new URLSearchParams({ page: String(checklistPage), page_size: String(CHECKLISTS_PAGE_SIZE) });
      if (checklistQuery) params.set("area", checklistQuery);
      if (checklistResult) params.set("result", checklistResult);
      try {
        const response = await fetch(`/api/admin/maintenance/checklists?${params.toString()}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        if (active) setChecklistDirectory(await response.json() as ChecklistDirectory);
      } catch {
        if (active) setChecklistError("No se pudieron cargar las rondas de limpieza.");
      } finally {
        if (active) setChecklistLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [checklistPage, checklistQuery, checklistResult, refresh, onUnauthorized]);

  const tabButton = (value: "equipos" | "tickets" | "bitacora" | "rondas", label: string) => (
    <button type="button" className={tab === value ? "staff-tab-active" : ""} onClick={() => setTab(value)}>{label}</button>
  );

  const equipmentItems = equipmentDirectory?.items ?? [];
  const ticketItems = ticketDirectory?.items ?? [];
  const recordItems = recordDirectory?.items ?? [];
  const checklistItems = checklistDirectory?.items ?? [];
  const ticketSummary = ticketDirectory?.summary ?? { total: 0, open: 0, assigned: 0, in_progress: 0, resolved: 0, cancelled: 0, critical_open: 0 };

  return (
    <>
      <section className="access-summary-band pos-cash-band">
        <div className="access-summary-main">
          <span className="summary-icon"><Wrench size={18} /></span>
          <div>
            <span>MANTENIMIENTO DE EQUIPO</span>
            <strong>{overview ? `${overview.equipment_total} equipos en la flota` : "Consultando…"}</strong>
          </div>
        </div>
        <div className="summary-divider" />
        <div className="summary-stat"><span>OPERATIVOS</span><strong>{overview?.operational ?? "—"}</strong></div>
        <div className="summary-stat"><span>FUERA DE SERVICIO</span><strong>{overview?.out_of_service ?? "—"}</strong></div>
        <div className="summary-stat"><span>TICKETS ABIERTOS</span><strong>{overview?.tickets_open ?? "—"}</strong></div>
        <div className="summary-stat"><span>PREVENTIVOS VENCIDOS</span><strong>{overview?.preventives_due ?? "—"}</strong></div>
        {canReport && <button className="button button-primary" onClick={() => setTicketModalOpen(true)}><AlertTriangle size={16} />Reportar falla</button>}
      </section>

      <div className="staff-tabs pos-tabs">
        {tabButton("equipos", "Equipos")}
        {tabButton("tickets", "Tickets")}
        {tabButton("bitacora", "Bitácora")}
        {tabButton("rondas", "Rondas")}
        <span className="staff-tabs-note"><ShieldCheck size={14} />Un ticket crítico saca el equipo de servicio y lo devuelve al resolverse</span>
      </div>

      {tab === "equipos" && (
        <section className="panel full-panel">
          {areas.length > 0 && (
            <div className="area-status-row">
              {areas.map((area) => (
                <span className="area-status-chip" key={area.area}>
                  <strong>{area.area}</strong>
                  <span className={`status-badge ${availabilityBadges[area.availability]}`}><i />{availabilityLabels[area.availability]}</span>
                </span>
              ))}
            </div>
          )}
          <div className="panel-header access-list-heading">
            <div><p className="section-kicker">FLOTA E INSTALACIONES</p><h2>Equipos</h2></div>
            {canManage && <button className="button button-primary" onClick={() => setEquipmentModal({ equipment: null })}><Plus size={17} />Nuevo equipo</button>}
          </div>
          <div className="table-toolbar">
            <label className="table-search"><Search size={17} /><input value={equipmentSearch} onChange={(event) => setEquipmentSearch(event.target.value)} placeholder="Buscar por nombre, marca o serie" /></label>
            <label className="table-select"><span>Estado</span><select value={equipmentStatus} onChange={(event) => { setEquipmentStatus(event.target.value as "" | EquipmentState); setEquipmentPage(1); }}><option value="">Todos</option><option value="operational">Operativos</option><option value="maintenance">En mantenimiento</option><option value="out_of_service">Fuera de servicio</option><option value="inspection">En revisión</option><option value="retired">Retirados</option></select></label>
            {equipmentQuery || equipmentStatus ? <button className="button button-secondary" onClick={() => { setEquipmentSearch(""); setEquipmentStatus(""); setEquipmentPage(1); }}>Limpiar filtros</button> : <span className="table-hint">Abre un equipo para ver su historial y vincular ejercicios</span>}
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>EQUIPO</th><th>UBICACIÓN</th><th>ESTADO</th><th>TICKETS</th><th>PRÓX. PREVENTIVO</th><th>ÚLTIMO SERVICIO</th><th /></tr></thead>
              <tbody>
                {equipmentLoading ? <tr><td colSpan={7} className="empty-row">Cargando equipos…</td></tr>
                  : equipmentError ? <tr><td colSpan={7} className="empty-row">{equipmentError}</td></tr>
                  : equipmentItems.length === 0 ? <tr><td colSpan={7} className="empty-row">{equipmentQuery || equipmentStatus ? "No hay equipos que coincidan con el filtro." : "Aún no hay equipos registrados."}</td></tr>
                  : equipmentItems.map((equipment) => {
                    const overdue = equipment.next_preventive_due !== null && toDateInputValue(equipment.next_preventive_due) <= todayDateInput() && equipment.status !== "retired";
                    return (
                      <tr key={equipment.id}>
                        <td><div className="person-cell"><span className="pos-row-icon"><Wrench size={15} /></span><span><strong>{equipment.name}</strong><small>{equipment.category}{equipment.brand ? ` · ${equipment.brand}` : ""}{equipment.serial_number ? ` · ${equipment.serial_number}` : ""}</small></span></div></td>
                        <td>{equipment.location ?? "—"}</td>
                        <td><span className={`status-badge ${equipmentStatusBadges[equipment.status]}`}><i />{equipmentStatusLabels[equipment.status]}</span></td>
                        <td>{equipment.open_tickets > 0 ? <span className="status-badge status-warn"><i />{equipment.open_tickets}</span> : "—"}</td>
                        <td>{overdue ? <span className="status-badge status-bad"><i />{formatDateOnly(equipment.next_preventive_due)}</span> : formatDateOnly(equipment.next_preventive_due)}</td>
                        <td>{formatMoment(equipment.last_maintenance_at)}</td>
                        <td><div className="pos-row-actions">
                          <button type="button" className="text-button" onClick={() => setEquipmentDetailId(equipment.id)}>Abrir</button>
                          {canManage && equipment.status !== "retired" && <button type="button" className="text-button" onClick={() => setRecordModalEquipment(equipment)}>Registrar servicio</button>}
                        </div></td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
          <div className="table-bottom">
            <span>{equipmentDirectory?.summary.total ?? 0} equipos · {equipmentDirectory?.summary.operational ?? 0} operativos · {equipmentDirectory?.summary.retired ?? 0} retirados</span>
            {(equipmentDirectory?.pages ?? 0) > 1 && (
              <span className="member-pagination">
                <span>Página {equipmentDirectory?.page ?? 1} de {equipmentDirectory?.pages ?? 1}</span>
                <button type="button" aria-label="Página anterior" disabled={equipmentPage <= 1} onClick={() => setEquipmentPage((value) => Math.max(value - 1, 1))}>‹</button>
                <button type="button" aria-label="Página siguiente" disabled={equipmentPage >= (equipmentDirectory?.pages ?? 1)} onClick={() => setEquipmentPage((value) => value + 1)}>›</button>
              </span>
            )}
          </div>
        </section>
      )}

      {tab === "tickets" && (
        <section className="panel full-panel">
          <div className="panel-header access-list-heading">
            <div><p className="section-kicker">FALLAS Y PREVENTIVOS</p><h2>Tickets</h2></div>
            {canReport && <button className="button button-primary" onClick={() => setTicketModalOpen(true)}><Plus size={17} />Reportar falla</button>}
          </div>
          <div className="table-toolbar">
            <label className="table-search"><Search size={17} /><input value={ticketSearch} onChange={(event) => setTicketSearch(event.target.value)} placeholder="Buscar por folio o título" /></label>
            <label className="table-select"><span>Estado</span><select value={ticketStatus} onChange={(event) => { setTicketStatus(event.target.value as "" | TicketState); setTicketPage(1); }}><option value="">Todos</option><option value="open">Abiertos</option><option value="assigned">Asignados</option><option value="in_progress">En proceso</option><option value="resolved">Resueltos</option><option value="cancelled">Cancelados</option></select></label>
            <label className="table-select"><span>Severidad</span><select value={ticketSeverity} onChange={(event) => { setTicketSeverity(event.target.value as "" | TicketSeverity); setTicketPage(1); }}><option value="">Todas</option><option value="low">Baja</option><option value="medium">Media</option><option value="high">Alta</option><option value="critical">Crítica</option></select></label>
            {ticketQuery || ticketStatus || ticketSeverity ? <button className="button button-secondary" onClick={() => { setTicketSearch(""); setTicketStatus(""); setTicketSeverity(""); setTicketPage(1); }}>Limpiar filtros</button> : <span className="table-hint">{ticketSummary.critical_open} críticos abiertos</span>}
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>FOLIO</th><th>EQUIPO</th><th>TIPO</th><th>SEVERIDAD</th><th>TÍTULO</th><th>ASIGNADO</th><th>REPORTADO</th><th>ESTADO</th><th /></tr></thead>
              <tbody>
                {ticketLoading ? <tr><td colSpan={9} className="empty-row">Cargando tickets…</td></tr>
                  : ticketError ? <tr><td colSpan={9} className="empty-row">{ticketError}</td></tr>
                  : ticketItems.length === 0 ? <tr><td colSpan={9} className="empty-row">{ticketQuery || ticketStatus || ticketSeverity ? "No hay tickets que coincidan con el filtro." : "No hay tickets registrados."}</td></tr>
                  : ticketItems.map((ticket) => (
                    <tr key={ticket.id}>
                      <td><strong>{ticket.code}</strong></td>
                      <td>{ticket.equipment_name}</td>
                      <td>{ticketKindLabels[ticket.kind]}</td>
                      <td><span className={`status-badge ${ticketSeverityBadges[ticket.severity]}`}><i />{ticketSeverityLabels[ticket.severity]}</span></td>
                      <td>{ticket.title}</td>
                      <td>{ticket.assignee_name ?? "Sin asignar"}</td>
                      <td>{formatMoment(ticket.reported_at)}</td>
                      <td><span className={`status-badge ${ticketStatusBadges[ticket.status]}`}><i />{ticketStatusLabels[ticket.status]}</span></td>
                      <td><div className="pos-row-actions"><button type="button" className="text-button" onClick={() => setTicketDetailId(ticket.id)}>Abrir</button></div></td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <div className="table-bottom">
            <span>{ticketSummary.total} tickets · {ticketSummary.open + ticketSummary.assigned + ticketSummary.in_progress} abiertos · {ticketSummary.resolved} resueltos</span>
            {(ticketDirectory?.pages ?? 0) > 1 && (
              <span className="member-pagination">
                <span>Página {ticketDirectory?.page ?? 1} de {ticketDirectory?.pages ?? 1}</span>
                <button type="button" aria-label="Página anterior" disabled={ticketPage <= 1} onClick={() => setTicketPage((value) => Math.max(value - 1, 1))}>‹</button>
                <button type="button" aria-label="Página siguiente" disabled={ticketPage >= (ticketDirectory?.pages ?? 1)} onClick={() => setTicketPage((value) => value + 1)}>›</button>
              </span>
            )}
          </div>
        </section>
      )}

      {tab === "bitacora" && (
        <section className="panel full-panel">
          <div className="panel-header access-list-heading">
            <div><p className="section-kicker">HISTORIAL TÉCNICO</p><h2>Bitácora de mantenimiento</h2></div>
          </div>
          <div className="table-toolbar">
            <label className="table-select"><span>Tipo</span><select value={recordKind} onChange={(event) => { setRecordKind(event.target.value); setRecordPage(1); }}><option value="">Todos</option>{Object.entries(recordKindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            {recordKind ? <button className="button button-secondary" onClick={() => { setRecordKind(""); setRecordPage(1); }}>Limpiar filtro</button> : <span className="table-hint">Los registros son inmutables: cada servicio agrega una fila</span>}
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>EQUIPO</th><th>TIPO</th><th>RESUMEN</th><th>EJECUTADO</th><th>TÉCNICO</th><th>COSTO</th></tr></thead>
              <tbody>
                {recordLoading ? <tr><td colSpan={6} className="empty-row">Cargando bitácora…</td></tr>
                  : recordError ? <tr><td colSpan={6} className="empty-row">{recordError}</td></tr>
                  : recordItems.length === 0 ? <tr><td colSpan={6} className="empty-row">{recordKind ? "No hay registros de ese tipo." : "Aún no hay servicios registrados."}</td></tr>
                  : recordItems.map((record) => (
                    <tr key={record.id}>
                      <td>{record.equipment_name}</td>
                      <td>{recordKindLabels[record.kind] ?? record.kind}</td>
                      <td><div className="person-cell"><span className="pos-row-icon"><ClipboardList size={15} /></span><span><strong>{record.summary}</strong><small>{record.notes ?? "Sin notas"}</small></span></div></td>
                      <td>{formatMoment(record.performed_at)}</td>
                      <td>{record.technician_name ?? "—"}</td>
                      <td>{formatMoney(record.cost_cents)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <div className="table-bottom">
            <span>{recordDirectory?.total ?? 0} registros · costo acumulado {formatMoney(recordDirectory?.total_cost_cents ?? 0)}</span>
            {(recordDirectory?.pages ?? 0) > 1 && (
              <span className="member-pagination">
                <span>Página {recordDirectory?.page ?? 1} de {recordDirectory?.pages ?? 1}</span>
                <button type="button" aria-label="Página anterior" disabled={recordPage <= 1} onClick={() => setRecordPage((value) => Math.max(value - 1, 1))}>‹</button>
                <button type="button" aria-label="Página siguiente" disabled={recordPage >= (recordDirectory?.pages ?? 1)} onClick={() => setRecordPage((value) => value + 1)}>›</button>
              </span>
            )}
          </div>
        </section>
      )}

      {tab === "rondas" && (
        <section className="panel full-panel">
          <div className="panel-header access-list-heading">
            <div><p className="section-kicker">LIMPIEZA E INSPECCIÓN</p><h2>Rondas por área</h2></div>
            {canManage && <button className="button button-primary" onClick={() => setChecklistModalOpen(true)}><Plus size={17} />Registrar ronda</button>}
          </div>
          <div className="table-toolbar">
            <label className="table-search"><Search size={17} /><input value={checklistArea} onChange={(event) => setChecklistArea(event.target.value)} placeholder="Buscar por área" /></label>
            <label className="table-select"><span>Resultado</span><select value={checklistResult} onChange={(event) => { setChecklistResult(event.target.value); setChecklistPage(1); }}><option value="">Todos</option><option value="ok">Sin novedad</option><option value="observation">Con observación</option><option value="pending">Pendiente</option></select></label>
            {checklistQuery || checklistResult ? <button className="button button-secondary" onClick={() => { setChecklistArea(""); setChecklistResult(""); setChecklistPage(1); }}>Limpiar filtros</button> : <span className="table-hint">Una observación exige describirse</span>}
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>ÁREA</th><th>RESULTADO</th><th>OBSERVACIÓN</th><th>EJECUTADO</th><th>QUIÉN</th></tr></thead>
              <tbody>
                {checklistLoading ? <tr><td colSpan={5} className="empty-row">Cargando rondas…</td></tr>
                  : checklistError ? <tr><td colSpan={5} className="empty-row">{checklistError}</td></tr>
                  : checklistItems.length === 0 ? <tr><td colSpan={5} className="empty-row">{checklistQuery || checklistResult ? "No hay rondas que coincidan con el filtro." : "Aún no hay rondas registradas."}</td></tr>
                  : checklistItems.map((item) => (
                    <tr key={item.id}>
                      <td>{item.area}</td>
                      <td><span className={`status-badge ${item.result === "ok" ? "status-good" : item.result === "observation" ? "status-warn" : "status-neutral"}`}><i />{checklistResultLabels[item.result]}</span></td>
                      <td>{item.observations ?? "—"}</td>
                      <td>{formatMoment(item.performed_at)}</td>
                      <td>{item.performer_email ?? "—"}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <div className="table-bottom">
            <span>{checklistDirectory?.total ?? 0} rondas registradas</span>
            {(checklistDirectory?.pages ?? 0) > 1 && (
              <span className="member-pagination">
                <span>Página {checklistDirectory?.page ?? 1} de {checklistDirectory?.pages ?? 1}</span>
                <button type="button" aria-label="Página anterior" disabled={checklistPage <= 1} onClick={() => setChecklistPage((value) => Math.max(value - 1, 1))}>‹</button>
                <button type="button" aria-label="Página siguiente" disabled={checklistPage >= (checklistDirectory?.pages ?? 1)} onClick={() => setChecklistPage((value) => value + 1)}>›</button>
              </span>
            )}
          </div>
        </section>
      )}

      {equipmentModal && <EquipmentFormModal equipment={equipmentModal.equipment} onClose={() => setEquipmentModal(null)} onSaved={(message) => { setEquipmentModal(null); reload(); onToast(message); }} onUnauthorized={onUnauthorized} />}

      {equipmentDetailId && <EquipmentDetailModal equipmentId={equipmentDetailId} canManage={canManage} canReport={canReport} technicians={technicians} onClose={() => setEquipmentDetailId(null)} onChanged={reload} onToast={onToast} onUnauthorized={onUnauthorized} onEdit={(equipment) => { setEquipmentDetailId(null); setEquipmentModal({ equipment }); }} onRecord={(equipment) => { setEquipmentDetailId(null); setRecordModalEquipment(equipment); }} />}

      {recordModalEquipment && <MaintenanceRecordModal equipment={recordModalEquipment} technicians={technicians} onClose={() => setRecordModalEquipment(null)} onSaved={(message) => { setRecordModalEquipment(null); reload(); onToast(message); }} onUnauthorized={onUnauthorized} />}

      {ticketModalOpen && <TicketFormModal equipment={equipmentChoices} technicians={technicians} onClose={() => setTicketModalOpen(false)} onSaved={(message) => { setTicketModalOpen(false); reload(); onToast(message); }} onUnauthorized={onUnauthorized} />}

      {ticketDetailId && <TicketDetailModal ticketId={ticketDetailId} canManage={canManage} technicians={technicians} onClose={() => setTicketDetailId(null)} onChanged={reload} onToast={onToast} onUnauthorized={onUnauthorized} />}

      {checklistModalOpen && <ChecklistFormModal onClose={() => setChecklistModalOpen(false)} onSaved={(message) => { setChecklistModalOpen(false); reload(); onToast(message); }} onUnauthorized={onUnauthorized} />}
    </>
  );
}

function EquipmentFormModal({ equipment, onClose, onSaved, onUnauthorized }: { equipment: BackendEquipment | null; onClose: () => void; onSaved: (message: string) => void; onUnauthorized: () => void }) {
  const [name, setName] = useState(equipment?.name ?? "");
  const [category, setCategory] = useState(equipment?.category ?? "");
  const [brand, setBrand] = useState(equipment?.brand ?? "");
  const [model, setModel] = useState(equipment?.model ?? "");
  const [serialNumber, setSerialNumber] = useState(equipment?.serial_number ?? "");
  const [location, setLocation] = useState(equipment?.location ?? "");
  const [acquiredOn, setAcquiredOn] = useState(toDateInputValue(equipment?.acquired_on ?? null));
  const [usefulLife, setUsefulLife] = useState(equipment?.useful_life_months === null || equipment?.useful_life_months === undefined ? "" : String(equipment.useful_life_months));
  const [cost, setCost] = useState(equipment ? formatMoney(equipment.purchase_cost_cents) : "");
  const [nextPreventive, setNextPreventive] = useState(toDateInputValue(equipment?.next_preventive_due ?? null));
  const [notes, setNotes] = useState(equipment?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim() || !category.trim()) { setError("Nombre y categoría son obligatorios."); return; }
    const costCents = cost.trim() ? parseMoneyToCents(cost) : 0;
    if (costCents === null) { setError("El costo no es válido."); return; }
    setBusy(true);
    setError("");
    const body: Record<string, unknown> = {
      name: name.trim(),
      category: category.trim(),
      brand: brand.trim() || null,
      model: model.trim() || null,
      serial_number: serialNumber.trim() || null,
      location: location.trim() || null,
      acquired_on: acquiredOn || null,
      useful_life_months: usefulLife.trim() ? Number(usefulLife) : null,
      purchase_cost_cents: costCents,
      next_preventive_due: nextPreventive || null,
      notes: notes.trim() || null,
    };
    try {
      const response = await fetch(equipment ? `/api/admin/maintenance/equipment/${equipment.id}` : "/api/admin/maintenance/equipment", {
        method: equipment ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo guardar el equipo."); return; }
      onSaved(equipment ? `Equipo actualizado: ${name.trim()}.` : `Equipo registrado: ${name.trim()}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="equipment-modal-title">
        <div className="modal-header"><span className="modal-icon"><Wrench size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">FLOTA DE EQUIPOS</p>
        <h2 id="equipment-modal-title">{equipment ? "Editar equipo" : "Nuevo equipo"}</h2>
        <p className="modal-subtitle">El equipo nunca se elimina: al darse de baja se marca como retirado para conservar su historial.</p>
        <form onSubmit={submit}>
          <div className="form-grid">
            <label className="form-field"><span>Nombre</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Ej. Caminadora Pro" maxLength={160} autoFocus /></label>
            <label className="form-field"><span>Categoría</span><input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="Cardio" maxLength={60} /></label>
          </div>
          <div className="form-grid">
            <label className="form-field"><span>Marca</span><input value={brand} onChange={(event) => setBrand(event.target.value)} placeholder="Opcional" maxLength={80} /></label>
            <label className="form-field"><span>Modelo</span><input value={model} onChange={(event) => setModel(event.target.value)} placeholder="Opcional" maxLength={80} /></label>
          </div>
          <div className="form-grid">
            <label className="form-field"><span>Número de serie</span><input value={serialNumber} onChange={(event) => setSerialNumber(event.target.value)} placeholder="Opcional" maxLength={80} /></label>
            <label className="form-field"><span>Ubicación</span><input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="Ej. Piso de pesas" maxLength={80} /></label>
          </div>
          <div className="form-grid">
            <label className="form-field"><span>Fecha de compra</span><input type="date" value={acquiredOn} onChange={(event) => setAcquiredOn(event.target.value)} /></label>
            <label className="form-field"><span>Vida útil (meses)</span><input value={usefulLife} inputMode="numeric" onChange={(event) => setUsefulLife(event.target.value)} placeholder="Opcional" /></label>
          </div>
          <div className="form-grid">
            <label className="form-field"><span>Costo de compra</span><input value={cost} onChange={(event) => setCost(event.target.value)} placeholder="0.00" /></label>
            <label className="form-field"><span>Próximo preventivo</span><input type="date" value={nextPreventive} onChange={(event) => setNextPreventive(event.target.value)} /></label>
          </div>
          <label className="form-field"><span>Notas</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={2} placeholder="Opcional" /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : equipment ? "Guardar cambios" : "Registrar equipo"}</button></div>
        </form>
      </section>
    </div>
  );
}

function EquipmentDetailModal({ equipmentId, canManage, canReport, technicians, onClose, onChanged, onToast, onUnauthorized, onEdit, onRecord }: { equipmentId: string; canManage: boolean; canReport: boolean; technicians: BackendEmployee[]; onClose: () => void; onChanged: () => void; onToast: (message: string) => void; onUnauthorized: () => void; onEdit: (equipment: BackendEquipment) => void; onRecord: (equipment: BackendEquipment) => void }) {
  const [detail, setDetail] = useState<EquipmentDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [status, setStatus] = useState<EquipmentState>("operational");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`/api/admin/maintenance/equipment/${equipmentId}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        if (!active) return;
        const data = await response.json() as EquipmentDetail;
        setDetail(data);
        setStatus(data.equipment.status === "retired" ? "operational" : data.equipment.status);
      } catch {
        if (active) setError("No se pudo cargar el equipo.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [equipmentId, refresh, onUnauthorized]);

  const changeStatus = async () => {
    setBusy(true);
    try {
      const response = await fetch(`/api/admin/maintenance/equipment/${equipmentId}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo cambiar el estado."); return; }
      setRefresh((value) => value + 1);
      onChanged();
      onToast(`Estado actualizado a ${equipmentStatusLabels[status]}.`);
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const retire = async () => {
    try {
      const response = await fetch(`/api/admin/maintenance/equipment/${equipmentId}/retire`, { method: "POST" });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo dar de baja el equipo."); return; }
      setRefresh((value) => value + 1);
      onChanged();
      onToast("Equipo retirado. Su historial se conserva.");
    } catch {
      onToast("No se pudo conectar con el backend.");
    }
  };

  const equipment = detail?.equipment ?? null;

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="equipment-detail-title">
        <div className="modal-header"><span className="modal-icon"><Wrench size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">EQUIPO</p>
        <h2 id="equipment-detail-title">{equipment?.name ?? "Cargando…"}</h2>
        {equipment && (
          <p className="modal-subtitle">
            {equipmentStatusLabels[equipment.status]} · {equipment.category}
            {equipment.location ? ` · ${equipment.location}` : ""}
            {equipment.serial_number ? ` · Serie ${equipment.serial_number}` : ""}
          </p>
        )}
        {loading && !detail && <p className="panel-hint">Cargando equipo…</p>}
        {error && <div className="login-error" role="alert">{error}</div>}

        {equipment && (
          <div className="detail-section">
            <div className="detail-meta-grid">
              <span><small>Marca / modelo</small><strong>{[equipment.brand, equipment.model].filter(Boolean).join(" ") || "—"}</strong></span>
              <span><small>Compra</small><strong>{formatDateOnly(equipment.acquired_on)} · {formatMoney(equipment.purchase_cost_cents)}</strong></span>
              <span><small>Vida útil</small><strong>{equipment.useful_life_months ? `${equipment.useful_life_months} meses` : "—"}</strong></span>
              <span><small>Próximo preventivo</small><strong>{formatDateOnly(equipment.next_preventive_due)}</strong></span>
              <span><small>Último servicio</small><strong>{formatMoment(equipment.last_maintenance_at)}</strong></span>
              <span><small>Tickets abiertos</small><strong>{equipment.open_tickets}</strong></span>
            </div>
            {equipment.notes && <p className="panel-hint">{equipment.notes}</p>}
          </div>
        )}

        {equipment && equipment.status !== "retired" && canManage && (
          <div className="detail-section">
            <p className="form-section-label">Acciones</p>
            <div className="inline-form">
              <label className="form-field"><span>Estado</span><select value={status} disabled={!canReport} onChange={(event) => setStatus(event.target.value as EquipmentState)}><option value="operational">Operativo</option><option value="maintenance">En mantenimiento</option><option value="out_of_service">Fuera de servicio</option><option value="inspection">En revisión</option></select></label>
              <button type="button" className="button button-secondary" disabled={busy || !canReport} onClick={changeStatus}>Cambiar estado</button>
              <button type="button" className="button button-secondary" onClick={() => onRecord(equipment)}>Registrar servicio</button>
              <button type="button" className="button button-secondary" onClick={() => onEdit(equipment)}>Editar ficha</button>
              <button type="button" className="button button-danger" onClick={retire}><Trash2 size={15} />Dar de baja</button>
            </div>
          </div>
        )}

        {detail && detail.exercises.length > 0 && (
          <div className="detail-section">
            <p className="form-section-label">Ejercicios que usan este equipo</p>
            <div className="chip-row">{detail.exercises.map((exercise) => <span className="info-chip" key={exercise.id}>{exercise.name} · {exercise.muscle_group}</span>)}</div>
          </div>
        )}

        {detail && (
          <div className="detail-section">
            <p className="form-section-label">Historial técnico ({detail.records.length})</p>
            {detail.records.length === 0
              ? <p className="panel-hint">Sin servicios registrados.</p>
              : (
                <table className="data-table compact-table">
                  <thead><tr><th>TIPO</th><th>RESUMEN</th><th>EJECUTADO</th><th>COSTO</th></tr></thead>
                  <tbody>{detail.records.map((record) => (
                    <tr key={record.id}><td>{recordKindLabels[record.kind] ?? record.kind}</td><td>{record.summary}</td><td>{formatMoment(record.performed_at)}</td><td>{formatMoney(record.cost_cents)}</td></tr>
                  ))}</tbody>
                </table>
              )}
          </div>
        )}

        {detail && (
          <div className="detail-section">
            <p className="form-section-label">Tickets ({detail.tickets.length})</p>
            {detail.tickets.length === 0
              ? <p className="panel-hint">Sin tickets registrados.</p>
              : (
                <table className="data-table compact-table">
                  <thead><tr><th>FOLIO</th><th>TÍTULO</th><th>SEVERIDAD</th><th>ESTADO</th></tr></thead>
                  <tbody>{detail.tickets.map((ticket) => (
                    <tr key={ticket.id}>
                      <td>{ticket.code}</td><td>{ticket.title}</td>
                      <td><span className={`status-badge ${ticketSeverityBadges[ticket.severity]}`}><i />{ticketSeverityLabels[ticket.severity]}</span></td>
                      <td><span className={`status-badge ${ticketStatusBadges[ticket.status]}`}><i />{ticketStatusLabels[ticket.status]}</span></td>
                    </tr>
                  ))}</tbody>
                </table>
              )}
          </div>
        )}

        <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cerrar</button></div>
      </section>
    </div>
  );
}

function MaintenanceRecordModal({ equipment, technicians, onClose, onSaved, onUnauthorized }: { equipment: BackendEquipment; technicians: BackendEmployee[]; onClose: () => void; onSaved: (message: string) => void; onUnauthorized: () => void }) {
  const [kind, setKind] = useState("preventive");
  const [summary, setSummary] = useState("");
  const [performedAt, setPerformedAt] = useState("");
  const [cost, setCost] = useState("");
  const [technicianId, setTechnicianId] = useState("");
  const [nextDue, setNextDue] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!summary.trim()) { setError("El resumen es obligatorio."); return; }
    const costCents = cost.trim() ? parseMoneyToCents(cost) : 0;
    if (costCents === null) { setError("El costo no es válido."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/maintenance/equipment/${equipment.id}/records`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind,
          summary: summary.trim(),
          performed_at: performedAt ? fromDateTimeLocalValue(performedAt) : null,
          cost_cents: costCents,
          technician_id: technicianId || null,
          next_due_on: nextDue || null,
          notes: notes.trim() || null,
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo registrar el servicio."); return; }
      onSaved(`Servicio registrado en ${equipment.name}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="record-modal-title">
        <div className="modal-header"><span className="modal-icon"><ClipboardList size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">HISTORIAL TÉCNICO</p>
        <h2 id="record-modal-title">Registrar servicio</h2>
        <p className="modal-subtitle">{equipment.name} · {equipment.location ?? "Sin ubicación"}</p>
        <form onSubmit={submit}>
          <div className="form-grid">
            <label className="form-field"><span>Tipo</span><select value={kind} onChange={(event) => setKind(event.target.value)}>{Object.entries(recordKindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label className="form-field"><span>Ejecutado</span><input type="datetime-local" value={performedAt} onChange={(event) => setPerformedAt(event.target.value)} /></label>
          </div>
          <label className="form-field"><span>Resumen</span><input value={summary} onChange={(event) => setSummary(event.target.value)} placeholder="Ej. Lubricación y ajuste de banda" maxLength={200} autoFocus /></label>
          <div className="form-grid">
            <label className="form-field"><span>Costo</span><input value={cost} onChange={(event) => setCost(event.target.value)} placeholder="0.00" /></label>
            <label className="form-field"><span>Técnico</span><select value={technicianId} onChange={(event) => setTechnicianId(event.target.value)}><option value="">Sin asignar</option>{technicians.map((technician) => <option key={technician.id} value={technician.id}>{technician.first_name} {technician.last_name}</option>)}</select></label>
          </div>
          <label className="form-field"><span>Próximo preventivo</span><input type="date" value={nextDue} onChange={(event) => setNextDue(event.target.value)} /></label>
          <label className="form-field"><span>Notas</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={2} placeholder="Opcional" /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : "Registrar servicio"}</button></div>
        </form>
      </section>
    </div>
  );
}

function TicketFormModal({ equipment, technicians, onClose, onSaved, onUnauthorized }: { equipment: EquipmentChoice[]; technicians: BackendEmployee[]; onClose: () => void; onSaved: (message: string) => void; onUnauthorized: () => void }) {
  const [equipmentId, setEquipmentId] = useState("");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<TicketKind>("corrective");
  const [severity, setSeverity] = useState<TicketSeverity>("medium");
  const [description, setDescription] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [scheduledFor, setScheduledFor] = useState("");
  const [block, setBlock] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!equipmentId) { setError("Selecciona el equipo."); return; }
    if (!title.trim()) { setError("El título es obligatorio."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/maintenance/tickets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          equipment_id: equipmentId,
          title: title.trim(),
          kind,
          severity,
          description: description.trim() || null,
          assigned_to: assignedTo || null,
          scheduled_for: scheduledFor || null,
          block_equipment: block,
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo registrar el ticket."); return; }
      onSaved(`Ticket registrado: ${title.trim()}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="ticket-modal-title">
        <div className="modal-header"><span className="modal-icon"><AlertTriangle size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">TICKETS DE MANTENIMIENTO</p>
        <h2 id="ticket-modal-title">Reportar falla</h2>
        <p className="modal-subtitle">Un ticket con severidad crítica saca el equipo de servicio de inmediato.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Equipo</span><select value={equipmentId} onChange={(event) => setEquipmentId(event.target.value)} autoFocus><option value="">Selecciona…</option>{equipment.map((choice) => <option key={choice.id} value={choice.id}>{choice.name}{choice.location ? ` · ${choice.location}` : ""}</option>)}</select></label>
          <label className="form-field"><span>Título</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Ej. Banda desgastada" maxLength={160} /></label>
          <div className="form-grid">
            <label className="form-field"><span>Tipo</span><select value={kind} onChange={(event) => setKind(event.target.value as TicketKind)}><option value="corrective">Correctivo</option><option value="preventive">Preventivo</option></select></label>
            <label className="form-field"><span>Severidad</span><select value={severity} onChange={(event) => setSeverity(event.target.value as TicketSeverity)}><option value="low">Baja</option><option value="medium">Media</option><option value="high">Alta</option><option value="critical">Crítica</option></select></label>
          </div>
          <label className="form-field"><span>Descripción</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={2} placeholder="Opcional" /></label>
          <div className="form-grid">
            <label className="form-field"><span>Asignar a</span><select value={assignedTo} onChange={(event) => setAssignedTo(event.target.value)}><option value="">Sin asignar</option>{technicians.map((technician) => <option key={technician.id} value={technician.id}>{technician.first_name} {technician.last_name}</option>)}</select></label>
            <label className="form-field"><span>Programado para</span><input type="date" value={scheduledFor} onChange={(event) => setScheduledFor(event.target.value)} /></label>
          </div>
          <label className="form-check"><input type="checkbox" checked={block} onChange={(event) => setBlock(event.target.checked)} /><span>Sacar el equipo de servicio ahora</span></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Registrando…" : "Reportar falla"}</button></div>
        </form>
      </section>
    </div>
  );
}

function TicketDetailModal({ ticketId, canManage, technicians, onClose, onChanged, onToast, onUnauthorized }: { ticketId: string; canManage: boolean; technicians: BackendEmployee[]; onClose: () => void; onChanged: () => void; onToast: (message: string) => void; onUnauthorized: () => void }) {
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [assignee, setAssignee] = useState("");
  const [notes, setNotes] = useState("");
  const [cost, setCost] = useState("");
  const [nextDue, setNextDue] = useState("");
  const [technicianId, setTechnicianId] = useState("");
  const [cancelReason, setCancelReason] = useState("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`/api/admin/maintenance/tickets/${ticketId}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) throw new Error("failed");
        if (!active) return;
        const data = await response.json() as TicketDetail;
        setDetail(data);
        setAssignee(data.ticket.assigned_to ?? "");
        setTechnicianId(data.ticket.assigned_to ?? "");
      } catch {
        if (active) setError("No se pudo cargar el ticket.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [ticketId, refresh, onUnauthorized]);

  const run = async (path: string, body: unknown, method: "POST" | "PATCH", success: string) => {
    setBusy(true);
    try {
      const response = await fetch(`/api/admin/maintenance/tickets/${ticketId}${path}`, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { onToast(payload.detail || "No se pudo actualizar el ticket."); return; }
      setRefresh((value) => value + 1);
      onChanged();
      onToast(success);
    } catch {
      onToast("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  const resolve = async () => {
    if (!notes.trim()) { onToast("Describe la solución antes de resolver."); return; }
    const costCents = cost.trim() ? parseMoneyToCents(cost) : null;
    if (cost.trim() && costCents === null) { onToast("El costo no es válido."); return; }
    await run("/resolve", { resolution_notes: notes.trim(), cost_cents: costCents, next_due_on: nextDue || null, technician_id: technicianId || null }, "POST", "Ticket resuelto y servicio registrado.");
    setNotes(""); setCost(""); setNextDue("");
  };

  const ticket = detail?.ticket ?? null;
  const open = ticket !== null && (ticket.status === "open" || ticket.status === "assigned" || ticket.status === "in_progress");

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="ticket-detail-title">
        <div className="modal-header"><span className="modal-icon"><AlertTriangle size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">TICKET {ticket?.code ?? ""}</p>
        <h2 id="ticket-detail-title">{ticket?.title ?? "Cargando…"}</h2>
        {ticket && (
          <p className="modal-subtitle">
            {ticket.equipment_name} · {ticketKindLabels[ticket.kind]} · <span className={`status-badge ${ticketSeverityBadges[ticket.severity]}`}><i />{ticketSeverityLabels[ticket.severity]}</span> · <span className={`status-badge ${ticketStatusBadges[ticket.status]}`}><i />{ticketStatusLabels[ticket.status]}</span>
          </p>
        )}
        {loading && !detail && <p className="panel-hint">Cargando ticket…</p>}
        {error && <div className="login-error" role="alert">{error}</div>}

        {ticket && (
          <div className="detail-section">
            <div className="detail-meta-grid">
              <span><small>Reportó</small><strong>{ticket.reporter_email ?? "—"}</strong></span>
              <span><small>Reportado</small><strong>{formatMoment(ticket.reported_at)}</strong></span>
              <span><small>Asignado a</small><strong>{ticket.assignee_name ?? "Sin asignar"}</strong></span>
              <span><small>Programado</small><strong>{formatDateOnly(ticket.scheduled_for)}</strong></span>
              <span><small>Resuelto</small><strong>{formatMoment(ticket.resolved_at)}</strong></span>
              <span><small>Costo</small><strong>{formatMoney(ticket.cost_cents)}</strong></span>
            </div>
            {ticket.description && <p className="panel-hint">{ticket.description}</p>}
            {ticket.blocked_equipment && <p className="panel-hint"><AlertTriangle size={13} /> Este ticket mantiene el equipo fuera de servicio.</p>}
            {ticket.resolution_notes && <p className="panel-hint"><strong>Solución:</strong> {ticket.resolution_notes}</p>}
            {detail?.record && <p className="panel-hint">Registro #{detail.record.id.slice(0, 8)} · {recordKindLabels[detail.record.kind] ?? detail.record.kind} · {formatMoney(detail.record.cost_cents)}</p>}
          </div>
        )}

        {ticket && open && canManage && (
          <>
            <div className="detail-section">
              <p className="form-section-label">Gestión</p>
              <div className="inline-form">
                <label className="form-field"><span>Asignar a</span><select value={assignee} onChange={(event) => setAssignee(event.target.value)}><option value="">Sin asignar</option>{technicians.map((technician) => <option key={technician.id} value={technician.id}>{technician.first_name} {technician.last_name}</option>)}</select></label>
                <button type="button" className="button button-secondary" disabled={busy} onClick={() => run("", { assigned_to: assignee || null }, "PATCH", "Ticket actualizado.")}>Guardar asignación</button>
                {ticket.status !== "in_progress" && <button type="button" className="button button-secondary" disabled={busy} onClick={() => run("/start", undefined, "POST", "Ticket en proceso.")}>Iniciar trabajo</button>}
              </div>
            </div>
            <div className="detail-section">
              <p className="form-section-label">Resolver</p>
              <label className="form-field"><span>Solución</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={2} placeholder="Describe el trabajo realizado" /></label>
              <div className="form-grid">
                <label className="form-field"><span>Costo</span><input value={cost} onChange={(event) => setCost(event.target.value)} placeholder="0.00" /></label>
                <label className="form-field"><span>Técnico</span><select value={technicianId} onChange={(event) => setTechnicianId(event.target.value)}><option value="">Sin asignar</option>{technicians.map((technician) => <option key={technician.id} value={technician.id}>{technician.first_name} {technician.last_name}</option>)}</select></label>
              </div>
              <div className="inline-form">
                <label className="form-field"><span>Próximo preventivo</span><input type="date" value={nextDue} onChange={(event) => setNextDue(event.target.value)} /></label>
                <button type="button" className="button button-primary" disabled={busy} onClick={resolve}><Check size={15} />Resolver ticket</button>
              </div>
            </div>
            <div className="detail-section">
              <p className="form-section-label">Cancelar</p>
              <div className="inline-form">
                <label className="form-field inline-grow"><span>Motivo</span><input value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} placeholder="Opcional" /></label>
                <button type="button" className="button button-danger" disabled={busy} onClick={() => run("/cancel", { reason: cancelReason.trim() || null }, "POST", "Ticket cancelado.")}>Cancelar ticket</button>
              </div>
            </div>
          </>
        )}

        <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cerrar</button></div>
      </section>
    </div>
  );
}

function ChecklistFormModal({ onClose, onSaved, onUnauthorized }: { onClose: () => void; onSaved: (message: string) => void; onUnauthorized: () => void }) {
  const [area, setArea] = useState("");
  const [result, setResult] = useState<"ok" | "observation" | "pending">("ok");
  const [observations, setObservations] = useState("");
  const [performedAt, setPerformedAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!area.trim()) { setError("El área es obligatoria."); return; }
    if (result === "observation" && !observations.trim()) { setError("Describe la observación."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/maintenance/checklists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          area: area.trim(),
          result,
          observations: observations.trim() || null,
          performed_at: performedAt ? fromDateTimeLocalValue(performedAt) : null,
        }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      const payload = await response.json().catch(() => ({})) as { detail?: string };
      if (!response.ok) { setError(payload.detail || "No se pudo registrar la ronda."); return; }
      onSaved(`Ronda registrada en ${area.trim()}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="checklist-modal-title">
        <div className="modal-header"><span className="modal-icon"><ClipboardList size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">LIMPIEZA E INSPECCIÓN</p>
        <h2 id="checklist-modal-title">Registrar ronda</h2>
        <p className="modal-subtitle">El resultado de la ronda queda en la bitácora de la operación.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Área</span><input value={area} onChange={(event) => setArea(event.target.value)} placeholder="Ej. Vestidores" maxLength={80} autoFocus /></label>
          <div className="form-grid">
            <label className="form-field"><span>Resultado</span><select value={result} onChange={(event) => setResult(event.target.value as "ok" | "observation" | "pending")}><option value="ok">Sin novedad</option><option value="observation">Con observación</option><option value="pending">Pendiente</option></select></label>
            <label className="form-field"><span>Fecha</span><input type="datetime-local" value={performedAt} onChange={(event) => setPerformedAt(event.target.value)} /></label>
          </div>
          <label className="form-field"><span>Observaciones</span><textarea value={observations} onChange={(event) => setObservations(event.target.value)} rows={2} placeholder={result === "observation" ? "Requerido" : "Opcional"} /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : "Registrar ronda"}</button></div>
        </form>
      </section>
    </div>
  );
}

function ModulePreview({ page, onReturn }: { page: PageName; onReturn: () => void }) {
  return <section className="module-placeholder"><span className="placeholder-icon"><Dumbbell size={22} /></span><p className="section-kicker">SIGUIENTE EN LA RUTA</p><h2>{page}</h2><p>Esta sección está en diseño. El panel muestra ahora el flujo inicial de accesos, socios y operación del equipo.</p><button className="button button-secondary" onClick={onReturn}><ArrowRight className="back-arrow" size={16} />Volver al resumen</button></section>;
}

const MANUAL_REASONS = ["Cortesía autorizada", "Visita de prueba", "Soporte de gerente", "Incidencia con credencial"];

function ManualMemberRow({ member, onSelect }: { member: BackendMember; onSelect: () => void }) {
  const initials = `${member.first_name[0] ?? ""}${member.last_name[0] ?? ""}`.toUpperCase();
  return (
    <button type="button" onClick={onSelect}>
      <span className={`person-avatar ${memberAvatarColor(member.id)}`}>{initials}</span>
      <span><strong>{member.first_name} {member.last_name}</strong><small>{member.email ?? member.plan_name ?? "Sin datos"}</small></span>
    </button>
  );
}

function ManualAccessModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [memberQuery, setMemberQuery] = useState("");
  const [results, setResults] = useState<BackendMember[]>([]);
  const [selected, setSelected] = useState<BackendMember | null>(null);
  const [reason, setReason] = useState(MANUAL_REASONS[0]);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const term = memberQuery.trim();
    if (selected || term.length < 2) {
      setResults([]);
      return;
    }
    let active = true;
    const handle = window.setTimeout(async () => {
      setSearching(true);
      try {
        const response = await fetch(`/api/admin/members?search=${encodeURIComponent(term)}&page_size=6`, { cache: "no-store" });
        if (response.ok) {
          const directory = await response.json() as MemberDirectory;
          if (active) setResults(directory.items);
        } else if (active) {
          setResults([]);
        }
      } catch {
        if (active) setResults([]);
      } finally {
        if (active) setSearching(false);
      }
    }, 250);
    return () => { active = false; window.clearTimeout(handle); };
  }, [memberQuery, selected]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) {
      setError("Selecciona un socio del directorio.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/access-events/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ member_id: selected.id, note: reason, reader_id: "Recepción" }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        setError(payload.detail || "No se pudo registrar el acceso manual.");
        return;
      }
      onCreated();
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="manual-title">
        <div className="modal-header"><span className="modal-icon"><DoorOpen size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">REGISTRO EN LA BITÁCORA · SIN APERTURA DE TORNIQUETE</p><h2 id="manual-title">Registrar acceso manual</h2><p className="modal-subtitle">Autoriza la entrada de un socio y guarda el motivo en la bitácora del club.</p>
        <form onSubmit={submit}>
          {selected ? (
            <div className="manual-member">
              <div className="person-cell">
                <span className={`person-avatar ${memberAvatarColor(selected.id)}`}>{`${selected.first_name[0] ?? ""}${selected.last_name[0] ?? ""}`.toUpperCase()}</span>
                <span><strong>{selected.first_name} {selected.last_name}</strong><small>{selected.plan_name ?? "Sin membresía"}</small></span>
              </div>
              <button type="button" className="button button-secondary" onClick={() => { setSelected(null); setMemberQuery(""); setResults([]); }}>Cambiar</button>
            </div>
          ) : (
            <>
              <label className="form-field"><span>Socio</span><input value={memberQuery} onChange={(event) => setMemberQuery(event.target.value)} placeholder="Buscar por nombre, correo o plan" autoFocus autoComplete="off" /></label>
              {searching && <p className="modal-hint">Buscando…</p>}
              {!searching && memberQuery.trim().length >= 2 && results.length === 0 && <p className="modal-hint">Sin coincidencias en el directorio.</p>}
              {results.length > 0 && (
                <ul className="manual-results">
                  {results.map((member) => (
                    <li key={member.id}>
                      <ManualMemberRow member={member} onSelect={() => { setSelected(member); setResults([]); }} />
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
          <label className="form-field"><span>Motivo de la excepción</span><select value={reason} onChange={(event) => setReason(event.target.value)}>{MANUAL_REASONS.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-note"><ShieldCheck size={16} /><span>Queda registrado quién autoriza y a qué socio; no abre torniquetes ni cobra.</span></div>
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy || !selected}><Check size={16} />{busy ? "Registrando…" : "Registrar acceso"}</button></div>
        </form>
      </section>
    </div>
  );
}

function NewMemberModal({ onClose, onCreated }: { onClose: () => void; onCreated: (fullName: string) => void }) {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [consent, setConsent] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!firstName.trim() || !lastName.trim()) {
      setError("El nombre y los apellidos son obligatorios.");
      return;
    }
    if (!email.trim() && !phone.trim()) {
      setError("Indica un correo o un teléfono de contacto.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/members", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          email: email.trim() || null,
          phone: phone.trim() || null,
          privacy_notice_accepted: consent,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        setError(payload.detail || "No se pudo registrar el alta.");
        return;
      }
      const created = await response.json() as { first_name: string; last_name: string };
      onCreated(`${created.first_name} ${created.last_name}`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="new-member-title">
        <div className="modal-header"><span className="modal-icon"><UserPlus size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">ALTA DE SOCIO · DATOS Y CONSENTIMIENTO</p><h2 id="new-member-title">Nuevo socio</h2><p className="modal-subtitle">Registra al socio y su consentimiento de privacidad. El plan se asigna después desde la ficha del socio (sin cobro); el primer cobro se hará al conectar la pasarela de pago.</p>
        <form onSubmit={submit}>
          <div className="form-row">
            <label className="form-field"><span>Nombre</span><input value={firstName} onChange={(event) => setFirstName(event.target.value)} placeholder="Nombre" autoFocus autoComplete="given-name" /></label>
            <label className="form-field"><span>Apellidos</span><input value={lastName} onChange={(event) => setLastName(event.target.value)} placeholder="Apellidos" autoComplete="family-name" /></label>
          </div>
          <label className="form-field"><span>Correo electrónico</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="socio@correo.com" autoComplete="email" /></label>
          <label className="form-field"><span>Teléfono</span><input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="55 0000 0000" autoComplete="tel" /></label>
          <label className="form-check"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /><span>El socio aceptó el aviso de privacidad; el consentimiento queda registrado con fecha.</span></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-note"><ShieldCheck size={16} /><span>El alta queda pendiente hasta asignar plan. Puedes asignarlo luego desde la ficha del socio (sin cobro); aquí no se realiza ningún cargo.</span></div>
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Registrando…" : "Registrar alta"}</button></div>
        </form>
      </section>
    </div>
  );
}

function MemberModal({ member, onClose, onChanged }: { member: BackendMember; onClose: () => void; onChanged: (message: string) => void }) {
  const [firstName, setFirstName] = useState(member.first_name);
  const [lastName, setLastName] = useState(member.last_name);
  const [email, setEmail] = useState(member.email ?? "");
  const [phone, setPhone] = useState(member.phone ?? "");
  const [membershipStatus, setMembershipStatus] = useState<string | null>(member.membership_status);
  const [planName, setPlanName] = useState<string | null>(member.plan_name);
  const [endsAt, setEndsAt] = useState<string | null>(member.membership_ends_at);
  const [plans, setPlans] = useState<BackendPlan[] | null>(null);
  const [plansError, setPlansError] = useState("");
  const [selectedPlan, setSelectedPlan] = useState("");
  const [autoRenew, setAutoRenew] = useState(member.auto_renew ?? false);
  const [paymentMethod, setPaymentMethod] = useState<"cash" | "card" | "transfer">("cash");
  const [paymentNote, setPaymentNote] = useState("");
  const paymentKeyRef = useRef<string | null>(null);
  const paymentInFlightRef = useRef(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<"data" | "payment" | "plan" | "freeze" | "resume" | "cancel" | null>(null);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    let active = true;
    fetch("/api/admin/plans", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("plans");
        return (await response.json()) as BackendPlan[];
      })
      .then((items) => { if (active) setPlans(items); })
      .catch(() => { if (active) setPlansError("No se pudieron cargar los planes."); });
    return () => { active = false; };
  }, []);

  const applyMembership = (state: BackendMembershipState) => {
    setMembershipStatus(state.status);
    setPlanName(state.plan_name);
    setEndsAt(state.ends_at);
    setAutoRenew(state.auto_renew);
  };

  const submitData = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!firstName.trim() || !lastName.trim()) {
      setError("El nombre y los apellidos son obligatorios.");
      return;
    }
    if (!email.trim() && !phone.trim()) {
      setError("Indica un correo o un teléfono de contacto.");
      return;
    }
    setBusy("data");
    setError("");
    setFeedback("");
    try {
      const response = await fetch(`/api/admin/members/${encodeURIComponent(member.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          email: email.trim() || null,
          phone: phone.trim() || null,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        setError(payload.detail || "No se pudieron guardar los datos.");
        return;
      }
      const updated = await response.json() as { first_name: string; last_name: string; email: string | null; phone: string | null };
      setFirstName(updated.first_name);
      setLastName(updated.last_name);
      setEmail(updated.email ?? "");
      setPhone(updated.phone ?? "");
      setFeedback("Datos actualizados.");
      onChanged("Datos del socio actualizados.");
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(null);
    }
  };

  const collectPayment = async () => {
    if (paymentInFlightRef.current) return;
    paymentInFlightRef.current = true;
    setBusy("payment");
    setError("");
    setFeedback("");
    // Keep the same key across retries of a network failure. If the backend did
    // commit the payment but the response was lost, the retry returns the
    // original payment instead of charging twice. Editing the form clears it.
    const idempotencyKey = paymentKeyRef.current ?? globalThis.crypto.randomUUID();
    paymentKeyRef.current = idempotencyKey;
    try {
      const response = await fetch(`/api/admin/members/${encodeURIComponent(member.id)}/membership/payments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          plan_id: selectedPlan || null,
          payment_method: paymentMethod,
          idempotency_key: idempotencyKey,
          note: paymentNote.trim() || null,
          auto_renew: autoRenew,
        }),
      });
      if (!response.ok) {
        paymentKeyRef.current = null;
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        setError(payload.detail || "No se pudo registrar el cobro.");
        return;
      }
      const result = await response.json() as BackendMembershipPayment;
      paymentKeyRef.current = null;
      setMembershipStatus(result.membership_status);
      setPlanName(result.plan_name);
      setEndsAt(result.period_ends_at);
      setAutoRenew(result.auto_renew);
      setSelectedPlan("");
      setPaymentNote("");
      setFeedback(`${result.renewed ? "Renovación registrada" : "Membresía activada"}: ${formatMoney(result.amount_cents)} · vigente hasta ${formatRenewalDate(result.period_ends_at)}.`);
      onChanged(`${result.renewed ? "Renovación" : "Membresía"} de ${member.first_name} ${member.last_name} cobrada por ${formatMoney(result.amount_cents)} (${paymentMethodLabels[result.method] ?? result.method}).`);
    } catch {
      setError("No se pudo conectar con el backend. Reintenta con los mismos datos para no duplicar el cobro.");
    } finally {
      paymentInFlightRef.current = false;
      setBusy(null);
    }
  };

  const runMembershipAction = async (path: string, kind: "plan" | "freeze" | "resume" | "cancel", body?: unknown) => {
    setBusy(kind);
    setError("");
    setFeedback("");
    try {
      const response = await fetch(`/api/admin/members/${encodeURIComponent(member.id)}/membership${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        setError(payload.detail || "No se pudo completar la acción.");
        return;
      }
      const state = await response.json() as BackendMembershipState;
      applyMembership(state);
      if (kind === "plan") {
        setSelectedPlan("");
        setFeedback(`Plan asignado: ${state.plan_name}. Membresía activa sin cobro.`);
        onChanged(`Plan ${state.plan_name} asignado a ${member.first_name} ${member.last_name} (sin cobro).`);
      } else if (kind === "freeze") {
        setFeedback("Membresía congelada.");
        onChanged(`Membresía de ${member.first_name} congelada.`);
      } else if (kind === "resume") {
        setFeedback("Membresía reanudada.");
        onChanged(`Membresía de ${member.first_name} reanudada.`);
      } else {
        setReason("");
        setFeedback("Membresía cancelada.");
        onChanged(`Membresía de ${member.first_name} cancelada.`);
      }
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(null);
    }
  };

  const isNonTerminal =
    membershipStatus === "active" ||
    membershipStatus === "frozen" ||
    membershipStatus === "suspended" ||
    membershipStatus === "pending_payment";
  const canFreeze = membershipStatus === "active";
  const canResume = membershipStatus === "frozen";
  const displayStatus = memberDisplayStatus({ ...member, membership_status: membershipStatus, membership_ends_at: endsAt });
  const currentPlan = (plans ?? []).find((option) => selectedPlan ? option.id === selectedPlan : option.name === planName);
  const paymentAllowed =
    membershipStatus === null ||
    membershipStatus === "active" ||
    membershipStatus === "expired" ||
    membershipStatus === "cancelled";
  const canCollect = paymentAllowed && Boolean(currentPlan) && (currentPlan?.price_cents ?? 0) > 0;

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal member-modal" role="dialog" aria-modal="true" aria-labelledby="member-modal-title">
        <div className="modal-header"><span className="modal-icon"><Users size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">FICHA DE SOCIO</p><h2 id="member-modal-title">{firstName} {lastName}</h2><p className="modal-subtitle">{email || phone || "Sin contacto"}</p>

        <form className="modal-section" onSubmit={submitData}>
          <p className="modal-section-title">Datos de contacto</p>
          <div className="form-row">
            <label className="form-field"><span>Nombre</span><input value={firstName} onChange={(event) => setFirstName(event.target.value)} /></label>
            <label className="form-field"><span>Apellidos</span><input value={lastName} onChange={(event) => setLastName(event.target.value)} /></label>
          </div>
          <label className="form-field"><span>Correo electrónico</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="socio@correo.com" /></label>
          <label className="form-field"><span>Teléfono</span><input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="55 0000 0000" /></label>
          <div className="modal-actions"><button type="submit" className="button button-secondary" disabled={busy !== null}>{busy === "data" ? "Guardando…" : "Guardar datos"}</button></div>
        </form>

        <div className="modal-section">
          <div className="modal-section-title modal-section-status"><span>Membresía</span><StatusBadge state={displayStatus} /></div>
          <p className="member-modal-meta">{planName ? `Plan ${planName}` : "Sin plan asignado"}{endsAt ? ` · Renueva ${formatRenewalDate(endsAt)}` : ""}</p>
          <label className="form-field"><span>Plan del club</span><select value={selectedPlan} onChange={(event) => { paymentKeyRef.current = null; setSelectedPlan(event.target.value); }} disabled={plans === null}><option value="">{plans === null ? "Cargando planes…" : isNonTerminal ? `Plan actual: ${planName ?? "—"}` : "Selecciona un plan"}</option>{(plans ?? []).map((option) => <option key={option.id} value={option.id}>{option.name} · {option.duration_days} días</option>)}</select></label>
          {plansError && <p className="member-modal-error">{plansError}</p>}
          <label className="form-check"><input type="checkbox" checked={autoRenew} onChange={(event) => { paymentKeyRef.current = null; setAutoRenew(event.target.checked); }} /><span>Renovación automática (se guarda con la membresía).</span></label>
          {paymentAllowed ? (
            <>
              <div className="form-row">
                <label className="form-field"><span>Forma de pago</span><select value={paymentMethod} onChange={(event) => { paymentKeyRef.current = null; setPaymentMethod(event.target.value as "cash" | "card" | "transfer"); }}><option value="cash">Efectivo</option><option value="card">Tarjeta (declarada)</option><option value="transfer">Transferencia</option></select></label>
                <label className="form-field"><span>Importe</span><input value={currentPlan ? formatMoney(currentPlan.price_cents) : "—"} readOnly /></label>
              </div>
              <label className="form-field"><span>Nota del cobro (opcional)</span><input value={paymentNote} onChange={(event) => { paymentKeyRef.current = null; setPaymentNote(event.target.value); }} placeholder="Ej. renovación mensual" maxLength={200} /></label>
              <div className="modal-actions"><button type="button" className="button button-primary" disabled={busy !== null || !canCollect} onClick={() => { if (currentPlan && window.confirm(`¿Registrar ${isNonTerminal ? "la renovación" : "el cobro"} de ${formatMoney(currentPlan.price_cents)} con ${paymentMethodLabels[paymentMethod] ?? paymentMethod}?`)) void collectPayment(); }}>{busy === "payment" ? "Registrando cobro…" : isNonTerminal ? "Cobrar renovación" : "Cobrar y activar"}</button></div>
            </>
          ) : <p className="member-modal-meta">Reanuda o cancela el estado actual antes de registrar un cobro.</p>}
          <div className="modal-actions"><button type="button" className="button button-secondary" disabled={busy !== null || !selectedPlan} onClick={() => { if (window.confirm("La activación sin cobro no registra ningún pago. ¿Continuar?")) void runMembershipAction("", "plan", { plan_id: selectedPlan, auto_renew: autoRenew }); }}>{busy === "plan" ? "Guardando…" : isNonTerminal ? "Cambiar plan sin cobro" : "Activar sin cobro"}</button></div>
          {(isNonTerminal) && <label className="form-field"><span>Motivo de cancelación</span><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Ej. cambio de club" /></label>}
          <div className="member-modal-actions">
            {canFreeze && <button type="button" className="button button-secondary" disabled={busy !== null} onClick={() => runMembershipAction("/freeze", "freeze")}>{busy === "freeze" ? "Congelando…" : "Congelar"}</button>}
            {canResume && <button type="button" className="button button-secondary" disabled={busy !== null} onClick={() => runMembershipAction("/resume", "resume")}>{busy === "resume" ? "Reanudando…" : "Reanudar"}</button>}
            {isNonTerminal && <button type="button" className="button button-danger" disabled={busy !== null} onClick={() => runMembershipAction("/cancel", "cancel", { reason })}>{busy === "cancel" ? "Cancelando…" : "Cancelar membresía"}</button>}
          </div>
        </div>

        {error && <div className="login-error" role="alert">{error}</div>}
        {feedback && <div className="modal-feedback" role="status">{feedback}</div>}
        <div className="modal-note"><ShieldCheck size={16} /><span>El cobro manual queda ligado al <strong>turno de caja abierto</strong>; solo el efectivo entra al arqueo. La activación sin cobro es una cortesía auditada y no registra ningún pago.</span></div>
      </section>
    </div>
  );
}

function NewEmployeeModal({ canCreateAccount, roles, onClose, onCreated }: { canCreateAccount: boolean; roles: BackendRole[]; onClose: () => void; onCreated: (message: string) => void }) {
  const [employeeNumber, setEmployeeNumber] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [createAccount, setCreateAccount] = useState(false);
  const [accountEmail, setAccountEmail] = useState("");
  const [password, setPassword] = useState("");
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const toggleRole = (code: string) => {
    setSelectedRoles((current) => (current.includes(code) ? current.filter((value) => value !== code) : [...current, code]));
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!employeeNumber.trim() || !firstName.trim() || !lastName.trim() || !jobTitle.trim()) {
      setError("Número de empleado, nombre, apellidos y puesto son obligatorios.");
      return;
    }
    const accountEmailValue = (accountEmail.trim() || email.trim()).toLowerCase();
    if (createAccount && canCreateAccount) {
      if (!accountEmailValue) {
        setError("Indica el correo de la cuenta de acceso.");
        return;
      }
      if (password.length < 12) {
        setError("La contraseña debe tener al menos 12 caracteres.");
        return;
      }
      if (selectedRoles.length === 0) {
        setError("Selecciona al menos un rol para la cuenta.");
        return;
      }
    }
    setBusy(true);
    setError("");
    const fullName = `${firstName.trim()} ${lastName.trim()}`;

    let employeeId: string;
    try {
      const response = await fetch("/api/admin/staff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          employee_number: employeeNumber.trim(),
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          job_title: jobTitle.trim(),
          email: email.trim() || null,
          phone: phone.trim() || null,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        setError(payload.detail || "No se pudo crear el colaborador.");
        setBusy(false);
        return;
      }
      employeeId = ((await response.json()) as { id: string }).id;
    } catch {
      setError("No se pudo conectar con el backend.");
      setBusy(false);
      return;
    }

    if (createAccount && canCreateAccount) {
      try {
        const response = await fetch("/api/admin/users", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: accountEmailValue,
            password,
            employee_id: employeeId,
            role_codes: selectedRoles,
          }),
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({})) as { detail?: string };
          onCreated(`Colaborador ${fullName} creado, pero la cuenta falló: ${payload.detail || "error"}.`);
          onClose();
          return;
        }
      } catch {
        onCreated(`Colaborador ${fullName} creado, pero no se pudo crear la cuenta (sin conexión).`);
        onClose();
        return;
      }
    }

    onCreated(createAccount && canCreateAccount ? `Colaborador ${fullName} y su cuenta de acceso creados.` : `Colaborador ${fullName} creado.`);
    onClose();
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal member-modal" role="dialog" aria-modal="true" aria-labelledby="new-employee-title">
        <div className="modal-header"><span className="modal-icon"><Users size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">ALTA DE PERSONAL · EXPEDIENTE Y CUENTA</p><h2 id="new-employee-title">Nuevo colaborador</h2><p className="modal-subtitle">Registra el expediente del colaborador y, si corresponde, su cuenta de acceso con roles iniciales.</p>
        <form onSubmit={submit}>
          <p className="modal-section-title">Expediente</p>
          <div className="form-row">
            <label className="form-field"><span>Nombre</span><input value={firstName} onChange={(event) => setFirstName(event.target.value)} placeholder="Nombre" autoFocus autoComplete="given-name" /></label>
            <label className="form-field"><span>Apellidos</span><input value={lastName} onChange={(event) => setLastName(event.target.value)} placeholder="Apellidos" autoComplete="family-name" /></label>
          </div>
          <div className="form-row">
            <label className="form-field"><span>Número de empleado</span><input value={employeeNumber} onChange={(event) => setEmployeeNumber(event.target.value)} placeholder="EMP-001" /></label>
            <label className="form-field"><span>Puesto</span><input value={jobTitle} onChange={(event) => setJobTitle(event.target.value)} placeholder="Recepción" /></label>
          </div>
          <label className="form-field"><span>Correo de contacto</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="nombre@correo.com" autoComplete="email" /></label>
          <label className="form-field"><span>Teléfono</span><input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="55 0000 0000" autoComplete="tel" /></label>

          {canCreateAccount && <>
            <label className="form-check"><input type="checkbox" checked={createAccount} onChange={(event) => { const checked = event.target.checked; setCreateAccount(checked); if (checked && !accountEmail) setAccountEmail(email); }} /><span>Crear cuenta de acceso para este colaborador.</span></label>
            {createAccount && <>
              <label className="form-field"><span>Correo de la cuenta</span><input type="email" value={accountEmail} onChange={(event) => setAccountEmail(event.target.value)} placeholder="nombre@correo.com" autoComplete="off" /></label>
              <label className="form-field"><span>Contraseña (mínimo 12 caracteres)</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="••••••••••••" autoComplete="new-password" /></label>
              <p className="modal-section-title">Roles iniciales</p>
              {roles.length === 0 ? <p className="role-chip-empty">No hay roles disponibles.</p> : <div className="role-picker">{roles.map((role) => <label key={role.code} className="form-check"><input type="checkbox" checked={selectedRoles.includes(role.code)} onChange={() => toggleRole(role.code)} /><span>{role.name}</span></label>)}</div>}
            </>}
          </>}

          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-note"><ShieldCheck size={16} /><span>La contraseña se guarda con Argon2 y nunca se muestra. La cuenta se crea con los roles elegidos y queda auditada con el responsable.</span></div>
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Creando…" : "Crear colaborador"}</button></div>
        </form>
      </section>
    </div>
  );
}

function ScheduleShiftModal({ employees, onClose, onCreated }: { employees: BackendEmployee[]; onClose: () => void; onCreated: (message: string) => void }) {
  const now = new Date();
  const defaultDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const [employeeId, setEmployeeId] = useState(employees[0]?.id ?? "");
  const [date, setDate] = useState(defaultDate);
  const [startTime, setStartTime] = useState("07:00");
  const [endTime, setEndTime] = useState("15:00");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!employeeId) {
      setError("Selecciona un colaborador.");
      return;
    }
    if (!date || !startTime || !endTime) {
      setError("Indica fecha, hora de inicio y hora de fin.");
      return;
    }
    const startsAt = new Date(`${date}T${startTime}`);
    const endsAt = new Date(`${date}T${endTime}`);
    if (Number.isNaN(startsAt.getTime()) || Number.isNaN(endsAt.getTime())) {
      setError("La fecha u hora no son válidas.");
      return;
    }
    if (endsAt.getTime() <= startsAt.getTime()) {
      setError("La hora de fin debe ser posterior a la de inicio.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/staff/${encodeURIComponent(employeeId)}/shifts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ starts_at: startsAt.toISOString(), ends_at: endsAt.toISOString() }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        setError(payload.detail || "No se pudo programar el turno.");
        setBusy(false);
        return;
      }
      onCreated("Turno programado.");
      onClose();
    } catch {
      setError("No se pudo conectar con el backend.");
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal member-modal" role="dialog" aria-modal="true" aria-labelledby="new-shift-title">
        <div className="modal-header"><span className="modal-icon"><Users size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">TURNOS DEL PERSONAL</p><h2 id="new-shift-title">Programar turno</h2><p className="modal-subtitle">Agenda un turno para un colaborador. El backend rechaza traslapes con otro turno del mismo colaborador.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Colaborador</span><select value={employeeId} onChange={(event) => setEmployeeId(event.target.value)} disabled={employees.length === 0}><option value="">{employees.length === 0 ? "Sin colaboradores" : "Selecciona un colaborador"}</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.first_name} {employee.last_name} · {employee.employee_number}</option>)}</select></label>
          <label className="form-field"><span>Fecha</span><input type="date" value={date} onChange={(event) => setDate(event.target.value)} /></label>
          <div className="form-row">
            <label className="form-field"><span>Hora de inicio</span><input type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} /></label>
            <label className="form-field"><span>Hora de fin</span><input type="time" value={endTime} onChange={(event) => setEndTime(event.target.value)} /></label>
          </div>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-note"><ShieldCheck size={16} /><span>El turno queda registrado con el responsable y se muestra en la lista de turnos programados.</span></div>
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy || employees.length === 0}><Check size={16} />{busy ? "Guardando…" : "Programar turno"}</button></div>
        </form>
      </section>
    </div>
  );
}

function toDateTimeLocal(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function ManualAttendanceModal({ shift, employee, onClose, onCreated }: { shift: BackendShift; employee: BackendEmployee | null; onClose: () => void; onCreated: (message: string) => void }) {
  const eventType = shift.attendance ? "check_out" : "check_in";
  const name = employee ? `${employee.first_name} ${employee.last_name}` : "el colaborador";
  const [occurredAt, setOccurredAt] = useState(() => toDateTimeLocal(eventType === "check_in" ? shift.starts_at : shift.ends_at));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const occurred = new Date(occurredAt);
    if (Number.isNaN(occurred.getTime())) {
      setError("Indica la fecha y hora de la marca.");
      return;
    }
    if (reason.trim().length < 3) {
      setError("Escribe el motivo de la corrección.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/staff/attendance", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shift_id: shift.id,
          request_id: crypto.randomUUID(),
          event_type: eventType,
          occurred_at: occurred.toISOString(),
          reason: reason.trim(),
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        setError(response.status === 409 ? "Ese turno ya tiene esa marca registrada." : payload.detail || "No se pudo registrar la marca.");
        setBusy(false);
        return;
      }
      onCreated(eventType === "check_in" ? `Entrada registrada manualmente para ${name}.` : `Salida registrada manualmente para ${name}.`);
      onClose();
    } catch {
      setError("No se pudo conectar con el backend.");
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal member-modal" role="dialog" aria-modal="true" aria-labelledby="manual-attendance-title">
        <div className="modal-header"><span className="modal-icon"><Users size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">ASISTENCIA DEL PERSONAL</p><h2 id="manual-attendance-title">{eventType === "check_in" ? "Registrar entrada faltante" : "Registrar salida faltante"}</h2>
        <p className="modal-subtitle">{name} · {shiftDayLabel(shift.starts_at)} de {shiftClock(shift.starts_at)} a {shiftClock(shift.ends_at)}. Solo se registran marcas que faltan: si el colaborador ya marcó, el backend rechaza la corrección.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Fecha y hora de la marca</span><input type="datetime-local" value={occurredAt} onChange={(event) => setOccurredAt(event.target.value)} /></label>
          <label className="form-field"><span>Motivo</span><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="No pudo marcar, olvidó la salida…" maxLength={500} /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-note"><ShieldCheck size={16} /><span>La marca queda con tu cuenta como responsable y el motivo en la bitácora del turno.</span></div>
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : "Registrar marca"}</button></div>
        </form>
      </section>
    </div>
  );
}

function AttendanceCorrectionModal({ shift, employee, onClose, onSaved }: { shift: BackendShift; employee: BackendEmployee | null; onClose: () => void; onSaved: (message: string) => void }) {
  const attendance = shift.attendance;
  const name = employee ? `${employee.first_name} ${employee.last_name}` : "el colaborador";
  const [checkInAt, setCheckInAt] = useState(() => toDateTimeLocal(shift.attendance?.check_in_at ?? shift.starts_at));
  const [checkOutAt, setCheckOutAt] = useState(() => shift.attendance?.check_out_at ? toDateTimeLocal(shift.attendance.check_out_at) : "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!attendance) return;
    if (reason.trim().length < 3) {
      setError("Escribe el motivo de la corrección.");
      return;
    }
    const entry = new Date(checkInAt);
    if (Number.isNaN(entry.getTime())) {
      setError("Indica la fecha y hora de la entrada.");
      return;
    }
    const originalEntry = new Date(attendance.check_in_at);
    const originalExit = attendance.check_out_at ? new Date(attendance.check_out_at) : null;
    const changes: { eventType: "check_in" | "check_out"; value: Date }[] = [];
    if (entry.getTime() !== originalEntry.getTime()) changes.push({ eventType: "check_in", value: entry });
    let exit: Date | null = originalExit;
    if (originalExit) {
      const parsedExit = new Date(checkOutAt);
      if (Number.isNaN(parsedExit.getTime())) {
        setError("Indica la fecha y hora de la salida.");
        return;
      }
      exit = parsedExit;
      if (parsedExit.getTime() !== originalExit.getTime()) changes.push({ eventType: "check_out", value: parsedExit });
    }
    if (changes.length === 0) {
      setError("Cambia al menos una fecha u hora.");
      return;
    }
    if (exit && entry.getTime() > exit.getTime()) {
      setError("La entrada no puede quedar después de la salida.");
      return;
    }
    // Each correction is validated against the stored marks, so the mark that
    // still fits the current value is sent first.
    const ordered = [...changes];
    if (ordered.length === 2 && originalExit) {
      const entryFirst = entry.getTime() <= originalExit.getTime();
      ordered.sort((item) => (item.eventType === (entryFirst ? "check_in" : "check_out") ? -1 : 1));
    }

    setBusy(true);
    setError("");
    let applied = 0;
    try {
      for (const change of ordered) {
        const response = await fetch(`/api/admin/staff/attendance/${attendance.id}/corrections`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            request_id: crypto.randomUUID(),
            event_type: change.eventType,
            occurred_at: change.value.toISOString(),
            reason: reason.trim(),
          }),
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({})) as { detail?: string };
          if (applied > 0) {
            onSaved("Se corrigió una marca; la otra no se pudo guardar. Revisa la tabla.");
            onClose();
            return;
          }
          setError(response.status === 409
            ? "Ese turno cambió mientras corregías. Vuelve a abrir la corrección."
            : payload.detail || "No se pudo corregir la marca.");
          setBusy(false);
          return;
        }
        applied += 1;
      }
      onSaved(applied === 1 ? `Marca de ${name} corregida.` : `Entrada y salida de ${name} corregidas.`);
      onClose();
    } catch {
      if (applied > 0) {
        onSaved("Se corrigió una marca; la otra no se pudo guardar. Revisa la tabla.");
        onClose();
        return;
      }
      setError("No se pudo conectar con el backend.");
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal member-modal" role="dialog" aria-modal="true" aria-labelledby="attendance-correction-title">
        <div className="modal-header"><span className="modal-icon"><PenLine size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">ASISTENCIA DEL PERSONAL</p><h2 id="attendance-correction-title">Corregir marcas</h2>
        <p className="modal-subtitle">{name} · {shiftDayLabel(shift.starts_at)} de {shiftClock(shift.starts_at)} a {shiftClock(shift.ends_at)}. La marca anterior y el motivo quedan en la bitácora del turno.</p>
        <form onSubmit={submit}>
          <label className="form-field"><span>Entrada</span><input type="datetime-local" value={checkInAt} onChange={(event) => setCheckInAt(event.target.value)} /></label>
          {attendance?.check_out_at
            ? <label className="form-field"><span>Salida</span><input type="datetime-local" value={checkOutAt} onChange={(event) => setCheckOutAt(event.target.value)} /></label>
            : <p className="table-hint">La salida aún no existe: regístrala desde la tabla antes de corregirla.</p>}
          <label className="form-field"><span>Motivo</span><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="La hora marcada no era la correcta…" maxLength={500} /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-note"><ShieldCheck size={16} /><span>El backend conserva la marca original, registra tu cuenta como responsable y rechaza una salida anterior a la entrada.</span></div>
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : "Corregir marca"}</button></div>
        </form>
      </section>
    </div>
  );
}

const ATTENDANCE_EVENT_LABELS: Record<string, string> = {
  check_in: "Entrada",
  check_out: "Salida",
  check_in_correction: "Entrada corregida",
  check_out_correction: "Salida corregida",
  check_out_voided: "Salida anulada",
  attendance_voided: "Asistencia anulada",
};

const ATTENDANCE_SOURCE_LABELS: Record<string, string> = {
  staff_app: "app del personal",
  manual: "recepción",
  correction: "corrección",
  access_reader: "lector de acceso",
};

const ATTENDANCE_REQUEST_STATUS_LABELS: Record<AttendanceRequestStatus, string> = {
  pending: "Pendiente",
  approved: "Aprobada",
  rejected: "Rechazada",
};

function attendanceMarkLabel(mark: "check_in" | "check_out"): string {
  return mark === "check_in" ? "Entrada" : "Salida";
}

function AttendanceLogModal({ shift, attendance, employee, onClose }: { shift: BackendShift; attendance: BackendAttendance; employee: BackendEmployee | null; onClose: () => void }) {
  const name = employee ? `${employee.first_name} ${employee.last_name}` : "el colaborador";
  const [entries, setEntries] = useState<AttendanceLogEntry[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const response = await fetch(`/api/admin/staff/attendance/${attendance.id}/events`, { cache: "no-store" });
        if (!response.ok) {
          if (active) setError(response.status === 404 ? "La asistencia ya no existe." : "No se pudo consultar la bitácora.");
          return;
        }
        const payload = await response.json() as { items: AttendanceLogEntry[] };
        if (active) setEntries(payload.items);
      } catch {
        if (active) setError("No se pudo conectar con el backend.");
      }
    })();
    return () => { active = false; };
  }, [attendance.id]);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal member-modal" role="dialog" aria-modal="true" aria-labelledby="attendance-log-title">
        <div className="modal-header"><span className="modal-icon"><ClipboardList size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">ASISTENCIA DEL PERSONAL</p><h2 id="attendance-log-title">Bitácora del turno</h2>
        <p className="modal-subtitle">{name} · {shiftDayLabel(shift.starts_at)} de {shiftClock(shift.starts_at)} a {shiftClock(shift.ends_at)}. Cada marca, corrección y anulación queda registrada con su responsable y motivo; la más reciente aparece al final.</p>
        {error ? <div className="login-error" role="alert">{error}</div>
          : entries === null ? <p className="panel-hint">Cargando la bitácora…</p>
          : entries.length === 0 ? <p className="panel-hint">Esta asistencia todavía no tiene eventos.</p>
          : <ol className="staff-log-list">{entries.map((entry) => <li key={entry.id} className="staff-log-item"><div className="staff-log-head"><strong>{ATTENDANCE_EVENT_LABELS[entry.event_type] ?? entry.event_type}</strong><span className="time-cell">{formatSessionTime(entry.occurred_at)}</span></div><div className="staff-log-meta">{entry.actor_name ?? entry.actor_email} · {ATTENDANCE_SOURCE_LABELS[entry.source] ?? entry.source}</div>{entry.reason ? <p className="staff-log-reason">{entry.reason}</p> : null}</li>)}</ol>}
        <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cerrar</button></div>
      </section>
    </div>
  );
}

function AttendanceVoidModal({ shift, attendance, employee, onClose, onSaved }: { shift: BackendShift; attendance: BackendAttendance; employee: BackendEmployee | null; onClose: () => void; onSaved: (message: string) => void }) {
  const name = employee ? `${employee.first_name} ${employee.last_name}` : "el colaborador";
  const [mark, setMark] = useState<"check_in" | "check_out">(attendance.check_out_at ? "check_out" : "check_in");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (reason.trim().length < 3) {
      setError("Escribe el motivo de la anulación.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/staff/attendance/${attendance.id}/voids`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: crypto.randomUUID(), mark, reason: reason.trim() }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        setError(response.status === 409
          ? "Ese turno cambió mientras anulabas la marca. Vuelve a abrir la anulación."
          : payload.detail || "No se pudo anular la marca.");
        setBusy(false);
        return;
      }
      onSaved(mark === "check_out" ? `Salida de ${name} anulada; la entrada se conserva.` : `Asistencia de ${name} anulada; el turno queda libre para marcarse de nuevo.`);
      onClose();
    } catch {
      setError("No se pudo conectar con el backend.");
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal member-modal" role="dialog" aria-modal="true" aria-labelledby="attendance-void-title">
        <div className="modal-header"><span className="modal-icon"><Trash2 size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">ASISTENCIA DEL PERSONAL</p><h2 id="attendance-void-title">Anular una marca</h2>
        <p className="modal-subtitle">{name} · {shiftDayLabel(shift.starts_at)} de {shiftClock(shift.starts_at)} a {shiftClock(shift.ends_at)}. Anular no borra la marca: la conserva en la bitácora junto con el motivo y tu cuenta como responsable.</p>
        <form onSubmit={submit}>
          <fieldset className="staff-void-marks"><legend>¿Qué marca se anula?</legend>
            <label><input type="radio" name="void-mark" value="check_in" checked={mark === "check_in"} disabled={busy} onChange={() => setMark("check_in")} />Entrada · {shiftClock(attendance.check_in_at)}</label>
            <label><input type="radio" name="void-mark" value="check_out" checked={mark === "check_out"} disabled={busy || !attendance.check_out_at} onChange={() => setMark("check_out")} />{attendance.check_out_at ? `Salida · ${shiftClock(attendance.check_out_at)}` : "Salida · sin marca"}</label>
          </fieldset>
          <p className="table-hint">{mark === "check_out" ? "La entrada se conserva y el colaborador puede volver a marcar su salida." : "La asistencia completa queda anulada y el turno vuelve a estar libre para marcarse."}</p>
          <label className="form-field"><span>Motivo</span><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="La marca se registró en el turno equivocado…" maxLength={500} /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Trash2 size={16} />{busy ? "Anulando…" : "Anular marca"}</button></div>
        </form>
      </section>
    </div>
  );
}

function AttendanceRequestModal({ shift, attendance, onClose, onCreated }: { shift: BackendShift; attendance: BackendAttendance; onClose: () => void; onCreated: (message: string) => void }) {
  const [mark, setMark] = useState<"check_in" | "check_out">("check_in");
  const [action, setAction] = useState<"correct" | "void">("correct");
  const [proposedAt, setProposedAt] = useState(() => toDateTimeLocal(attendance.check_in_at));
  const [justification, setJustification] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const switchMark = (next: "check_in" | "check_out") => {
    setMark(next);
    setProposedAt(toDateTimeLocal(next === "check_in" ? attendance.check_in_at : attendance.check_out_at ?? attendance.check_in_at));
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (justification.trim().length < 3) {
      setError("Explica por qué la marca debe cambiar.");
      return;
    }
    let proposed: string | null = null;
    if (action === "correct") {
      const parsed = new Date(proposedAt);
      if (Number.isNaN(parsed.getTime())) {
        setError("Indica la hora correcta de la marca.");
        return;
      }
      proposed = parsed.toISOString();
    }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/staff/attendance/${attendance.id}/requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mark, action, proposed_at: proposed, justification: justification.trim() }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        setError(response.status === 409
          ? "Ya hay una solicitud pendiente para esa marca o el turno cambió. Revisa «Mis solicitudes»."
          : payload.detail || "No se pudo enviar la solicitud.");
        setBusy(false);
        return;
      }
      onCreated(action === "void" ? `Pediste anular la ${attendanceMarkLabel(mark).toLowerCase()}; un supervisor la revisará.` : `Pediste corregir la ${attendanceMarkLabel(mark).toLowerCase()}; un supervisor la revisará.`);
      onClose();
    } catch {
      setError("No se pudo conectar con el backend.");
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal member-modal" role="dialog" aria-modal="true" aria-labelledby="attendance-request-title">
        <div className="modal-header"><span className="modal-icon"><PenLine size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">MI JORNADA</p><h2 id="attendance-request-title">Solicitar cambio de marca</h2>
        <p className="modal-subtitle">{shiftDayLabel(shift.starts_at)} de {shiftClock(shift.starts_at)} a {shiftClock(shift.ends_at)}. Tu solicitud no cambia la marca: un supervisor la revisa y te avisa cuando decide.</p>
        <form onSubmit={submit}>
          <fieldset className="staff-void-marks"><legend>¿Qué marca cambia?</legend>
            <label><input type="radio" name="request-mark" value="check_in" checked={mark === "check_in"} disabled={busy} onChange={() => switchMark("check_in")} />Entrada · {shiftClock(attendance.check_in_at)}</label>
            <label><input type="radio" name="request-mark" value="check_out" checked={mark === "check_out"} disabled={busy || !attendance.check_out_at} onChange={() => switchMark("check_out")} />{attendance.check_out_at ? `Salida · ${shiftClock(attendance.check_out_at)}` : "Salida · sin marca"}</label>
          </fieldset>
          <fieldset className="staff-void-marks"><legend>¿Qué quieres que haga el supervisor?</legend>
            <label><input type="radio" name="request-action" value="correct" checked={action === "correct"} disabled={busy} onChange={() => setAction("correct")} />Corregir la hora</label>
            <label><input type="radio" name="request-action" value="void" checked={action === "void"} disabled={busy} onChange={() => setAction("void")} />Anular la marca</label>
          </fieldset>
          {action === "correct" ? <label className="form-field"><span>Hora correcta</span><input type="datetime-local" value={proposedAt} onChange={(event) => setProposedAt(event.target.value)} /></label> : <p className="table-hint">La marca anulada deja de contar en el turno, pero se conserva en la bitácora con el motivo.</p>}
          <label className="form-field"><span>Justificación</span><input value={justification} onChange={(event) => setJustification(event.target.value)} placeholder="Entré antes de la hora marcada, marqué en el turno equivocado…" maxLength={500} /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-note"><ShieldCheck size={16} /><span>La solicitud queda con tu cuenta y el motivo. El supervisor no puede aprobar su propia solicitud.</span></div>
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Enviando…" : "Enviar solicitud"}</button></div>
        </form>
      </section>
    </div>
  );
}

function AttendanceRequestDecisionModal({ request, shift, onClose, onDecided }: { request: AttendanceRequest; shift: BackendShift | null; onClose: () => void; onDecided: (message: string) => void }) {
  const [decision, setDecision] = useState<"approved" | "rejected">("approved");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (decision === "rejected" && note.trim().length < 3) {
      setError("Explica por qué rechazas la solicitud.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/staff/attendance/requests/${request.id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, note: note.trim() || null }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as { detail?: string };
        setError(response.status === 409
          ? "La solicitud cambió mientras la revisabas. Cierra el panel y vuelve a abrir la cola."
          : response.status === 403
            ? "No puedes decidir tu propia solicitud."
            : payload.detail || "No se pudo guardar la decisión.");
        setBusy(false);
        return;
      }
      onDecided(decision === "approved"
        ? `Solicitud de ${request.employee_name ?? "colaborador"} aprobada; el cambio ya aplica.`
        : `Solicitud de ${request.employee_name ?? "colaborador"} rechazada; se le avisó el motivo.`);
      onClose();
    } catch {
      setError("No se pudo conectar con el backend.");
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal member-modal" role="dialog" aria-modal="true" aria-labelledby="attendance-decision-title">
        <div className="modal-header"><span className="modal-icon"><ClipboardList size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">SOLICITUDES DEL EQUIPO</p><h2 id="attendance-decision-title">Revisar solicitud</h2>
        <p className="modal-subtitle">{request.employee_name ?? "Colaborador"}{shift ? ` · ${shiftDayLabel(shift.starts_at)} de ${shiftClock(shift.starts_at)} a ${shiftClock(shift.ends_at)}` : ""}. Aprobar aplica el cambio con tu cuenta como responsable; rechazar avisa el motivo al colaborador.</p>
        <div className="staff-request-summary">
          <div><span>Marca</span><strong>{attendanceMarkLabel(request.mark)}</strong></div>
          <div><span>Ahora</span><strong>{shiftClock(request.mark === "check_in" ? request.current_check_in_at : request.current_check_out_at)}</strong></div>
          <div><span>Pide</span><strong>{request.action === "void" ? "Anular la marca" : shiftClock(request.proposed_at)}</strong></div>
        </div>
        <p className="staff-log-reason">{request.justification}</p>
        <form onSubmit={submit}>
          <fieldset className="staff-void-marks"><legend>Decisión</legend>
            <label><input type="radio" name="request-decision" value="approved" checked={decision === "approved"} disabled={busy} onChange={() => setDecision("approved")} />Aprobar y aplicar el cambio</label>
            <label><input type="radio" name="request-decision" value="rejected" checked={decision === "rejected"} disabled={busy} onChange={() => setDecision("rejected")} />Rechazar</label>
          </fieldset>
          <label className="form-field"><span>{decision === "rejected" ? "Motivo del rechazo (obligatorio)" : "Nota para el colaborador (opcional)"}</span><input value={note} onChange={(event) => setNote(event.target.value)} placeholder={decision === "rejected" ? "La cámara muestra la hora original…" : "Confirmado con recepción…"} maxLength={300} /></label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}>{busy ? "Guardando…" : decision === "approved" ? <><Check size={16} />Aprobar solicitud</> : <><X size={16} />Rechazar solicitud</>}</button></div>
        </form>
      </section>
    </div>
  );
}

function PolicyHistoryModal({ onClose }: { onClose: () => void }) {
  const [events, setEvents] = useState<StaffingSettingsEvent[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const response = await fetch("/api/admin/staff/settings/events", { cache: "no-store" });
        if (!active) return;
        if (!response.ok) {
          setError("No se pudo consultar el historial de la política.");
          return;
        }
        const payload = await response.json() as { items: StaffingSettingsEvent[] };
        setEvents(payload.items);
      } catch {
        if (active) setError("No se pudo conectar con el backend.");
      }
    })();
    return () => { active = false; };
  }, []);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal member-modal" role="dialog" aria-modal="true" aria-labelledby="policy-history-title">
        <div className="modal-header"><span className="modal-icon"><History size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">POLÍTICA DE ASISTENCIA</p><h2 id="policy-history-title">Historial de tolerancias</h2>
        <p className="modal-subtitle">Cada cambio conserva la cuenta responsable, la fecha y los valores anteriores. Guardar sin cambios no registra nada.</p>
        {error ? <div className="login-error" role="alert">{error}</div>
          : events === null ? <p className="panel-hint">Cargando el historial…</p>
          : events.length === 0 ? <p className="panel-hint">La política conserva sus valores iniciales; todavía no hay cambios registrados.</p>
          : <ol className="staff-log-list">{events.map((entry) => <li key={entry.id} className="staff-log-item"><div className="staff-log-head"><strong>{entry.previous_check_in_early_grace_minutes}/{entry.previous_lateness_tolerance_minutes} → {entry.check_in_early_grace_minutes}/{entry.lateness_tolerance_minutes} min</strong><span className="time-cell">{formatSessionTime(entry.changed_at)}</span></div><div className="staff-log-meta">{entry.actor_name ?? entry.actor_email ?? "Cuenta eliminada"} · apertura / tolerancia</div></li>)}</ol>}
        <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cerrar</button></div>
      </section>
    </div>
  );
}

function formatBankSignedAmount(cents: number): string {
  return `${cents < 0 ? "−" : "+"}${formatMoney(Math.abs(cents))}`;
}

function bankMovementStatus(value: string): BankMovementStatus {
  return value === "reconciled" || value === "difference" || value === "reviewing" ? value : "pending";
}

function bankEventLabel(eventType: string): string {
  const labels: Record<string, string> = {
    imported: "Movimiento importado",
    matched: "Conciliación confirmada",
    unmatched: "Conciliación deshecha",
    flagged: "Movimiento marcado para revisión",
    reopened: "Movimiento reabierto",
  };
  return labels[eventType] ?? eventType;
}

function parseBankCsvLine(line: string, delimiter: string): string[] {
  const cells: string[] = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const character = line[index];
    if (quoted) {
      if (character === '"') {
        if (line[index + 1] === '"') {
          current += '"';
          index += 1;
        } else {
          quoted = false;
        }
      } else {
        current += character;
      }
    } else if (character === '"') {
      quoted = true;
    } else if (character === delimiter) {
      cells.push(current.trim());
      current = "";
    } else {
      current += character;
    }
  }
  cells.push(current.trim());
  return cells;
}

function parseBankAmount(rawValue: string): number | null {
  let raw = rawValue.trim().replace(/\s/g, "");
  if (!raw) return null;
  let negative = false;
  if (/^\(.*\)$/.test(raw)) {
    negative = true;
    raw = raw.slice(1, -1);
  }
  if (/^[−-]/.test(raw)) {
    negative = !negative;
    raw = raw.slice(1);
  } else if (raw.startsWith("+")) {
    raw = raw.slice(1);
  }
  raw = raw.replace(/[^0-9.,]/g, "");
  if (!raw) return null;
  const lastDot = raw.lastIndexOf(".");
  const lastComma = raw.lastIndexOf(",");
  if (lastDot >= 0 && lastComma >= 0) {
    raw = lastDot > lastComma ? raw.replace(/,/g, "") : raw.replace(/\./g, "").replace(",", ".");
  } else if (lastComma >= 0) {
    const decimals = raw.length - lastComma - 1;
    raw = decimals > 0 && decimals <= 2 ? raw.replace(",", ".") : raw.replace(/,/g, "");
  }
  const amount = Number.parseFloat(raw);
  if (!Number.isFinite(amount) || amount <= 0) return null;
  const cents = Math.round(amount * 100);
  if (cents < 1 || cents > 1_000_000_000_000) return null;
  return negative ? -cents : cents;
}

function parseBankDate(rawValue: string): string | null {
  const raw = rawValue.trim();
  const iso = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(raw);
  const latin = /^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/.exec(raw);
  let year: number;
  let month: number;
  let day: number;
  if (iso) {
    year = Number(iso[1]);
    month = Number(iso[2]);
    day = Number(iso[3]);
  } else if (latin) {
    day = Number(latin[1]);
    month = Number(latin[2]);
    year = Number(latin[3]);
  } else {
    return null;
  }
  if (year < 2000 || year > 2100 || month < 1 || month > 12 || day < 1 || day > 31) return null;
  const check = new Date(Date.UTC(year, month - 1, day));
  if (check.getUTCFullYear() !== year || check.getUTCMonth() !== month - 1 || check.getUTCDate() !== day) return null;
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function parseBankCsv(text: string): { rows: BankImportRow[]; errors: string[] } {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (lines.length === 0) return { rows: [], errors: ["Pega o carga un archivo CSV con al menos una fila."] };
  const firstLine = lines[0] ?? "";
  const delimiter = firstLine.includes("\t")
    ? "\t"
    : (firstLine.split(";").length > firstLine.split(",").length ? ";" : ",");
  const rows: BankImportRow[] = [];
  const errors: string[] = [];
  const header = /^(fecha|date|fecha de operaci[oó]n|f\.?\s*operaci[oó]n)$/i;
  lines.forEach((line, index) => {
    const cells = parseBankCsvLine(line, delimiter);
    const first = (cells[0] ?? "").trim();
    if (index === 0 && header.test(first)) return;
    if (cells.length < 2) {
      errors.push(`Línea ${index + 1}: se esperaban al menos fecha e importe.`);
      return;
    }
    const occurredOn = parseBankDate(first);
    if (!occurredOn) {
      errors.push(`Línea ${index + 1}: fecha inválida «${first}». Usa AAAA-MM-DD o DD/MM/AAAA.`);
      return;
    }
    const amount = parseBankAmount(cells[1] ?? "");
    if (amount === null) {
      errors.push(`Línea ${index + 1}: importe inválido «${cells[1] ?? ""}».`);
      return;
    }
    if (rows.length >= 500) {
      errors.push("El lote supera 500 movimientos; divide el archivo.");
      return;
    }
    rows.push({
      occurred_on: occurredOn,
      amount_cents: amount,
      reference: (cells[2] ?? "").slice(0, 120),
      description: (cells[3] ?? "").slice(0, 240),
    });
  });
  if (rows.length === 0 && errors.length === 0) {
    errors.push("No se encontraron movimientos válidos en el CSV.");
  }
  return { rows, errors };
}

function ReconciliationView({ permissions, onUnauthorized, onToast }: { permissions: string[]; onUnauthorized: () => void; onToast: (message: string) => void }) {
  const canManage = permissions.includes("finance.manage");
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [movements, setMovements] = useState<BankMovementPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [accountFilter, setAccountFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | BankMovementStatus>("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [importAccountId, setImportAccountId] = useState<string | null>(null);
  const [activeMovementId, setActiveMovementId] = useState<string | null>(null);
  const [statusBusyId, setStatusBusyId] = useState<string | null>(null);

  useEffect(() => {
    const handle = window.setTimeout(() => setQuery(search.trim()), 300);
    return () => window.clearTimeout(handle);
  }, [search]);

  useEffect(() => {
    setPage(1);
  }, [accountFilter, query, statusFilter, fromDate, toDate]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ page: String(page), page_size: String(RECONCILIATION_PAGE_SIZE) });
        if (accountFilter) params.set("bank_account_id", accountFilter);
        if (statusFilter) params.set("status", statusFilter);
        if (fromDate) params.set("from_date", fromDate);
        if (toDate) params.set("to_date", toDate);
        if (query) params.set("search", query);
        const [accountsResponse, movementsResponse] = await Promise.all([
          fetch("/api/admin/finance/bank-accounts", { cache: "no-store" }),
          fetch(`/api/admin/finance/bank-movements?${params.toString()}`, { cache: "no-store" }),
        ]);
        if (accountsResponse.status === 401 || movementsResponse.status === 401) {
          onUnauthorized();
          return;
        }
        if (!accountsResponse.ok || !movementsResponse.ok) {
          throw new Error("No se pudo consultar la conciliación bancaria.");
        }
        const accountsPayload = await accountsResponse.json() as { items: BankAccount[]; total: number };
        const movementsPayload = await movementsResponse.json() as BankMovementPage;
        if (!active) return;
        setAccounts(accountsPayload.items);
        setMovements(movementsPayload);
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "Error al cargar la conciliación.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [accountFilter, fromDate, onUnauthorized, page, query, refresh, statusFilter, toDate]);

  const summary = movements?.summary;
  const activeAccounts = accounts.filter((account) => account.status === "active");
  const selectedAccount = accounts.find((account) => account.id === accountFilter) ?? null;
  const importAccount = accounts.find((account) => account.id === importAccountId) ?? null;
  const rows = movements?.items ?? [];
  const total = movements?.total ?? 0;
  const pages = movements?.pages ?? 1;
  const oldestPending = summary?.oldest_pending_on ? formatDateOnly(summary.oldest_pending_on) : null;

  const openImport = () => {
    const target = selectedAccount && selectedAccount.status === "active" ? selectedAccount : activeAccounts[0] ?? null;
    if (!target) {
      onToast("Crea una cuenta bancaria activa antes de importar.");
      return;
    }
    setImportAccountId(target.id);
  };

  const toggleAccount = async (account: BankAccount) => {
    setStatusBusyId(account.id);
    setError("");
    try {
      const response = await fetch(`/api/admin/finance/bank-accounts/${encodeURIComponent(account.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: account.status === "active" ? "inactive" : "active" }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo actualizar la cuenta bancaria."));
        return;
      }
      setRefresh((value) => value + 1);
      onToast(account.status === "active" ? `Cuenta ${account.name} desactivada.` : `Cuenta ${account.name} reactivada.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setStatusBusyId(null);
    }
  };

  const statusFilters: { value: "" | BankMovementStatus; label: string }[] = [
    { value: "", label: "Todos" },
    { value: "pending", label: "Pendientes" },
    { value: "difference", label: "Con diferencia" },
    { value: "reviewing", label: "En revisión" },
    { value: "reconciled", label: "Conciliados" },
  ];

  return (
    <>
      <section className="access-summary-band pos-cash-band reconciliation-band">
        <div className="access-summary-main">
          <span className="summary-icon"><Landmark size={18} /></span>
          <div>
            <span>CONCILIACIÓN BANCARIA</span>
            <strong>{summary ? `${summary.count} movimientos · ${summary.pending} por conciliar · ${summary.difference} con diferencia` : "Consultando movimientos…"}</strong>
            <small className="report-timezone">Depósitos positivos y retiros negativos · vincular no duplica los ingresos del club</small>
          </div>
        </div>
        <div className="summary-divider" />
        <div className="summary-stat"><span>POR CONCILIAR</span><strong>{summary?.pending ?? "—"}</strong>{oldestPending && <small>El más antiguo · {oldestPending}</small>}</div>
        <div className="summary-stat"><span>DIFERENCIAS</span><strong>{summary?.difference ?? "—"}</strong>{summary && summary.difference_cents > 0 && <small>{formatMoney(summary.difference_cents)} por explicar</small>}</div>
        <div className="summary-stat"><span>INGRESOS</span><strong>{summary ? formatMoney(summary.inflow_cents) : "—"}</strong></div>
        <div className="summary-stat"><span>EGRESOS</span><strong>{summary ? formatMoney(Math.abs(summary.outflow_cents)) : "—"}</strong></div>
        {canManage && (
          <button className="button button-primary" onClick={openImport} disabled={activeAccounts.length === 0} title={activeAccounts.length === 0 ? "Crea una cuenta bancaria activa para importar" : "Importar estado de cuenta"}>
            <Upload size={16} />Importar estado
          </button>
        )}
      </section>

      {error && <div className="billing-alert" role="alert">{error}</div>}

      <section className="panel full-panel reconciliation-accounts-panel">
        <div className="panel-header access-list-heading">
          <div><p className="section-kicker">CUENTAS BANCARIAS</p><h2>Cuentas del club</h2></div>
          <div className="pos-row-actions">
            {selectedAccount && <button type="button" className="button button-secondary button-small" onClick={() => setAccountFilter("")}>Ver todas las cuentas</button>}
            {canManage && <button type="button" className="button button-secondary button-small" onClick={() => setCreateOpen(true)}><Plus size={15} />Nueva cuenta</button>}
          </div>
        </div>
        {accounts.length === 0 ? (
          <div className="reconciliation-empty">
            <Landmark size={22} />
            <div><strong>Sin cuentas bancarias</strong><span>{canManage ? "Crea una cuenta para importar el estado de cuenta y conciliar los pagos electrónicos." : "Un administrador debe crear la primera cuenta bancaria."}</span></div>
            {canManage && <button type="button" className="button button-primary button-small" onClick={() => setCreateOpen(true)}><Plus size={15} />Crear cuenta</button>}
          </div>
        ) : (
          <div className="reconciliation-account-grid">
            {accounts.map((account) => {
              const isSelected = accountFilter === account.id;
              return (
                <article key={account.id} className={`reconciliation-account ${isSelected ? "reconciliation-account-selected" : ""}`}>
                  <div className="reconciliation-account-head">
                    <span className="reconciliation-account-icon"><Landmark size={16} /></span>
                    <div><strong>{account.name}</strong><span>{account.bank_name} · •••• {account.account_last4}</span></div>
                    <span className={`status-badge ${account.status === "active" ? "status-good" : "status-neutral"}`}><i />{account.status === "active" ? "Activa" : "Inactiva"}</span>
                  </div>
                  <div className="reconciliation-account-values">
                    <div><span>SALDO</span><strong>{formatMoney(account.balance_cents)}</strong></div>
                    <div><span>PENDIENTES</span><strong>{account.pending_count}</strong></div>
                    <div><span>DIFERENCIAS</span><strong>{account.difference_count}</strong></div>
                  </div>
                  <div className="reconciliation-account-foot">
                    <span>{account.last_movement_on ? `Último movimiento ${formatDateOnly(account.last_movement_on)}` : "Sin movimientos"}</span>
                    <div className="pos-row-actions">
                      <button type="button" className="button button-secondary button-small" onClick={() => setAccountFilter(isSelected ? "" : account.id)}>{isSelected ? "Ver todas" : "Filtrar"}</button>
                      {canManage && <button type="button" className="button button-secondary button-small" disabled={account.status !== "active"} onClick={() => setImportAccountId(account.id)}>Importar</button>}
                      {canManage && <button type="button" className="button button-secondary button-small" disabled={statusBusyId === account.id} onClick={() => void toggleAccount(account)}>{statusBusyId === account.id ? "Guardando…" : account.status === "active" ? "Desactivar" : "Activar"}</button>}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="panel full-panel">
        <div className="panel-header access-list-heading">
          <div><p className="section-kicker">MOVIMIENTOS DEL BANCO</p><h2>Estado de cuenta</h2></div>
          {summary && summary.reconciled > 0 && <span className="status-badge status-good"><i />{summary.reconciled} conciliados</span>}
        </div>
        <div className="table-toolbar reconciliation-toolbar">
          <label className="table-search"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar referencia, descripción o coincidencia" /></label>
          <label className="table-select"><span>Cuenta</span><select value={accountFilter} onChange={(event) => setAccountFilter(event.target.value)}><option value="">Todas</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
          <label className="table-select"><span>Estado</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as "" | BankMovementStatus)}>{statusFilters.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
          <label className="table-select"><span>Desde</span><input type="date" value={fromDate} onChange={(event) => setFromDate(event.target.value)} /></label>
          <label className="table-select"><span>Hasta</span><input type="date" value={toDate} onChange={(event) => setToDate(event.target.value)} /></label>
          <span className="table-hint">Cada línea del banco se vincula a una sola operación interna</span>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>FECHA</th><th>CUENTA</th><th>REFERENCIA</th><th>IMPORTE</th><th>ESTADO</th><th>CONCILIACIÓN</th><th /></tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={7} className="empty-row">Cargando movimientos…</td></tr>
                : rows.length === 0 ? <tr><td colSpan={7} className="empty-row">{accounts.length === 0 ? "Crea una cuenta e importa tu primer estado de cuenta." : query || statusFilter || fromDate || toDate || accountFilter ? "No hay movimientos que coincidan con el filtro." : "Aún no hay movimientos importados."}</td></tr>
                : rows.map((movement) => {
                  const status = bankMovementStatus(movement.status);
                  return (
                    <tr key={movement.id}>
                      <td className="time-cell">{formatDateOnly(movement.occurred_on)}</td>
                      <td><strong>{movement.bank_account_name}</strong><small className="billing-inline-note">{movement.bank_name} · •••• {movement.account_last4}</small></td>
                      <td><strong>{movement.reference || "Sin referencia"}</strong><small className="billing-inline-note">{movement.description || "Sin descripción"}</small></td>
                      <td><span className={movement.amount_cents < 0 ? "reconciliation-amount-out" : "reconciliation-amount-in"}>{formatBankSignedAmount(movement.amount_cents)}</span></td>
                      <td><span className={`status-badge ${bankMovementStatusBadges[status]}`}><i />{bankMovementStatusLabels[status]}</span>{status === "difference" && movement.difference_cents !== null && <small className="billing-inline-note">Diferencia {formatMoney(Math.abs(movement.difference_cents))}</small>}</td>
                      <td>{movement.matched_label ? <><strong>{movement.matched_label}</strong><small className="billing-inline-note">{movement.matched_source ? bankSourceLabels[movement.matched_source] : "Operación vinculada"}</small></> : movement.suggestion_count > 0 ? <><span className="status-badge status-warn"><i />{movement.suggestion_count} {movement.suggestion_count === 1 ? "sugerencia" : "sugerencias"}</span>{movement.suggested_label && <small className="billing-inline-note">{movement.suggested_label}</small>}</> : <span className="billing-empty">Sin coincidencias</span>}</td>
                      <td><button className="button button-secondary button-small" onClick={() => setActiveMovementId(movement.id)}>Revisar</button></td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
        <div className="table-bottom">
          <span>{total} {total === 1 ? "movimiento" : "movimientos"}</span>
          {pages > 1 && (
            <span className="member-pagination">
              <span>Página {page} de {pages}</span>
              <button type="button" aria-label="Página anterior" disabled={page <= 1} onClick={() => setPage(Math.max(1, page - 1))}>‹</button>
              <button type="button" aria-label="Página siguiente" disabled={page >= pages} onClick={() => setPage(Math.min(pages, page + 1))}>›</button>
            </span>
          )}
        </div>
      </section>
      <footer className="page-footer"><span>Centro Fit · Conciliación bancaria</span><span>{canManage ? "IMPORTACIÓN, VÍNCULO Y REVISIÓN" : "CONSULTA DE MOVIMIENTOS"}</span></footer>

      {createOpen && (
        <NewBankAccountModal
          onClose={() => setCreateOpen(false)}
          onCreated={(message) => { setCreateOpen(false); setRefresh((value) => value + 1); onToast(message); }}
          onUnauthorized={onUnauthorized}
        />
      )}
      {importAccount && (
        <BankImportModal
          key={importAccount.id}
          account={importAccount}
          onClose={() => setImportAccountId(null)}
          onImported={(result) => {
            setImportAccountId(null);
            setAccountFilter(importAccount.id);
            setStatusFilter("");
            setPage(1);
            setRefresh((value) => value + 1);
            const importedLabel = result.imported === 1 ? "Importado 1" : `Importados ${result.imported}`;
            const totalLabel = result.total_rows === 1 ? "movimiento" : "movimientos";
            const skippedLabel = result.duplicates === 1 ? "1 duplicado omitido" : `${result.duplicates} duplicados omitidos`;
            onToast(`${importedLabel} de ${result.total_rows} ${totalLabel}${result.duplicates > 0 ? `; ${skippedLabel}` : ""}.`);
          }}
          onUnauthorized={onUnauthorized}
        />
      )}
      {activeMovementId && (
        <BankMovementModal
          key={activeMovementId}
          movementId={activeMovementId}
          canManage={canManage}
          onClose={() => setActiveMovementId(null)}
          onChanged={(message) => { setRefresh((value) => value + 1); onToast(message); }}
          onUnauthorized={onUnauthorized}
        />
      )}
    </>
  );
}

function NewBankAccountModal({ onClose, onCreated, onUnauthorized }: { onClose: () => void; onCreated: (message: string) => void; onUnauthorized: () => void }) {
  const [name, setName] = useState("");
  const [bankName, setBankName] = useState("");
  const [last4, setLast4] = useState("");
  const [currency, setCurrency] = useState("MXN");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const displayName = name.trim();
    const bank = bankName.trim();
    if (displayName.length < 2) { setError("Escribe un nombre de cuenta de al menos 2 caracteres."); return; }
    if (bank.length < 2) { setError("Escribe el nombre del banco."); return; }
    if (!/^\d{4}$/.test(last4)) { setError("Los últimos 4 dígitos deben ser exactamente 4 números."); return; }
    if (!/^[A-Za-z]{3}$/.test(currency.trim())) { setError("La moneda debe ser un código de 3 letras, por ejemplo MXN."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/finance/bank-accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: displayName, bank_name: bank, account_last4: last4, currency: currency.trim().toUpperCase() }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo crear la cuenta bancaria."));
        return;
      }
      const created = await response.json() as BankAccount;
      onCreated(`Cuenta ${created.name} creada.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="new-bank-account-title">
        <div className="modal-header"><span className="modal-icon"><Landmark size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">CONCILIACIÓN BANCARIA</p>
        <h2 id="new-bank-account-title">Nueva cuenta bancaria</h2>
        <p className="modal-subtitle">Registra la cuenta del club que recibirá los pagos electrónicos. Los movimientos se cargan desde el estado de cuenta del banco.</p>
        <form onSubmit={submit}>
          <div className="form-row">
            <label className="form-field"><span>Nombre de la cuenta *</span><input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} placeholder="Cuenta operativa" /></label>
            <label className="form-field"><span>Banco *</span><input value={bankName} onChange={(event) => setBankName(event.target.value)} maxLength={80} placeholder="BBVA" /></label>
          </div>
          <div className="form-row">
            <label className="form-field"><span>Últimos 4 dígitos *</span><input value={last4} onChange={(event) => setLast4(event.target.value.replace(/\D/g, "").slice(0, 4))} inputMode="numeric" maxLength={4} placeholder="1234" /></label>
            <label className="form-field"><span>Moneda</span><input value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase().slice(0, 3))} maxLength={3} placeholder="MXN" /></label>
          </div>
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-note"><ShieldCheck size={16} /><span>Una cuenta inactiva conserva su historial pero no acepta nuevas importaciones. No se pueden eliminar cuentas con movimientos.</span></div>
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy}><Check size={16} />{busy ? "Guardando…" : "Crear cuenta"}</button></div>
        </form>
      </section>
    </div>
  );
}

function BankImportModal({ account, onClose, onImported, onUnauthorized }: { account: BankAccount; onClose: () => void; onImported: (result: { imported: number; duplicates: number; total_rows: number }) => void; onUnauthorized: () => void }) {
  const [csv, setCsv] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const parsed = useMemo(() => parseBankCsv(csv), [csv]);
  const hasCsv = csv.trim().length > 0;
  const incomingCents = parsed.rows.filter((row) => row.amount_cents > 0).reduce((sum, row) => sum + row.amount_cents, 0);
  const outgoingCents = parsed.rows.filter((row) => row.amount_cents < 0).reduce((sum, row) => sum + row.amount_cents, 0);

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const text = await file.text();
      setCsv(text);
      setError("");
    } catch {
      setError("No se pudo leer el archivo CSV.");
    }
  };

  const loadSample = () => {
    const today = todayDateInput();
    setCsv(`fecha,importe,referencia,descripcion\n${today},11600.00,TRF-EJEMPLO,Pago de factura de ejemplo\n${today},-450.00,COMISION,Comisión bancaria de ejemplo`);
    setError("");
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (parsed.errors.length > 0) { setError("Corrige las líneas con error antes de importar."); return; }
    if (parsed.rows.length === 0) { setError("Agrega al menos un movimiento válido."); return; }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/finance/bank-accounts/${encodeURIComponent(account.id)}/movements`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows: parsed.rows }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudieron importar los movimientos."));
        return;
      }
      const result = await response.json() as { imported: number; duplicates: number; total_rows: number };
      onImported(result);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="bank-import-title">
        <div className="modal-header"><span className="modal-icon"><Upload size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        <p className="section-kicker">IMPORTAR ESTADO DE CUENTA</p>
        <h2 id="bank-import-title">{account.name}</h2>
        <p className="modal-subtitle">{account.bank_name} · •••• {account.account_last4} · Formato CSV: fecha, importe, referencia, descripción. Usa importes negativos para retiros.</p>
        <form onSubmit={submit}>
          <div className="reconciliation-import-sample">
            <label className="button button-secondary button-small reconciliation-file-button"><Upload size={15} />Cargar CSV<input type="file" accept=".csv,text/csv" hidden onChange={(event) => void handleFile(event)} /></label>
            <button type="button" className="button button-secondary button-small" onClick={loadSample}>Cargar ejemplo</button>
          </div>
          <label className="form-field">
            <span>Contenido CSV</span>
            <textarea value={csv} onChange={(event) => { setCsv(event.target.value); setError(""); }} rows={6} placeholder={"fecha,importe,referencia,descripcion\n2026-10-20,11600.00,TRF-4821,Pago de factura A-000001\n2026-10-21,-450.00,COMISION,Comisión anual"} />
          </label>
          {hasCsv && parsed.errors.length > 0 && (
            <div className="billing-alert" role="alert">
              {parsed.errors.slice(0, 5).map((message, index) => <div key={`${index}-${message}`}>{message}</div>)}
              {parsed.errors.length > 5 && <div>Y {parsed.errors.length - 5} errores más.</div>}
            </div>
          )}
          {hasCsv && parsed.rows.length > 0 && (
            <>
              <div className="reconciliation-import-preview">
                <div><span>MOVIMIENTOS VÁLIDOS</span><strong>{parsed.rows.length}</strong></div>
                <div><span>INGRESOS</span><strong>{formatMoney(incomingCents)}</strong></div>
                <div><span>RETIROS</span><strong>{formatMoney(Math.abs(outgoingCents))}</strong></div>
              </div>
              <div className="table-scroll reconciliation-import-table">
                <table className="data-table compact-table">
                  <thead><tr><th>FECHA</th><th>IMPORTE</th><th>REFERENCIA</th><th>DESCRIPCIÓN</th></tr></thead>
                  <tbody>
                    {parsed.rows.slice(0, 6).map((row, index) => (
                      <tr key={`${row.occurred_on}-${row.amount_cents}-${index}`}>
                        <td>{formatDateOnly(row.occurred_on)}</td>
                        <td><span className={row.amount_cents < 0 ? "reconciliation-amount-out" : "reconciliation-amount-in"}>{formatBankSignedAmount(row.amount_cents)}</span></td>
                        <td>{row.reference || "—"}</td>
                        <td>{row.description || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {parsed.rows.length > 6 && <p className="billing-empty">Se muestran 6 de {parsed.rows.length} movimientos; el lote completo se enviará al confirmar.</p>}
            </>
          )}
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="modal-note"><ShieldCheck size={16} /><span>La importación es idempotente: una línea idéntica ya importada se omite. Si una fila es inválida, no se guarda ninguna del lote.</span></div>
          <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={busy || parsed.rows.length === 0 || parsed.errors.length > 0}><Upload size={16} />{busy ? "Importando…" : "Importar movimientos"}</button></div>
        </form>
      </section>
    </div>
  );
}

function BankMovementModal({ movementId, canManage, onClose, onChanged, onUnauthorized }: { movementId: string; canManage: boolean; onClose: () => void; onChanged: (message: string) => void; onUnauthorized: () => void }) {
  const [detail, setDetail] = useState<BankMovementDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [note, setNote] = useState("");
  const [unmatchOpen, setUnmatchOpen] = useState(false);
  const [unmatchReason, setUnmatchReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams();
        if (appliedSearch.trim()) params.set("candidate_search", appliedSearch.trim());
        const queryString = params.toString();
        const response = await fetch(`/api/admin/finance/bank-movements/${encodeURIComponent(movementId)}${queryString ? `?${queryString}` : ""}`, { cache: "no-store" });
        if (response.status === 401) { onUnauthorized(); return; }
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(billingErrorDetail(payload, "No se pudo consultar el movimiento."));
        }
        const payload = await response.json() as BankMovementDetail;
        if (active) setDetail(payload);
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "Error al consultar el movimiento.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [appliedSearch, movementId, onUnauthorized, refresh]);

  const afterAction = (message: string) => {
    setNote("");
    setUnmatchOpen(false);
    setUnmatchReason("");
    setRefresh((value) => value + 1);
    onChanged(message);
  };

  const match = async (candidate: BankMovementCandidate) => {
    const reason = note.trim();
    if (!candidate.amount_match && reason.length < 3) {
      setError("El importe no coincide. Escribe el motivo de la diferencia (mínimo 3 caracteres).");
      return;
    }
    setBusy(`match:${candidate.source_id}`);
    setError("");
    try {
      const response = await fetch(`/api/admin/finance/bank-movements/${encodeURIComponent(movementId)}/match`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: candidate.source, source_id: candidate.source_id, note: reason || null }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo conciliar el movimiento."));
        return;
      }
      afterAction(candidate.amount_match
        ? `Movimiento conciliado con ${candidate.label}.`
        : `Movimiento conciliado con ${candidate.label}; diferencia de ${formatMoney(Math.abs(candidate.difference_cents))}.`);
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(null);
    }
  };

  const unmatch = async () => {
    const reason = unmatchReason.trim();
    if (reason.length < 3) { setError("Escribe el motivo de la desvinculación."); return; }
    setBusy("unmatch");
    setError("");
    try {
      const response = await fetch(`/api/admin/finance/bank-movements/${encodeURIComponent(movementId)}/unmatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo deshacer la conciliación."));
        return;
      }
      afterAction("Coincidencia desvinculada; el movimiento volvió a pendiente.");
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(null);
    }
  };

  const flag = async (status: "pending" | "difference" | "reviewing") => {
    const reason = note.trim();
    if (status !== "pending" && reason.length < 3) {
      setError("Escribe una nota para marcar la revisión o la diferencia.");
      return;
    }
    setBusy(`flag:${status}`);
    setError("");
    try {
      const response = await fetch(`/api/admin/finance/bank-movements/${encodeURIComponent(movementId)}/flag`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, note: reason || null }),
      });
      if (response.status === 401) { onUnauthorized(); return; }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        setError(billingErrorDetail(payload, "No se pudo actualizar la revisión."));
        return;
      }
      afterAction(status === "pending" ? "Movimiento devuelto a pendiente." : status === "difference" ? "Movimiento marcado con diferencia." : "Movimiento marcado en revisión.");
    } catch {
      setError("No se pudo conectar con el backend.");
    } finally {
      setBusy(null);
    }
  };

  const status = detail ? bankMovementStatus(detail.status) : "pending";

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal modal-wide billing-modal" role="dialog" aria-modal="true" aria-labelledby="bank-movement-title">
        <div className="modal-header"><span className="modal-icon"><Landmark size={19} /></span><button className="icon-button" aria-label="Cerrar" onClick={onClose}><X size={19} /></button></div>
        {!detail ? (
          <>
            <p className="section-kicker">CONCILIACIÓN BANCARIA</p>
            <h2 id="bank-movement-title">{loading ? "Cargando movimiento…" : "Movimiento no disponible"}</h2>
            {error && <div className="login-error" role="alert">{error}</div>}
            <div className="modal-actions"><button className="button button-secondary" onClick={onClose}>Cerrar</button></div>
          </>
        ) : (
          <>
            <p className="section-kicker">CONCILIACIÓN BANCARIA · {detail.currency}</p>
            <h2 id="bank-movement-title" className={detail.amount_cents < 0 ? "reconciliation-detail-out" : "reconciliation-detail-in"}>{formatBankSignedAmount(detail.amount_cents)}</h2>
            <p className="modal-subtitle">{detail.bank_account_name} · {detail.bank_name} •••• {detail.account_last4} · {formatDateOnly(detail.occurred_on)}</p>
            <div className="billing-detail-status">
              <span className={`status-badge ${bankMovementStatusBadges[status]}`}><i />{bankMovementStatusLabels[status]}</span>
              {detail.matched_source && <span className="status-badge status-neutral"><i />{bankSourceLabels[detail.matched_source]}</span>}
              {detail.suggestion_count > 0 && !detail.matched_id && <span className="status-badge status-warn"><i />{detail.suggestion_count} {detail.suggestion_count === 1 ? "sugerencia" : "sugerencias"}</span>}
            </div>
            {error && <div className="login-error" role="alert">{error}</div>}

            <div className="detail-section">
              <div className="modal-section-title"><span>DETALLE DEL MOVIMIENTO</span><span>{loading ? "Actualizando…" : detail.currency}</span></div>
              <div className="billing-detail-grid">
                <div><span>FECHA</span><strong>{formatDateOnly(detail.occurred_on)}</strong></div>
                <div><span>REFERENCIA</span><strong>{detail.reference || "—"}</strong></div>
                <div><span>DESCRIPCIÓN</span><strong>{detail.description || "—"}</strong></div>
                <div><span>IMPORTE</span><strong>{formatBankSignedAmount(detail.amount_cents)}</strong></div>
                <div><span>IMPORTADO</span><strong>{formatMoment(detail.imported_at)}</strong></div>
                <div><span>CONCILIADO</span><strong>{formatMoment(detail.reconciled_at)}</strong></div>
                <div><span>REVISADO</span><strong>{formatMoment(detail.reviewed_at)}</strong></div>
                <div><span>NOTA</span><strong>{detail.note || "—"}</strong></div>
              </div>
            </div>

            {detail.matched_id && (
              <div className="reconciliation-match-card">
                <span className="summary-icon"><Check size={16} /></span>
                <div>
                  <span>OPERACIÓN VINCULADA</span>
                  <strong>{detail.matched_label}</strong>
                  <small>{detail.matched_source ? bankSourceLabels[detail.matched_source] : "Operación interna"}{detail.difference_cents !== null && detail.difference_cents !== 0 ? ` · Diferencia ${formatMoney(Math.abs(detail.difference_cents))}` : " · Importe exacto"}</small>
                </div>
              </div>
            )}

            {!detail.matched_id && (
              <div className="detail-section">
                <div className="modal-section-title"><span>COINCIDENCIAS INTERNAS</span><span>{detail.candidates.length}</span></div>
                {canManage && (
                  <form className="reconciliation-manual-search" onSubmit={(event) => { event.preventDefault(); setAppliedSearch(search.trim()); }}>
                    <label className="table-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar por folio, socio, plan o referencia" /></label>
                    <button type="submit" className="button button-secondary button-small" disabled={loading || !search.trim()}>Buscar</button>
                    {appliedSearch && <button type="button" className="button button-secondary button-small" onClick={() => { setSearch(""); setAppliedSearch(""); }}>Limpiar</button>}
                  </form>
                )}
                {detail.candidates.length === 0 ? (
                  <p className="billing-empty">{appliedSearch ? `No se encontraron operaciones para «${appliedSearch}».` : "No hay operaciones compatibles con la fecha y el importe. Usa la búsqueda manual para ampliar a ±60 días."}</p>
                ) : (
                  <>
                    <p className="reconciliation-hint">Se muestran operaciones electrónicas dentro de ±{appliedSearch ? "60" : "7"} días. Si el importe no coincide, escribe la nota de revisión antes de conciliar.</p>
                    <div className="reconciliation-candidates">
                      {detail.candidates.map((candidate) => (
                        <div key={`${candidate.source}-${candidate.source_id}`} className="reconciliation-candidate">
                          <div className="reconciliation-candidate-main">
                            <strong>{candidate.label}</strong>
                            <small>{candidate.detail}{candidate.reference ? ` · Ref. ${candidate.reference}` : ""} · {formatDateOnly(candidate.occurred_on)} · {bankSourceLabels[candidate.source]}</small>
                          </div>
                          <div className="reconciliation-candidate-side">
                            <strong>{formatMoney(candidate.amount_cents)}</strong>
                            {candidate.amount_match
                              ? <span className="status-badge status-good"><i />Importe exacto</span>
                              : <span className="status-badge status-warn"><i />Dif. {formatMoney(Math.abs(candidate.difference_cents))}</span>}
                            {canManage && (
                              <button type="button" className="button button-primary button-small" disabled={busy !== null || loading} onClick={() => void match(candidate)}>
                                {busy === `match:${candidate.source_id}` ? "Conciliando…" : "Conciliar"}
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

            {canManage && !detail.matched_id && (
              <div className="detail-section">
                <div className="modal-section-title"><span>NOTA DE REVISIÓN</span><span>{note.length}/300</span></div>
                <label className="form-field"><span>Nota para conciliar con diferencia o marcar revisión *</span><input value={note} onChange={(event) => setNote(event.target.value)} maxLength={300} placeholder="Ej. Comisión descontada por el banco" /></label>
                <div className="reconciliation-flag-actions">
                  {status !== "reviewing" && <button type="button" className="button button-secondary button-small" disabled={busy !== null || loading} onClick={() => void flag("reviewing")}><Clock3 size={14} />Marcar en revisión</button>}
                  {status !== "difference" && <button type="button" className="button button-secondary button-small" disabled={busy !== null || loading} onClick={() => void flag("difference")}><Flag size={14} />Marcar diferencia</button>}
                  {status !== "pending" && <button type="button" className="button button-secondary button-small" disabled={busy !== null || loading} onClick={() => void flag("pending")}><RotateCcw size={14} />Regresar a pendiente</button>}
                </div>
              </div>
            )}

            {canManage && detail.matched_id && (
              <div className="detail-section">
                <div className="modal-section-title"><span>DESHACER CONCILIACIÓN</span></div>
                {!unmatchOpen ? (
                  <button type="button" className="button button-danger" onClick={() => setUnmatchOpen(true)}><Unlink size={15} />Desvincular coincidencia</button>
                ) : (
                  <div className="reconciliation-unmatch-form">
                    <label className="form-field"><span>Motivo *</span><input value={unmatchReason} onChange={(event) => setUnmatchReason(event.target.value)} maxLength={300} placeholder="Explica por qué se desvincula" /></label>
                    <div className="modal-actions">
                      <button type="button" className="button button-secondary" onClick={() => { setUnmatchOpen(false); setUnmatchReason(""); }}>Cancelar</button>
                      <button type="button" className="button button-danger" disabled={busy !== null || loading} onClick={() => void unmatch()}>{busy === "unmatch" ? "Desvinculando…" : "Desvincular"}</button>
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="detail-section">
              <div className="modal-section-title"><span>BITÁCORA DEL MOVIMIENTO</span><span>{detail.events.length}</span></div>
              <div className="billing-timeline">
                {detail.events.map((event) => (
                  <div className="billing-event" key={event.id}>
                    <span className="billing-event-dot" />
                    <div>
                      <strong>{bankEventLabel(event.event_type)}</strong>
                      <small>{formatMoment(event.occurred_at)}{event.actor_email ? ` · ${event.actor_email}` : ""}</small>
                      {event.detail && <small>{event.detail}</small>}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="modal-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cerrar</button></div>
          </>
        )}
      </section>
    </div>
  );
}