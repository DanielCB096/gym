"use strict";

const CONFIG_KEY = "centrofit.sign.config.v1";
const REQUEST_TIMEOUT_MS = 10000;
const REFRESH_MS = 60000;

const elements = {
  setupView: document.getElementById("setup-view"),
  signView: document.getElementById("sign-view"),
  setupForm: document.getElementById("setup-form"),
  apiUrl: document.getElementById("api-url"),
  deviceToken: document.getElementById("device-token"),
  setupError: document.getElementById("setup-error"),
  setupCancel: document.getElementById("setup-cancel"),
  openSetup: document.getElementById("open-setup"),
  list: document.getElementById("equipment-list"),
  empty: document.getElementById("sign-empty"),
  loading: document.getElementById("sign-loading"),
  offline: document.getElementById("sign-offline"),
  error: document.getElementById("sign-error"),
  updatedAt: document.getElementById("updated-at"),
  today: document.getElementById("today"),
  clock: document.getElementById("clock"),
  networkDot: document.getElementById("network-dot"),
  networkLabel: document.getElementById("network-label"),
};

const state = {
  config: loadConfig(),
  items: null,
  updatedAt: null,
  lastFetchFailed: false,
  loading: false,
};

let refreshTimer = null;

function loadConfig() {
  try {
    const raw = window.localStorage.getItem(CONFIG_KEY);
    if (!raw) {
      return { apiUrl: "", token: "" };
    }
    const parsed = JSON.parse(raw);
    return {
      apiUrl: typeof parsed.apiUrl === "string" ? parsed.apiUrl : "",
      token: typeof parsed.token === "string" ? parsed.token : "",
    };
  } catch {
    return { apiUrl: "", token: "" };
  }
}

function saveConfig() {
  try {
    window.localStorage.setItem(CONFIG_KEY, JSON.stringify(state.config));
    return true;
  } catch {
    showSetupError("Este navegador no permite guardar la configuración del cartel.");
    return false;
  }
}

function hasConfig() {
  return Boolean(state.config.apiUrl && state.config.token);
}

function normalizeApiUrl(value) {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) {
    return "";
  }
  return /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`;
}

function setView(name) {
  elements.setupView.hidden = name !== "setup";
  elements.signView.hidden = name !== "sign";
}

function showSetupError(message) {
  elements.setupError.textContent = message;
  elements.setupError.hidden = !message;
}

function openSetup(message) {
  stopRefresh();
  elements.apiUrl.value = state.config.apiUrl;
  elements.deviceToken.value = state.config.token;
  elements.setupCancel.hidden = !hasConfig();
  showSetupError(message || "");
  setView("setup");
}

function closeSetup() {
  if (!hasConfig()) {
    return;
  }
  setView("sign");
  startRefresh();
}

function formatClock(date) {
  return date.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
}

function buildCard(item) {
  const card = document.createElement("li");
  card.className = `equipment-card ${
    item.status === "out_of_service" ? "out_of_service" : "maintenance"
  }`;

  const name = document.createElement("span");
  name.className = "equipment-name";
  name.textContent = item.name;
  card.append(name);

  if (item.location) {
    const location = document.createElement("span");
    location.className = "equipment-location";
    location.textContent = item.location;
    card.append(location);
  }

  const status = document.createElement("span");
  status.className = "equipment-status";
  status.textContent = item.status_label || "No disponible";
  card.append(status);

  return card;
}

function render() {
  const items = state.items || [];
  const stale = !navigator.onLine || state.lastFetchFailed;

  elements.loading.hidden = state.items !== null || state.lastFetchFailed;
  elements.error.hidden = !(state.lastFetchFailed && state.items === null);
  elements.offline.hidden = !(stale && state.items !== null);
  elements.list.hidden = items.length === 0;
  elements.empty.hidden = !(state.items !== null && items.length === 0);
  elements.list.replaceChildren(...items.map(buildCard));
  elements.updatedAt.textContent = state.updatedAt
    ? `Actualizado a las ${formatClock(state.updatedAt)}`
    : "Sin actualizar";
}

async function refreshEquipment() {
  if (!hasConfig() || state.loading || elements.signView.hidden) {
    return;
  }
  state.loading = true;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${state.config.apiUrl}/kiosk/equipment`, {
      headers: { "X-Kiosk-Token": state.config.token },
      signal: controller.signal,
    });

    if (response.status === 401) {
      state.config.token = "";
      saveConfig();
      state.items = null;
      state.updatedAt = null;
      state.lastFetchFailed = false;
      openSetup("El token del dispositivo no es válido o fue revocado. Captura uno nuevo.");
      return;
    }
    if (!response.ok) {
      throw new Error("status");
    }
    const payload = await response.json().catch(() => null);
    if (!payload || !Array.isArray(payload.items)) {
      throw new Error("payload");
    }
    state.items = payload.items;
    state.updatedAt = new Date();
    state.lastFetchFailed = false;
  } catch {
    state.lastFetchFailed = true;
  } finally {
    clearTimeout(timeout);
    state.loading = false;
    render();
  }
}

function startRefresh() {
  stopRefresh();
  void refreshEquipment();
  refreshTimer = setInterval(() => void refreshEquipment(), REFRESH_MS);
}

function stopRefresh() {
  if (refreshTimer !== null) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

function updateNetworkStatus() {
  const online = navigator.onLine;
  elements.networkDot.classList.toggle("offline", !online);
  elements.networkLabel.textContent = online ? "En línea" : "Sin conexión";
  if (!elements.signView.hidden) {
    render();
  }
}

function tickClock() {
  const now = new Date();
  elements.clock.dateTime = now.toISOString();
  elements.clock.textContent = formatClock(now);
  elements.today.dateTime = now.toISOString();
  const label = now.toLocaleDateString("es-MX", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  elements.today.textContent = label.charAt(0).toUpperCase() + label.slice(1);
}

async function handleSetupSubmit(event) {
  event.preventDefault();
  const apiUrl = normalizeApiUrl(elements.apiUrl.value);
  const token = elements.deviceToken.value.trim() || state.config.token;

  if (!apiUrl) {
    showSetupError("Escribe la dirección del servidor.");
    return;
  }
  try {
    new URL(apiUrl);
  } catch {
    showSetupError("La dirección del servidor no es válida.");
    return;
  }
  if (!token) {
    showSetupError("Captura el token del dispositivo que genera el panel.");
    return;
  }

  showSetupError("");
  const button = elements.setupForm.querySelector("button[type='submit']");
  button.disabled = true;
  button.textContent = "Probando conexión…";

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${apiUrl}/health`, { signal: controller.signal });
    if (!response.ok) {
      throw new Error("health");
    }
    const payload = await response.json();
    if (!payload || payload.status !== "ok") {
      throw new Error("health");
    }
  } catch {
    showSetupError(
      "No se pudo conectar. Revisa la dirección del servidor y que este dispositivo siga activo.",
    );
    return;
  } finally {
    clearTimeout(timeout);
    button.disabled = false;
    button.textContent = "Guardar y probar conexión";
  }

  state.config = { apiUrl, token };
  if (!saveConfig()) {
    return;
  }
  state.items = null;
  state.updatedAt = null;
  state.lastFetchFailed = false;
  setView("sign");
  startRefresh();
}

elements.setupForm.addEventListener("submit", (event) => void handleSetupSubmit(event));
elements.setupCancel.addEventListener("click", closeSetup);
elements.openSetup.addEventListener("click", () => openSetup(""));

window.addEventListener("online", () => {
  updateNetworkStatus();
  void refreshEquipment();
});
window.addEventListener("offline", updateNetworkStatus);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    void refreshEquipment();
  }
});

if (typeof navigator.serviceWorker === "object") {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js").catch(() => {
      // The sign keeps working without the offline shell cache.
    });
  });
}

tickClock();
setInterval(tickClock, 15000);
updateNetworkStatus();

if (hasConfig()) {
  setView("sign");
  startRefresh();
} else {
  openSetup(
    state.config.apiUrl
      ? "Falta el token del dispositivo. Captúralo para terminar la configuración."
      : "",
  );
}
