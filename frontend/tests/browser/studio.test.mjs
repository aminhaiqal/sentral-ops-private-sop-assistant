import assert from "node:assert/strict";
import { test } from "node:test";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, readFile, rm, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { createServer } from "node:net";
import { resolve, join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { chromium } from "playwright";

async function freePort() {
  const server = createServer();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  return port;
}
async function ready(url, child, logs) {
  for (let attempt = 0; attempt < 150; attempt++) {
    if (child.exitCode !== null) throw Error(`Test server exited: ${logs()}`);
    try {
      if ((await fetch(url)).ok) return;
    } catch {}
    await delay(100);
  }
  throw Error(`Test server did not start: ${logs()}`);
}
async function stop(child) {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([once(child, "exit"), delay(3000)]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

test(
  "Studio: create, run, inspect, reopen, edit, isolate accounts, mobile, delete",
  { timeout: 90000 },
  async (t) => {
    const root = resolve(import.meta.dirname, "../../.."),
      frontend = join(root, "frontend");
    const state = await mkdtemp(join(tmpdir(), "axelyn-studio-browser-"));
    const [apiPort, webPort] = await Promise.all([freePort(), freePort()]);
    const origin = `http://127.0.0.1:${webPort}`,
      apiUrl = `http://127.0.0.1:${apiPort}`;
    let logs = "";
    const api = spawn(
      process.env.STUDIO_TEST_PYTHON || join(root, "backend/.venv/bin/python"),
      [
        join(root, "backend/tests/studio_browser_server.py"),
        "--port",
        String(apiPort),
        "--frontend-origin",
        origin,
        "--state-dir",
        state,
      ],
      {
        cwd: join(root, "backend"),
        env: { ...process.env, PYTHONPATH: join(root, "backend") },
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    const vite = spawn(
      process.execPath,
      [
        join(frontend, "node_modules/vite/bin/vite.js"),
        "--host",
        "127.0.0.1",
        "--port",
        String(webPort),
        "--strictPort",
      ],
      { cwd: frontend, stdio: ["ignore", "pipe", "pipe"] },
    );
    for (const child of [api, vite]) {
      child.stdout.on("data", (data) => {
        logs = (logs + data).slice(-12000);
      });
      child.stderr.on("data", (data) => {
        logs = (logs + data).slice(-12000);
      });
    }
    t.after(async () => {
      await Promise.all([stop(api), stop(vite)]);
      await rm(state, { recursive: true, force: true });
    });
    await Promise.all([
      ready(`${apiUrl}/api/health`, api, () => logs),
      ready(origin, vite, () => logs),
    ]);
    const token = await readFile(join(state, "owner.token"), "utf8"),
      strangerToken = await readFile(join(state, "stranger.token"), "utf8");
    const main = await (await fetch(`${origin}/src/main.tsx`)).text();
    const react = main.match(/"([^"\n]*\/react\.js\?[^"\n]*)"/)[1],
      reactDom = main.match(/"([^"\n]*\/react-dom_client\.js\?[^"\n]*)"/)[1];
    const browser = await chromium.launch();
    t.after(() => browser.close());
    const errors = [];
    async function pageFor(userToken, viewport = { width: 1440, height: 1000 }) {
      const context = await browser.newContext({ viewport });
      await context.route("**/src/main.tsx*", (route) =>
        route.fulfill({
          contentType: "application/javascript",
          body: `import React from ${JSON.stringify(react)};import ReactDOM from ${JSON.stringify(reactDom)};import App from '/src/App.tsx';import {createApiClient} from '/src/api.ts';import '/src/styles.css';ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App,{api:createApiClient(async()=>${JSON.stringify(userToken)},${JSON.stringify(apiUrl)}),storageScope:'isolated-browser-test',accountMenu:React.createElement('span',{'aria-label':'Test account'},'AH')}));`,
        }),
      );
      const page = await context.newPage();
      page.setDefaultTimeout(15000);
      page.on("pageerror", (error) => errors.push(String(error)));
      return { context, page };
    }
    async function screenshot(page, name) {
      if (process.env.STUDIO_SCREENSHOT_DIR) {
        await mkdir(process.env.STUDIO_SCREENSHOT_DIR, { recursive: true });
        await page.screenshot({
          path: join(process.env.STUDIO_SCREENSHOT_DIR, `${name}.png`),
          fullPage: false,
        });
      }
    }
    const { context, page } = await pageFor(token);
    await page.goto(`${origin}/#/studio`, { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Your first lead researcher" }).waitFor();
    await screenshot(page, "studio-empty-desktop");
    await page.getByRole("button", { name: "Create bot", exact: true }).click();
    await page
      .getByLabel("Objective", { exact: true })
      .fill("Find industrial automation companies for our operations software.");
    await page.getByLabel("Target industry", { exact: true }).fill("Industrial automation");
    await page.getByLabel("Location", { exact: true }).fill("Kuala Lumpur");
    await page
      .getByLabel("Qualification criteria", { exact: true })
      .fill("Offers industrial automation services in Kuala Lumpur.");
    await page
      .getByLabel("Your offering", { exact: true })
      .fill("Operations software for industrial service companies.");
    await screenshot(page, "studio-form-desktop");
    await page.getByRole("button", { name: "Create bot", exact: true }).click();
    await page.getByRole("heading", { name: "Lead Research Bot", exact: true }).waitFor();
    await page.getByRole("button", { name: "Run bot", exact: true }).click();
    await page.getByRole("heading", { name: "Research results", exact: true }).waitFor();
    await page.getByRole("heading", { name: "Acme Engineering", exact: true }).waitFor();
    await page.getByText("Minimum result count met", { exact: true }).waitFor();
    assert.equal(await page.locator(".studio-prospect").count(), 1);
    assert.ok(
      await page
        .locator(".studio-outreach-draft")
        .innerText()
        .then((text) => text.includes("NOT SENT")),
    );
    await screenshot(page, "studio-results-desktop");
    const resultUrl = page.url(),
      runId = resultUrl.split("/").pop();
    await page.getByRole("button", { name: /Analyze.*completed/i }).click();
    await page.getByRole("heading", { name: "Analyze step", exact: true }).waitFor();
    await page.getByText("Output · validated structured data", { exact: true }).click();
    assert.ok((await page.locator(".studio-step-details").innerText()).includes("evidence_quote"));
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Acme Engineering", exact: true }).waitFor();
    await page
      .getByRole("navigation", { name: "Studio navigation" })
      .getByRole("button", { name: "Bot library", exact: true })
      .click();
    await page.getByRole("button", { name: "Edit Lead Research Bot", exact: true }).waitFor();
    await screenshot(page, "studio-library-desktop");
    await page.getByRole("button", { name: "Edit Lead Research Bot", exact: true }).click();
    await page.getByLabel("Bot name", { exact: true }).fill("KL Lead Research");
    await page.getByLabel("Draft optional skill", { exact: true }).uncheck();
    await page.getByRole("button", { name: "Save changes", exact: true }).click();
    await page.getByRole("heading", { name: "KL Lead Research", exact: true }).waitFor();
    await page.getByRole("button", { name: "Run bot", exact: true }).click();
    await page.getByRole("heading", { name: "Research results", exact: true }).waitFor();
    assert.equal(await page.locator(".studio-outreach-draft").count(), 0);
    assert.equal(await page.locator(".studio-step").count(), 3);
    const unauthorized = await fetch(`${apiUrl}/api/studio/runs/${runId}`, {
      headers: { Authorization: `Bearer ${strangerToken}` },
    });
    assert.equal(unauthorized.status, 404);
    const other = await pageFor(strangerToken);
    await other.page.goto(`${origin}/#/studio`, { waitUntil: "domcontentloaded" });
    await other.page.getByRole("heading", { name: "Your first lead researcher" }).waitFor();
    await other.context.close();
    const mobile = await pageFor(token, { width: 375, height: 812 });
    await mobile.page.goto(resultUrl, { waitUntil: "domcontentloaded" });
    await mobile.page.getByRole("heading", { name: "Acme Engineering", exact: true }).waitFor();
    assert.equal(
      await mobile.page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      false,
    );
    await screenshot(mobile.page, "studio-results-mobile");
    await mobile.page
      .getByRole("navigation", { name: "Studio navigation" })
      .getByRole("button", { name: "Bot library", exact: true })
      .click();
    await mobile.page.getByRole("button", { name: "Edit KL Lead Research", exact: true }).click();
    await mobile.page.getByLabel("Objective", { exact: true }).waitFor();
    assert.equal(
      await mobile.page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      false,
    );
    await screenshot(mobile.page, "studio-form-mobile");
    await mobile.context.close();
    await page
      .getByRole("navigation", { name: "Studio navigation" })
      .getByRole("button", { name: "Bot library", exact: true })
      .click();
    await page.getByRole("button", { name: "Delete KL Lead Research", exact: true }).click();
    await page.getByRole("button", { name: "Delete bot", exact: true }).click();
    await page.getByRole("heading", { name: "Your first lead researcher" }).waitFor();
    await page.goto(resultUrl, { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Acme Engineering", exact: true }).waitFor();
    await writeFile(join(state, "disable-search"), "test-only provider configuration toggle");
    await delay(250);
    await page.goto(`${origin}/#/studio`, { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "Create bot", exact: true }).click();
    await page.getByLabel("Bot name", { exact: true }).fill("Missing Search Connection");
    await page
      .getByLabel("Objective", { exact: true })
      .fill("Research industrial automation companies and save qualified results.");
    await page.getByLabel("Target industry", { exact: true }).fill("Industrial automation");
    await page.getByLabel("Location", { exact: true }).fill("Kuala Lumpur");
    await page
      .getByLabel("Qualification criteria", { exact: true })
      .fill("Offers industrial automation services.");
    await page
      .getByLabel("Your offering", { exact: true })
      .fill("Operations software for service companies.");
    await page.getByRole("button", { name: "Create bot", exact: true }).click();
    await page.getByRole("button", { name: "Run bot", exact: true }).click();
    await page.getByRole("heading", { name: "No results saved", exact: true }).waitFor();
    await page.getByText("configuration error", { exact: true }).waitFor();
    assert.ok(
      (await page.locator(".studio-run-error").innerText()).includes("BRAVE_SEARCH_API_KEY"),
    );
    const failedRunId = page.url().split("/").pop();
    const failed = await (
      await fetch(`${apiUrl}/api/studio/runs/${failedRunId}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
    ).json();
    assert.equal(failed.usage.api_calls, 0);
    await screenshot(page, "studio-configuration-error");
    assert.deepEqual(errors, []);
    await context.close();
  },
);
