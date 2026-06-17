// Конфіг моста: server URL + JWT-токен у chrome.storage.
const $ = (id) => document.getElementById(id);

chrome.storage.local.get(["server", "token"], (s) => {
  $("server").value = s.server || "";
  $("token").value = s.token || "";
});

$("save").addEventListener("click", () => {
  chrome.storage.local.set(
    { server: $("server").value.trim(), token: $("token").value.trim() },
    () => { $("status").textContent = "Збережено ✓"; }
  );
});
