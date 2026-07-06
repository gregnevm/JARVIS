// JARVIS Chrome Bridge — service worker.
// Опитує сервер (/api/v1/chrome/poll), виконує команду в активній вкладці,
// повертає результат (/api/v1/chrome/result). Конфіг (server URL + token) у storage.

const POLL_MS = 1500;

function normalizeServer(u) {
  return (u || "").replace(/\/$/, "");
}

async function cfg() {
  const s = await chrome.storage.local.get(["server", "token"]);
  return { server: normalizeServer(s.server), token: s.token || "" };
}

function authHeaders(token) {
  return token ? { "Authorization": "Bearer " + token } : {};
}

// Результат вважається невдалим, якщо це рядок-маркер помилки/відсутності елемента.
function isFailure(result) {
  return typeof result === "string" &&
    (result.startsWith("err:") || result === "no-element" || result === "noop");
}

async function poll() {
  const { server, token } = await cfg();
  if (!server) return;
  try {
    const r = await fetch(server + "/api/v1/chrome/poll", { headers: authHeaders(token) });
    if (!r.ok) return;
    const cmd = await r.json();
    if (!cmd || !cmd.action) return;
    const result = await execute(cmd);
    await fetch(server + "/api/v1/chrome/result", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders(token) },
      body: JSON.stringify({ id: cmd.id, ok: !isFailure(result), result })
    });
  } catch (e) { /* мережа недоступна — наступний тік */ }
}

async function activeTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

// Виконує команду в активній вкладці. Дії: navigate/location/read/schema/click/fill/eval.
// location/schema/fill — CSP-safe (без eval), працюють навіть коли сторінка блокує eval.
async function execute(cmd) {
  if (cmd.action === "navigate" && cmd.url) {
    const tab = await activeTab();
    await chrome.tabs.update(tab.id, { url: cmd.url });
    return { navigated: cmd.url };
  }
  const tab = await activeTab();
  const [out] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    args: [cmd],
    func: (c) => {
      try {
        if (c.action === "location") return location.href;
        if (c.action === "read") return document.body ? document.body.innerText.slice(0, 8000) : "";
        if (c.action === "schema") {
          // Жива схема форми (input/select/textarea) → JSON-рядок. Годує erp_sa.map.
          const els = Array.from(document.querySelectorAll("input,select,textarea"))
            .filter((e) => e.type !== "hidden");
          return JSON.stringify(els.map((e) => {
            let l = "";
            if (e.id) { const lb = document.querySelector('label[for="' + e.id + '"]'); if (lb) l = lb.innerText; }
            if (!l && e.closest("label")) l = e.closest("label").innerText;
            return {
              selector: e.id ? ("#" + e.id) : (e.name ? ('[name="' + e.name + '"]') : e.tagName.toLowerCase()),
              name: e.name || "", id: e.id || "", label: (l || e.placeholder || "").trim(),
              type: (e.type || e.tagName.toLowerCase())
            };
          }));
        }
        if (c.action === "click" && c.selector) { document.querySelector(c.selector)?.click(); return "clicked"; }
        if (c.action === "fill" && c.selector) {
          const el = document.querySelector(c.selector);
          if (!el) return "no-element";
          el.focus();
          // React-стійке присвоєння: нативний value-сеттер, щоб фреймворк побачив зміну.
          const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
            : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
          const desc = Object.getOwnPropertyDescriptor(proto, "value");
          if (desc && desc.set) { desc.set.call(el, c.value || ""); } else { el.value = c.value || ""; }
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
          el.blur();
          return "filled";
        }
        if (c.action === "eval" && c.script) {
          const v = eval(c.script);
          return (typeof v === "string") ? v : JSON.stringify(v);
        }
        return "noop";
      } catch (e) { return "err: " + e.message; }
    }
  });
  return out ? out.result : null;
}

// --- MV3 keepalive -----------------------------------------------------------
// setInterval сам по собі НЕ переживає присипляння service worker (~30с idle) —
// поллінг би гинув. Тримаємо воркер живим двома механізмами:
//   1) chrome.alarms — зовнішнє пробудження (навіть якщо воркер убитий), кожні 30с;
//   2) keepalive — періодичний виклик chrome-API скидає 30с idle-таймер, поки воркер живий.
// При рестарті воркера цей файл переоцінюється → ensureLoops() самовідновлює цикли.
const KEEPALIVE_MS = 20000;
let pollTimer = null;
let keepAliveTimer = null;

function ensureLoops() {
  if (pollTimer === null) { pollTimer = setInterval(poll, POLL_MS); poll(); }
  if (keepAliveTimer === null) {
    keepAliveTimer = setInterval(() => { chrome.runtime.getPlatformInfo(() => {}); }, KEEPALIVE_MS);
  }
}

// Бутстрап лише в service worker (chrome є). У node-тестах (R5.3) таймери/алярми не стартують.
if (typeof chrome !== "undefined" && chrome.storage) {
  chrome.alarms.create("jarvis-bridge-keepalive", { periodInMinutes: 0.5 });
  chrome.alarms.onAlarm.addListener((a) => { if (a.name === "jarvis-bridge-keepalive") ensureLoops(); });
  chrome.runtime.onStartup.addListener(ensureLoops);
  chrome.runtime.onInstalled.addListener(ensureLoops);
  ensureLoops();
}

// Node-тести (R5.3 smoke): у Chrome service worker `module` не існує — гілка мертва в проді.
if (typeof module !== "undefined") {
  module.exports = { authHeaders, normalizeServer };
}
