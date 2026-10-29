"use strict";

const CONFIG_KEY = "centrofit.kiosk.config.v1";
const REQUEST_TIMEOUT_MS = 10000;
const SUCCESS_RESET_MS = 7000;
const DENIED_RESET_MS = 5000;
const RATE_LIMIT_RESET_MS = 8000;
const EQUIPMENT_REFRESH_MS = 60000;

const elements = {
  setupView: document.getElementById("setup-view"),
  keypadView: document.getElementById("keypad-view"),
  resultView: document.getElementById("result-view"),
  setupForm: document.getElementById("setup-form"),
  apiUrl: document.getElementById("api-url"),
  deviceToken: document.getElementById("device-token"),
  setupError: document.getElementById("setup-error"),
  openSetup: document.getElementById("open-setup"),
  slots: Array.from(document.querySelectorAll("#code-display .slot")),
  keypad: document.querySelector(".keypad"),
  keypadMessage: document.getElementById("keypad-message"),
  resultMark: document.getElementById("result-mark"),
  resultTitle: document.getElementById("result-title"),
  resultMember: document.getElementById("result-member"),
  resultMessage: document.getElementById("result-message"),
  resultClose: document.getElementById("result-close"),
  deviceLabel: document.getElementById("device-label"),
  equipmentNotice: document.getElementById("equipment-notice"),
  equipmentList: document.getElementById("equipment-list"),
  clock: document.getElementById("clock"),
  networkDot: document.getElementById("network-dot"),
  networkLabel: document.getElementById("network-label"),
};

const state = {
  config: loadConfig(),
  digits: "",
  busy: false,
  resetTimer: null,
  submitTimer: null,
  equipment: [],
};

let equipmentTimer = null;

function loadConfig() {
  try {
    const raw = window.localStorage.getItem(CONFIG_KEY);
    if (!raw) {
      return { apiUrl: "", token: "", label: "Kiosco de recepción" };
    }
    const parsed = JSON.parse(raw);
    return {
      apiUrl: typeof parsed.apiUrl === "string" ? parsed.apiUrl : "",
      token: typeof parsed.token === "string" ? parsed.token : "",
      label: typeof parsed.label === "string" ? parsed.label : "Kiosco de recepción",
    };
  } catch {
    return { apiUrl: "", token: "", label: "Kiosco de recepción" };
  }
}

function saveConfig() {
  try {
    window.localStorage.setItem(CONFIG_KEY, JSON.stringify(state.config));
  } catch {
    showSetupError("Este navegador no permite guardar la configuración del kiosco.");
  }
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
  elements.keypadView.hidden = name !== "keypad";
  elements.resultView.hidden = name !== "result";
  if (name === "keypad") {
    renderDigits();
  }
}

function showSetupError(message) {
  elements.setupError.textContent = message;
  elements.setupError.hidden = !message;
}

function openSetup(message) {
  clearTimeout(state.resetTimer);
  state.busy = false;
  state.digits = "";
  elements.apiUrl.value = state.config.apiUrl;
  elements.deviceToken.value = state.config.token;
  showSetupError(message || "");
  elements.deviceLabel.textContent = state.config.label;
  elements.equipmentNotice.hidden = true;
  setView("setup");
}

function backToKeypad() {
  clearTimeout(state.resetTimer);
  state.busy = false;
  state.digits = "";
  elements.keypadMessage.textContent = "";
  setView("keypad");
}

function renderDigits() {
  elements.slots.forEach((slot, index) => {
    const digit = state.digits[index];
    slot.textContent = digit || "";
    slot.classList.toggle("filled", Boolean(digit));
    slot.classList.toggle("active", !digit && index === state.digits.length);
  });
  elements.keypadMessage.textContent =
    state.digits.length === 0 ? "Esperando el código de seis dígitos." : "";
}

function pressDigit(digit) {
  if (state.busy || elements.keypadView.hidden || state.digits.length >= 6) {
    return;
  }
  state.digits += digit;
  renderDigits();
  if (state.digits.length === 6) {
    clearTimeout(state.submitTimer);
    state.submitTimer = setTimeout(() => void submitCode(), 150);
  }
}

function eraseDigit() {
  if (state.busy) {
    return;
  }
  state.digits = state.digits.slice(0, -1);
  renderDigits();
}

function clearDigits() {
  if (state.busy) {
    return;
  }
  state.digits = "";
  renderDigits();
}

function showResult(authorized, message, memberName, resetDelay) {
  clearTimeout(state.resetTimer);
  elements.resultView.classList.toggle("success", authorized);
  elements.resultView.classList.toggle("denied", !authorized);
  elements.resultMark.textContent = authorized ? "✓" : "✕";
  elements.resultTitle.textContent = authorized ? "Acceso concedido" : "Acceso denegado";
  elements.resultMember.textContent = memberName || "";
  elements.resultMember.hidden = !memberName;
  elements.resultMessage.textContent = message || "";
  state.digits = "";
  state.busy = false;
  setView("result");
  state.resetTimer = setTimeout(backToKeypad, resetDelay);
}

async function submitCode() {
  if (state.busy || state.digits.length !== 6) {
    return;
  }
  state.busy = true;
  elements.keypadMessage.textContent = "Validando…";

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${state.config.apiUrl}/kiosk/check-in`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Kiosk-Token": state.config.token,
      },
      body: JSON.stringify({ code: state.digits }),
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => null);

    if (response.status === 401) {
      state.config.token = "";
      saveConfig();
      openSetup("El token del kiosco no es válido, fue revocado o caducó. Captura uno nuevo.");
      return;
    }
    if (response.status === 429) {
      showResult(
        false,
        (payload && payload.detail) || "Demasiados intentos. Espera un minuto.",
        "",
        RATE_LIMIT_RESET_MS,
      );
      return;
    }
    if (!response.ok) {
      showResult(
        false,
        (payload && payload.detail) || "No se pudo validar el código. Intenta de nuevo.",
        "",
        DENIED_RESET_MS,
      );
      return;
    }

    if (payload && payload.reader_id) {
      state.config.label = payload.reader_id;
      saveConfig();
      elements.deviceLabel.textContent = payload.reader_id;
    }
    showResult(
      Boolean(payload && payload.authorized),
      (payload && payload.message) || "",
      (payload && payload.member_name) || "",
      payload && payload.authorized ? SUCCESS_RESET_MS : DENIED_RESET_MS,
    );
  } catch {
    showResult(
      false,
      "No se pudo conectar con el servidor. Avisa al personal del club.",
      "",
      DENIED_RESET_MS,
    );
  } finally {
    clearTimeout(timeout);
    state.busy = false;
  }
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
    showSetupError("Captura el token del kiosco que genera el panel.");
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
      "No se pudo conectar. Revisa la dirección del servidor y que este kiosco esté permitido.",
    );
    return;
  } finally {
    clearTimeout(timeout);
    button.disabled = false;
    button.textContent = "Guardar y probar conexión";
  }

  state.config = { apiUrl, token, label: state.config.label };
  saveConfig();
  elements.deviceLabel.textContent = state.config.label;
  backToKeypad();
  startEquipmentPolling();
}

function renderEquipmentNotices(items) {
  state.equipment = items;
  elements.equipmentList.replaceChildren();
  elements.equipmentNotice.hidden = items.length === 0;
  for (const item of items) {
    const row = document.createElement("li");
    const name = document.createElement("span");
    name.className = "equipment-name";
    name.textContent = item.location ? `${item.name} · ${item.location}` : item.name;
    const status = document.createElement("span");
    status.className = `equipment-status ${
      item.status === "out_of_service" ? "out_of_service" : "maintenance"
    }`;
    status.textContent = item.status_label || "No disponible";
    row.append(name, status);
    elements.equipmentList.append(row);
  }
}

async function refreshEquipmentNotices() {
  if (!state.config.apiUrl || !state.config.token) {
    return;
  }
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
      renderEquipmentNotices([]);
      if (!state.busy && state.digits.length === 0) {
        openSetup("El token del kiosco no es válido, fue revocado o caducó. Captura uno nuevo.");
      }
      return;
    }
    if (!response.ok) {
      return;
    }
    const payload = await response.json().catch(() => null);
    if (payload && Array.isArray(payload.items)) {
      renderEquipmentNotices(payload.items);
    }
  } catch {
    // The last known list stays on screen; check-in does not depend on it.
  } finally {
    clearTimeout(timeout);
  }
}

function startEquipmentPolling() {
  if (!state.config.apiUrl || !state.config.token) {
    return;
  }
  if (equipmentTimer !== null) {
    clearInterval(equipmentTimer);
  }
  void refreshEquipmentNotices();
  equipmentTimer = setInterval(() => void refreshEquipmentNotices(), EQUIPMENT_REFRESH_MS);
}

function setNetworkStatus() {
  const online = navigator.onLine;
  elements.networkDot.classList.toggle("offline", !online);
  elements.networkLabel.textContent = online ? "En línea" : "Sin conexión";
  if (!online) {
    elements.keypadMessage.textContent =
      "Sin conexión. El registro de entrada necesita el servidor.";
  } else {
    elements.keypadMessage.textContent = "";
  }
}

function tickClock() {
  const now = new Date();
  elements.clock.dateTime = now.toISOString();
  elements.clock.textContent = now.toLocaleTimeString("es-MX", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

elements.keypad.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) {
    return;
  }
  if (button.dataset.key) {
    pressDigit(button.dataset.key);
  } else if (button.dataset.action === "clear") {
    clearDigits();
  } else if (button.dataset.action === "back") {
    eraseDigit();
  }
});

elements.setupForm.addEventListener("submit", (event) => void handleSetupSubmit(event));
elements.openSetup.addEventListener("click", () => openSetup(""));
elements.resultClose.addEventListener("click", backToKeypad);

document.addEventListener("keydown", (event) => {
  if (event.target instanceof HTMLInputElement) {
    return;
  }
  if (!elements.setupView.hidden) {
    return;
  }
  if (/^\d$/.test(event.key)) {
    pressDigit(event.key);
  } else if (event.key === "Backspace") {
    eraseDigit();
  } else if (event.key === "Escape") {
    clearDigits();
  } else if (event.key === "Enter" && !elements.resultView.hidden) {
    backToKeypad();
  }
});

window.addEventListener("online", () => {
  setNetworkStatus();
  void refreshEquipmentNotices();
});
window.addEventListener("offline", setNetworkStatus);

if (typeof navigator.serviceWorker === "object") {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js").catch(() => {
      // The kiosk keeps working without the offline shell cache.
    });
  });
}

tickClock();
setInterval(tickClock, 15000);
setNetworkStatus();
elements.deviceLabel.textContent = state.config.label;

if (state.config.apiUrl && state.config.token) {
  backToKeypad();
  startEquipmentPolling();
} else {
  openSetup(
    state.config.apiUrl
      ? "Falta el token del kiosco. Captúralo para terminar la configuración."
      : "",
  );
}
