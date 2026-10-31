export type NotificationDestination =
  | "home"
  | "invoices"
  | "classes"
  | "physio"
  | "routines"
  | "notifications";

const CLASS_KINDS = new Set([
  "class_reminder",
  "class_reserved",
  "class_cancelled",
  "class_rescheduled",
  "class_waitlist_promoted",
]);

const PHYSIO_KINDS = new Set([
  "physio_appointment_scheduled",
  "physio_appointment_cancelled",
  "physio_appointment_rescheduled",
  "physio_reminder",
]);

const ROUTINE_KINDS = new Set([
  "workout_reviewed",
  "goal_achieved",
  "goal_cancelled_by_staff",
  "goal_updated_by_staff",
  "equipment_out_of_service",
]);

// A kind the app does not know yet lands in the inbox instead of guessing a
// screen, so the notice is never lost.
export function notificationDestination(kind: string): NotificationDestination {
  if (kind.startsWith("invoice_")) {
    return "invoices";
  }
  if (CLASS_KINDS.has(kind)) {
    return "classes";
  }
  if (PHYSIO_KINDS.has(kind)) {
    return "physio";
  }
  if (ROUTINE_KINDS.has(kind)) {
    return "routines";
  }
  if (kind === "membership_expiring") {
    return "home";
  }
  return "notifications";
}
