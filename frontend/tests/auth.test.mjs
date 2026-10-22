import assert from "node:assert/strict";
import { test } from "node:test";
import { createApiClient } from "../src/api.ts";

test("requests use fresh bearer tokens and do not rely on browser cookies", async (t) => {
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push({ url, options });
    return Response.json({ documents: [] });
  });
  let token = "session-one";
  const api = createApiClient(async () => token, "https://api.example");
  await api.getDocuments();
  token = "session-refreshed";
  await api.getDocuments();
  assert.equal(requests[0].options.headers.get("Authorization"), "Bearer session-one");
  assert.equal(requests[1].options.headers.get("Authorization"), "Bearer session-refreshed");
  assert.equal(requests[0].options.credentials, "omit");
});

test("a missing session prevents the request from being sent", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", () =>
    assert.fail("Must not send an unsigned request"),
  );
  const api = createApiClient(async () => null);
  await assert.rejects(api.getDocuments(), /session has ended/);
  assert.equal(fetch.mock.callCount(), 0);
});

test("uploads and downloads both carry authentication", async (t) => {
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push({ url, options });
    return url.endsWith("/download")
      ? new Response("file contents", { headers: { "Content-Type": "text/markdown" } })
      : Response.json({ id: "document" });
  });
  const api = createApiClient(async () => "session-test");
  await api.uploadDocument(new File(["# SOP"], "policy.md"));
  const file = await api.downloadDocument("document");
  assert.equal(requests[0].options.headers.get("Authorization"), "Bearer session-test");
  assert.equal(requests[0].options.headers.has("Content-Type"), false);
  assert.equal(requests[1].options.headers.get("Authorization"), "Bearer session-test");
  assert.equal(await file.text(), "file contents");
});

test("unmount can abort in-flight requests", async (t) => {
  t.mock.method(
    globalThis,
    "fetch",
    (url, options) =>
      new Promise((resolve, reject) => {
        options.signal.addEventListener("abort", () =>
          reject(new DOMException("Aborted", "AbortError")),
        );
      }),
  );
  const api = createApiClient(async () => "session-test");
  const request = api.getDocuments();
  const rejected = assert.rejects(request, { name: "AbortError" });
  await new Promise((resolve) => setImmediate(resolve));
  api.abortRequests();
  await rejected;
});

test("signed-out Studio links yield the hash to Clerk and preserve a local return path", async () => {
  const { prepareAuthRoute, clearAuthReturn } = await import("../src/authReturn.ts");
  const values = new Map(),
    replacements = [];
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  const history = { replaceState: (_state, _title, path) => replacements.push(path) };
  const hash = "#/studio/runs/0123456789abcdef0123456789abcdef";
  assert.equal(
    prepareAuthRoute({ hash, pathname: "/", search: "?source=link" }, history, storage, "app-one"),
    `/${hash}`,
  );
  assert.deepEqual(replacements, ["/?source=link"]);
  assert.equal(
    prepareAuthRoute(
      { hash: "#/verify-email-address", pathname: "/sign-up", search: "" },
      history,
      storage,
      "app-one",
    ),
    `/${hash}`,
  );
  assert.equal(
    prepareAuthRoute({ hash: "", pathname: "/", search: "" }, history, storage, "other-app"),
    "/",
  );
  clearAuthReturn(storage, "app-one");
  assert.equal(
    prepareAuthRoute({ hash: "", pathname: "/", search: "" }, history, storage, "app-one"),
    "/",
  );
});

test("auth return paths cannot redirect to external sites or unapproved app routes", async () => {
  const { prepareAuthRoute } = await import("../src/authReturn.ts");
  const history = { replaceState: () => {} };
  for (const value of [
    "https://attacker.example",
    "//attacker.example",
    "/api/studio/bots",
    "/#/studio//attacker.example",
  ]) {
    assert.equal(
      prepareAuthRoute(
        { hash: "", pathname: "/", search: "" },
        history,
        { getItem: () => value, setItem: () => {}, removeItem: () => {} },
        "scope",
      ),
      "/",
    );
  }
  assert.equal(
    prepareAuthRoute(
      { hash: "#/studio/invalid", pathname: "/", search: "" },
      history,
      null,
      "scope",
    ),
    "/#/studio",
  );
});

test("Studio sign-in handoff works when browser storage is unavailable", async () => {
  const { prepareAuthRoute } = await import("../src/authReturn.ts");
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
  assert.equal(
    prepareAuthRoute(
      { hash: "#/studio", pathname: "/", search: "" },
      { replaceState: () => {} },
      storage,
      "scope",
    ),
    "/#/studio",
  );
  assert.equal(
    prepareAuthRoute(
      { hash: "", pathname: "/", search: "" },
      { replaceState: () => {} },
      storage,
      "scope",
    ),
    "/",
  );
});

test("Connections deep links return to the same approved Studio page after sign-in", async () => {
  const { prepareAuthRoute } = await import("../src/authReturn.ts");
  assert.equal(
    prepareAuthRoute(
      { hash: "#/studio/connections", pathname: "/", search: "" },
      { replaceState: () => {} },
      null,
      "app",
    ),
    "/#/studio/connections",
  );
});
