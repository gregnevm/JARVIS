// JARVIS Chrome Bridge — service worker.
// Опитує сервер (/api/v1/chrome/poll), виконує команду в активній вкладці,
// повертає результат (/api/v1/chrome/result). Конфіг (server URL + token) у storage.

const POLL_MS = 1500;

async function cfg() {
  const s = await chrome.storage.local.get(["server", "token"]);
  return { server: (s.server || "").replace(/\/$/, ""), token: s.token || "" };
}

function authHeaders(token) {
  return token ? { "Authorization": "Bearer " + token } : {};
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
      body: JSON.stringify({ id: cmd.id, ok: true, result })
    });
  } catch (e) { /* мережа недоступна — наступний тік */ }
}

async function activeTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

// Виконує команду в браузері. Підтримка: navigate/read/click/fill/eval.
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
        if (c.action === "read") return document.body ? document.body.innerText.slice(0, 8000) : "";
        if (c.action === "click" && c.selector) { document.querySelector(c.selector)?.click(); return "clicked"; }
        if (c.action === "fill" && c.selector) {
          const el = document.querySelector(c.selector);
          if (el) { el.value = c.value || ""; el.dispatchEvent(new Event("input", { bubbles: true })); }
          return "filled";
        }
        if (c.action === "eval" && c.script) { return String(eval(c.script)); }
        return "noop";
      } catch (e) { return "err: " + e.message; }
    }
  });
  return out ? out.result : null;
}

setInterval(poll, POLL_MS);
poll();
