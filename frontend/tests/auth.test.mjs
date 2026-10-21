import assert from "node:assert/strict";
import { test } from "node:test";
import { createApiClient } from "../src/api.ts";
import { readChats, saveChats } from "../src/chats.ts";

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

test("chat history stays scoped to the account and does not import anonymous history", (t) => {
  const values = new Map([
    ["sentral.chats.v1", JSON.stringify([{ id: "anonymous", messages: [] }])],
  ]);
  const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
    },
  });
  t.after(() => {
    if (original) Object.defineProperty(globalThis, "localStorage", original);
    else delete globalThis.localStorage;
  });
  assert.deepEqual(readChats("user-a"), []);
  const chat = { id: "chat-a", title: "Private question", messages: [], updatedAt: 1 };
  saveChats("user-a", [chat]);
  assert.deepEqual(readChats("user-b"), []);
  assert.equal(readChats("user-a")[0].id, "chat-a");
});
