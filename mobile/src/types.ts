export type MemberSummary = {
  id: string;
  first_name: string;
  last_name: string;
  email: string | null;
  status: string;
};

export type MemberMembership = {
  plan_name: string;
  status: string;
  starts_at: string;
  ends_at: string;
  auto_renew: boolean;
  days_remaining: number;
};

export type MemberProfile = {
  id: string;
  first_name: string;
  last_name: string;
  email: string | null;
  phone: string | null;
  status: string;
  member_since: string;
  membership: MemberMembership | null;
  balance_cents: number;
  access_enabled: boolean;
};

export type MemberLoginResult = {
  access_token: string;
  token_type: string;
  expires_at: string;
  member: MemberSummary;
};

export type CodeRequestResult = {
  status: "accepted";
  expires_in: number;
  preview_code: string | null;
};

export type MemberClassReservation = {
  id: string;
  session_id: string;
  status: string;
  waitlist_position: number | null;
  late_cancellation: boolean;
  created_at: string;
};

export type MemberClass = {
  id: string;
  title: string;
  class_type_name: string;
  room_name: string | null;
  instructor_name: string | null;
  starts_at: string;
  ends_at: string;
  capacity: number;
  access_type: string;
  extra_price_cents: number;
  waitlist_enabled: boolean;
  cancel_window_hours: number;
  notes: string | null;
  reserved_count: number;
  waitlist_count: number;
  spots_left: number;
  can_reserve: boolean;
  blocked_reason: string | null;
  reservation: MemberClassReservation | null;
};

export type MemberClassPage = {
  items: MemberClass[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export type MemberRoutineAssignment = {
  id: string;
  routine_id: string;
  routine_name: string;
  routine_version: number;
  trainer_name: string | null;
  start_date: string;
  end_date: string | null;
  frequency_per_week: number | null;
  status: string;
  notes: string | null;
  workouts_logged: number;
  last_workout_at: string | null;
  created_at: string;
  ended_at: string | null;
};

export type MemberRoutineList = {
  items: MemberRoutineAssignment[];
  total: number;
  active: number;
  completed: number;
  cancelled: number;
};

export type MemberRoutineLine = {
  id: string;
  exercise_id: string;
  exercise_name: string;
  muscle_group: string;
  category: string;
  equipment_status: string | null;
  position: number;
  sets: number;
  reps: string;
  rest_seconds: number | null;
  load_note: string | null;
  notes: string | null;
};

export type MemberWorkoutSet = {
  exercise_id: string;
  exercise_name: string;
  position: number;
  set_number: number;
  reps: number;
  weight_kg: number | null;
};

export type MemberWorkoutSetInput = {
  exercise_id: string;
  set_number: number;
  reps: number;
  weight_kg?: number | null;
};

export type MemberWorkout = {
  id: string;
  assignment_id: string;
  member_id: string;
  routine_id: string;
  routine_version: number;
  performed_at: string;
  duration_minutes: number | null;
  perceived_effort: number | null;
  notes: string | null;
  status: string;
  origin: string;
  reviewed_at: string | null;
  created_at: string;
  sets: MemberWorkoutSet[];
};

export type MemberWorkoutInput = {
  performed_at: string;
  duration_minutes?: number | null;
  perceived_effort?: number | null;
  notes?: string | null;
  sets?: MemberWorkoutSetInput[];
};

export type MemberRoutineDetail = {
  assignment: MemberRoutineAssignment;
  objective: string | null;
  plan: MemberRoutineLine[];
  workouts: MemberWorkout[];
};

export type MemberMeasurement = {
  id: string;
  member_id: string;
  measured_at: string;
  weight_kg: number | null;
  waist_cm: number | null;
  chest_cm: number | null;
  body_fat_percent: number | null;
  notes: string | null;
  origin: string;
  created_at: string;
};

export type MemberMeasurementInput = {
  measured_at?: string;
  weight_kg?: number;
  waist_cm?: number;
  chest_cm?: number;
  body_fat_percent?: number;
  notes?: string | null;
};

export type MemberGoal = {
  id: string;
  member_id: string;
  metric: string;
  direction: string;
  target_value: number;
  baseline_value: number | null;
  baseline_measured_at: string | null;
  target_date: string | null;
  notes: string | null;
  status: string;
  origin: string;
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

export type MemberGoalInput = {
  metric: string;
  direction: string;
  target_value: number;
  target_date?: string | null;
  notes?: string | null;
};

export type MemberProgress = {
  workouts_total: number;
  workouts_last_30_days: number;
  last_workout_at: string | null;
  latest_measurement: MemberMeasurement | null;
  measurements: MemberMeasurement[];
  goals: MemberGoal[];
};

export type MemberPayment = {
  id: string;
  amount_cents: number;
  currency: string;
  method: string;
  paid_at: string;
  period_starts_at: string | null;
  period_ends_at: string | null;
  plan_name: string | null;
  note: string | null;
};

export type MemberPaymentPage = {
  items: MemberPayment[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  total_paid_cents: number;
};

export type MemberNotification = {
  id: string;
  kind: string;
  title: string;
  body: string;
  ref_id: string | null;
  created_at: string;
  read_at: string | null;
};

export type MemberNotificationPage = {
  items: MemberNotification[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  unread_total: number;
};

export type MemberAccountEntry = {
  kind: string;
  occurred_at: string;
  description: string;
  reference: string;
  method: string | null;
  amount_cents: number;
  balance_cents: number;
};

export type MemberAccount = {
  charges_cents: number;
  credits_cents: number;
  payments_cents: number;
  balance_cents: number;
  charges_count: number;
  payments_count: number;
  last_activity_at: string | null;
  oldest_charge_at: string | null;
  as_of: string;
  entries: MemberAccountEntry[];
  entries_total: number;
};
