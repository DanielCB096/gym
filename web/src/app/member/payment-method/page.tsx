import type { Metadata } from "next";

import { MemberPaymentMethodSetupClient } from "./setup-client";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Captura segura de tarjeta | Centro Fit",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function MemberPaymentMethodPage() {
  return <MemberPaymentMethodSetupClient />;
}
