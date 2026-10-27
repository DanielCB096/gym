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
