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
