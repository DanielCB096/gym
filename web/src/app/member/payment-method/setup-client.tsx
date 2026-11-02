"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

type SetupConfiguration = {
  public_key: string;
  plan_name: string;
  amount_cents: number;
  currency: string;
};

type SetupResult = {
  status: string;
  payment_attempt_id: string;
  membership_id: string;
};

type ConektaToken = { id: string };
type ConektaCardOptions = {
  config: { targetIFrame: string; publicKey: string; locale: "es" };
  options: {
    backgroundMode: "lightMode";
    colorPrimary: string;
    colorText: string;
    colorLabel: string;
    hideLogo: false;
    inputType: "minimalMode";
    excludeCardNetworks: string[];
  };
  callbacks: {
    onCreateTokenSucceeded: (token: ConektaToken) => void;
    onCreateTokenError: (_error: unknown) => void;
    onGetInfoSuccess: (_loadingTime: number) => void;
  };
};

declare global {
  interface Window {
    ConektaCheckoutComponents?: {
      Card: (options: ConektaCardOptions) => void;
    };
  }
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : "No se pudo completar la operación. Solicita un nuevo enlace desde la app.";
    throw new Error(detail);
  }
  return payload as T;
}

function formatAmount(amountCents: number, currency: string): string {
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency,
  }).format(amountCents / 100);
}

export function MemberPaymentMethodSetupClient() {
  const setupTokenRef = useRef<string | null>(null);
  const initializedRef = useRef(false);
  const completedRef = useRef(false);
  const [configuration, setConfiguration] = useState<SetupConfiguration | null>(null);
  const [scriptLoaded, setScriptLoaded] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SetupResult | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (setupTokenRef.current !== null) {
      return;
    }
    const setupToken = window.location.hash.slice(1);
    window.history.replaceState(null, "", window.location.pathname);
    if (!/^[A-Za-z0-9_-]{40,60}$/.test(setupToken)) {
      setError("El enlace de captura no es válido. Solicita uno nuevo desde la app.");
      setLoading(false);
      return;
    }
    setupTokenRef.current = setupToken;
    void postJson<SetupConfiguration>(
      "/api/member/membership/payment-method/setup/config",
      { setup_token: setupToken },
    )
      .then(setConfiguration)
      .catch((loadError: unknown) => {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "No se pudo validar el enlace de captura.",
        );
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const tokenizer = window.ConektaCheckoutComponents;
    const container = document.getElementById("conektaIframeContainer");
    if (
      !configuration ||
      !scriptLoaded ||
      !confirmed ||
      !tokenizer ||
      !container ||
      initializedRef.current ||
      result
    ) {
      return;
    }
    initializedRef.current = true;
    tokenizer.Card({
      config: {
        targetIFrame: "#conektaIframeContainer",
        publicKey: configuration.public_key,
        locale: "es",
      },
      options: {
        backgroundMode: "lightMode",
        colorPrimary: "#166534",
        colorText: "#1f2937",
        colorLabel: "#4b5563",
        hideLogo: false,
        inputType: "minimalMode",
        excludeCardNetworks: [],
      },
      callbacks: {
        onCreateTokenSucceeded: (token) => {
          if (completedRef.current || !/^tok_[A-Za-z0-9_-]{1,250}$/.test(token?.id ?? "")) {
            setError("Conekta no devolvió un token de tarjeta válido.");
            return;
          }
          completedRef.current = true;
          setError(null);
          void postJson<SetupResult>(
            "/api/member/membership/payment-method/setup/complete",
            { setup_token: setupTokenRef.current, card_token: token.id },
          )
            .then(setResult)
            .catch((completeError: unknown) => {
              completedRef.current = false;
              setError(
                completeError instanceof Error
                  ? completeError.message
                  : "No se pudo enviar la renovación a Conekta.",
              );
            });
        },
        onCreateTokenError: () => {
          setError("Conekta no pudo validar la tarjeta. Revisa los datos e intenta de nuevo.");
        },
        onGetInfoSuccess: () => undefined,
      },
    });
  }, [configuration, confirmed, result, scriptLoaded]);

  return (
    <main style={styles.page}>
      {configuration && confirmed && !result ? (
        <Script
          src="https://pay.conekta.com/v1.0/js/conekta-checkout.min.js"
          strategy="afterInteractive"
          onLoad={() => setScriptLoaded(true)}
          onError={() => setError("No se pudo cargar el formulario seguro de Conekta.")}
        />
      ) : null}
      <section style={styles.card}>
        <h1 style={styles.title}>Renovación de membresía</h1>
        {loading ? <p>Validando enlace seguro…</p> : null}
        {configuration && !result ? (
          <>
            <p>
              Plan: <strong>{configuration.plan_name}</strong>
            </p>
            <p>
              Al completar la captura, se intentará el cobro normal de renovación por{" "}
              <strong>{formatAmount(configuration.amount_cents, configuration.currency)}</strong>.
              No se realizará un cargo de verificación.
            </p>
            {!confirmed ? (
              <label style={styles.confirmation}>
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.currentTarget.checked)}
                />
                Confirmo que deseo pagar esta renovación y guardar la tarjeta para los ciclos
                futuros autorizados.
              </label>
            ) : null}
            {confirmed ? (
              <div id="conektaIframeContainer" style={styles.iframeContainer} />
            ) : null}
          </>
        ) : null}
        {result ? (
          <p role="status">
            La renovación se envió a Conekta. El acceso se habilitará cuando el gimnasio reciba y
            valide la confirmación segura del pago.
          </p>
        ) : null}
        {error ? (
          <p role="alert" style={styles.error}>
            {error}
          </p>
        ) : null}
        <p style={styles.notice}>
          Los datos de tarjeta se capturan directamente en Conekta. Centro Fit no recibe ni guarda
          el número de tarjeta ni el CVV.
        </p>
      </section>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    display: "grid",
    placeItems: "center",
    padding: "24px",
    background: "#f3f4f6",
    color: "#111827",
    fontFamily: "Arial, sans-serif",
  },
  card: {
    width: "min(100%, 620px)",
    padding: "28px",
    borderRadius: "16px",
    background: "#ffffff",
    boxShadow: "0 12px 36px rgba(15, 23, 42, 0.12)",
  },
  title: { marginTop: 0 },
  confirmation: {
    display: "flex",
    gap: "12px",
    alignItems: "flex-start",
    margin: "24px 0",
    lineHeight: 1.5,
  },
  iframeContainer: { minHeight: "580px" },
  error: { color: "#b91c1c" },
  notice: { marginTop: "24px", color: "#4b5563", fontSize: "14px" },
};
