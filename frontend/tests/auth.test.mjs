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
