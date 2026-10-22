import assert from "node:assert/strict";
import { test } from "node:test";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir, readFile } from "node:fs/promises";
import { createServer } from "node:net";
import { resolve, join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { chromium } from "playwright";

test(
  "one task flow: submit, inspect, download, upload, resume, retry, stop, and reopen",
  { timeout: 60000 },
  async (t) => {
    const frontend = resolve(import.meta.dirname, "../..");
    const server = createServer();
    server.listen(0, "127.0.0.1");
    await once(server, "listening");
    const port = server.address().port;
    await new Promise((resolve) => server.close(resolve));
    const origin = `http://127.0.0.1:${port}`;
    let logs = "";
    const vite = spawn(
      process.execPath,
      [
        join(frontend, "node_modules/vite/bin/vite.js"),
        "--host",
        "127.0.0.1",
        "--port",
        String(port),
        "--strictPort",
      ],
      { cwd: frontend, stdio: ["ignore", "pipe", "pipe"] },
    );
    for (const stream of [vite.stdout, vite.stderr])
      stream.on("data", (data) => {
        logs = (logs + data).slice(-5000);
      });
    t.after(async () => {
      vite.kill("SIGTERM");
      await Promise.race([once(vite, "exit"), delay(2000)]);
      if (vite.exitCode === null) vite.kill("SIGKILL");
    });
    let ready = false;
    for (let i = 0; i < 100; i++) {
      if (vite.exitCode !== null) throw Error(logs);
      try {
        ready = (await fetch(origin)).ok;
      } catch {}
      if (ready) break;
      await delay(100);
    }
    assert.ok(ready, logs);
    const main = await (await fetch(`${origin}/src/main.tsx`)).text();
    const react = main.match(/"([^"\n]*\/react\.js\?[^"\n]*)"/)[1];
    const reactDom = main.match(/"([^"\n]*\/react-dom_client\.js\?[^"\n]*)"/)[1];
    const browser = await chromium.launch();
    t.after(() => browser.close());
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await context.route("**/src/main.tsx*", (route) =>
      route.fulfill({
        contentType: "application/javascript",
        body: `import React from ${JSON.stringify(react)};import ReactDOM from ${JSON.stringify(reactDom)};import App from '/src/App.tsx';import {createApiClient} from '/src/api.ts';import '/src/styles.css';ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App,{api:createApiClient(async()=>'test-session'),accountMenu:React.createElement('span',{'aria-label':'Test account'},'AH')}));`,
      }),
    );
    const tasks = [];
    const documents = [];
    const errors = [];
    const artifact = {
      id: "artifact",
      title: "Briefing",
      content: "# Briefing\n\nFollow the uploaded procedure. [S1]",
      sha256: "test",
    };
    const source = {
      document_id: "doc",
      chunk_id: "doc-1",
      title: "Procedure",
      score: 0.9,
      excerpt: "Check the report before submitting it.",
      citation: "S1",
    };
    const update = (task, values) =>
      Object.assign(task, values, { updated_at: new Date().toISOString() });
    await context.route("**/api/**", async (route) => {
      const request = route.request();
      assert.equal(request.headers().authorization, "Bearer test-session");
      const path = new URL(request.url()).pathname;
      const json = (value, status = 200) => route.fulfill({ status, json: value });
      if (path === "/api/tasks" && request.method() === "POST") {
        const body = request.postDataJSON();
        assert.deepEqual(Object.keys(body), ["goal"]);
        const now = new Date().toISOString();
        const task = {
          id: `task-${tasks.length + 1}`,
          goal: body.goal,
          status: tasks.length === 1 ? "needs_input" : "queued",
          completion_criteria: "Save a cited document",
          created_at: now,
          updated_at: now,
          summary: "",
          exception: tasks.length === 1 ? "Please upload the procedure." : "",
          turns: 0,
          tokens: 0,
          max_turns: 16,
          max_tokens: 32000,
          context: "",
          sources: [],
          artifacts: [],
          events: [],
        };
        tasks.unshift(task);
        return json(task, 202);
      }
      if (path === "/api/tasks") return json(tasks);
      const match = path.match(/^\/api\/tasks\/([^/]+)(?:\/(resume|cancel))?$/);
      if (match) {
        const task = tasks.find((item) => item.id === match[1]);
        if (match[2] === "cancel") update(task, { status: "cancelled" });
        if (match[2] === "resume") {
          assert.ok(request.postDataJSON().message);
          update(task, {
            status: task.status === "failed" ? "completed" : "queued",
            exception: "",
          });
        }
        return json(task);
      }
      if (path === "/api/documents" && request.method() === "POST") {
        assert.ok(request.postData().includes("Check the report"));
        const document = {
          id: "doc",
          filename: "procedure.md",
          title: "Procedure",
          size_bytes: 50,
          uploaded_at: new Date().toISOString(),
          status: "indexed",
          chunks: 1,
          pages: null,
          indexing_error: null,
        };
        documents.push(document);
        return json(document, 201);
      }
      if (path === "/api/documents") return json({ documents, storage_configured: true });
      assert.fail(`Unexpected endpoint: ${path}`);
    });
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(String(error)));
    page.setDefaultTimeout(12000);
    async function screenshot(name) {
      if (!process.env.WORKSPACE_SCREENSHOT_DIR) return;
      await mkdir(process.env.WORKSPACE_SCREENSHOT_DIR, { recursive: true });
      await page.screenshot({
        path: join(process.env.WORKSPACE_SCREENSHOT_DIR, `${name}.png`),
        fullPage: true,
      });
    }
    await page.goto(origin);
    await page.getByRole("heading", { name: "What needs doing?" }).waitFor();
    await screenshot("empty-desktop");
    assert.equal(await page.getByRole("button", { name: "Create a bot" }).count(), 0);
    await page.getByLabel("Describe your task").fill("Prepare a briefing");
    await page.getByRole("button", { name: "Create document", exact: true }).click();
    await page.getByRole("button", { name: "Stop", exact: true }).waitFor();
    update(tasks[0], {
      status: "completed",
      summary: "The briefing is ready.",
      sources: [source],
      artifacts: [artifact],
    });
    await page.getByRole("heading", { name: "Briefing", exact: true, level: 2 }).waitFor();
    await page.getByText("Sources · 1", { exact: true }).click();
    await page.getByText(source.excerpt).waitFor();
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download Briefing" }).click();
    const download = await downloadPromise;
    assert.equal(await readFile(await download.path(), "utf8"), artifact.content);
    await screenshot("result-desktop");
    await page.getByRole("button", { name: "New task" }).click();
    await page.getByLabel("Describe your task").fill("Prepare another document");
    await page.getByRole("button", { name: "Create document", exact: true }).click();
    await page.getByText("Please upload the procedure.").waitFor();
    await page.getByRole("button", { name: "Add documents" }).click();
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: /Click to upload or drop files/ }).click();
    await (
      await chooser
    ).setFiles({
      name: "procedure.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Procedure\n\nCheck the report before submitting it."),
    });
    await page.getByRole("button", { name: "procedure.md", exact: true }).waitFor();
    await page.keyboard.press("Escape");
    await page.getByLabel("Reply to the task").fill("Use the uploaded procedure.");
    await page.getByRole("button", { name: "Continue task" }).click();
    await page.getByRole("button", { name: "Stop", exact: true }).waitFor();
    update(tasks[0], { status: "failed", exception: "A temporary service failure." });
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await page.getByText("Done", { exact: true }).waitFor();
    await page.getByRole("button", { name: "New task" }).click();
    await page.getByLabel("Describe your task").fill("Prepare a long document");
    await page.getByRole("button", { name: "Create document", exact: true }).click();
    await page.getByRole("button", { name: "Stop", exact: true }).click();
    await page.getByText("Stopped", { exact: true }).waitFor();
    await page.reload();
    await page.getByRole("button", { name: "History", exact: true }).click();
    await page.getByRole("button", { name: /Prepare a briefing/ }).click();
    await page.getByRole("heading", { name: "Briefing", exact: true, level: 2 }).waitFor();
    await page.setViewportSize({ width: 375, height: 812 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await screenshot("result-mobile");
    await page.getByRole("button", { name: "New task" }).click();
    await screenshot("empty-mobile");
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(errors, []);
  },
);
