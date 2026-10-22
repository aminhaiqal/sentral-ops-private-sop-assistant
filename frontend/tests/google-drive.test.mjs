import assert from "node:assert/strict";
import { test } from "node:test";
import { createApiClient } from "../src/api.ts";
import {
  googleAuthorizationUrl,
  pendingGoogleAuth,
  saveGoogleAuth,
} from "../src/connections/googleAuth.ts";

test("Drive authorization only navigates to the exact Google HTTPS endpoint", () => {
  const url = "https://accounts.google.com/o/oauth2/v2/auth?state=test";
  assert.equal(googleAuthorizationUrl(url), url);
  for (const invalid of [
    "http://accounts.google.com/o/oauth2/v2/auth",
    "https://accounts.google.com.evil.example/o/oauth2/v2/auth",
    "https://accounts.google.com@evil.example/o/oauth2/v2/auth",
    "https://user:password@accounts.google.com/o/oauth2/v2/auth",
    "https://accounts.google.com:8443/o/oauth2/v2/auth",
    "https://accounts.google.com/other",
    "javascript:alert(1)",
    "//accounts.google.com/o/oauth2/v2/auth",
  ])
    assert.throws(() => googleAuthorizationUrl(invalid));
});

test("only unexpired opaque Drive attempts resume for their account", () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  const now = 1000000;
  const pending = { flow_id: "a".repeat(32), expires_at: now + 600000 };
  saveGoogleAuth(storage, "owner", pending);
  assert.deepEqual(pendingGoogleAuth(storage, "owner", now), pending);
  assert.equal(pendingGoogleAuth(storage, "stranger", now), null);
  assert.equal(pendingGoogleAuth(storage, "owner", pending.expires_at), null);
  saveGoogleAuth(storage, "owner", null);
  assert.equal(pendingGoogleAuth(storage, "owner", now), null);
  for (const invalid of [
    "malformed",
    JSON.stringify({ ...pending, flow_id: "not-an-attempt" }),
    JSON.stringify({ ...pending, expires_at: now + 600001 }),
    JSON.stringify({ ...pending, expires_at: "Infinity" }),
    "null",
  ])
    assert.equal(pendingGoogleAuth({ getItem: () => invalid }, "owner", now), null);
});

test("disabled browser storage does not interrupt Google authorization", () => {
  const storage = {
    getItem: () => {
      throw Error("disabled");
    },
    setItem: () => {
      throw Error("disabled");
    },
    removeItem: () => {
      throw Error("disabled");
    },
  };
  assert.equal(pendingGoogleAuth(storage, "owner"), null);
  assert.doesNotThrow(() => saveGoogleAuth(storage, "owner", null));
  assert.doesNotThrow(() =>
    saveGoogleAuth(storage, "owner", { flow_id: "a".repeat(32), expires_at: Date.now() + 600000 }),
  );
});

test("only authorization start includes its browser-binding cookie; every call needs Clerk", async (t) => {
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push({ url, options });
    return Response.json({});
  });
  const api = createApiClient(async () => "clerk-session");
  await api.connectGoogleDrive();
  await api.googleDriveAuthStatus("a".repeat(32));
  await api.completeGoogleDriveAuth("a".repeat(32));
  await api.cancelGoogleDriveAuth("a".repeat(32));
  assert.deepEqual(
    requests.map(({ options }) => options.credentials),
    ["include", "omit", "omit", "omit"],
  );
  for (const { options } of requests)
    assert.equal(options.headers.get("Authorization"), "Bearer clerk-session");
});
