export type NotificationDestination =
  | "home"
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
  "equipment_back_in_service",
]);

export type NotificationRefTarget =
  | "reservation"
  | "class_session"
  | "physio_appointment"
  | "goal";

export type NotificationFocus = {
  destination: NotificationDestination;
  target: NotificationRefTarget;
  refId: string;
};

// Which row the notice's ref_id points to. A notice only focuses an item when
// its reference is something the destination screen actually lists; a workout
// or an equipment has no row of its own, so those notices keep opening their
// section without a highlight.
export function notificationRefTarget(
  kind: string,
): NotificationRefTarget | null {
  if (
    kind === "class_reserved" ||
    kind === "class_waitlist_promoted" ||
    kind === "class_reminder"
  ) {
    return "reservation";
  }
  if (kind === "class_cancelled" || kind === "class_rescheduled") {
    return "class_session";
  }
  if (kind.startsWith("physio_")) {
    return "physio_appointment";
  }
  if (kind.startsWith("goal_")) {
    return "goal";
  }
  return null;
}

export function notificationFocus(
  kind: string,
  refId: string | null,
): NotificationFocus | null {
  const target = notificationRefTarget(kind);
  if (!refId || !target) {
    return null;
  }
  const destination = notificationDestination(kind);
  if (destination === "notifications" || destination === "home") {
    return null;
  }
  return { destination, target, refId };
}

// A kind the app does not know yet lands in the inbox instead of guessing a
// screen, so the notice is never lost.
export function notificationDestination(kind: string): NotificationDestination {
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
