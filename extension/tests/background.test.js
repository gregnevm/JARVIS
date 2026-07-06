// R5.3 «Тонкий шлюз» — smoke чистих хелперів service worker-а.
// node:test (вбудований) — нуль залежностей, без jest/npm install.
// background.js у node не стартує таймери (guard на typeof chrome).
const test = require("node:test");
const assert = require("node:assert");

const { authHeaders, normalizeServer } = require("../background.js");

test("authHeaders: з токеном — Bearer", () => {
  assert.deepStrictEqual(authHeaders("abc"), { "Authorization": "Bearer abc" });
});

test("authHeaders: без токена — порожній обʼєкт (жодного Authorization)", () => {
  assert.deepStrictEqual(authHeaders(""), {});
  assert.deepStrictEqual(authHeaders(undefined), {});
});

test("normalizeServer: зрізає хвостовий слеш, толерантний до порожнього", () => {
  assert.strictEqual(normalizeServer("http://127.0.0.1:8000/"), "http://127.0.0.1:8000");
  assert.strictEqual(normalizeServer("http://127.0.0.1:8000"), "http://127.0.0.1:8000");
  assert.strictEqual(normalizeServer(""), "");
  assert.strictEqual(normalizeServer(undefined), "");
});
