#!/usr/bin/env node
// Reference measurement for range_bench.mjs: real lookups on the demo site in headless Chromium.
//
//   node benchmarks/site_lookup.mjs [--site https://rcpir.github.io] [--chrome PATH] [TITLE ...]
//
// Opens the site, waits for the title index, then opens each TITLE (via location.hash, as a click does) and
// reports, from Resource Timing: the retrieval part (all /rc-pir/r/ range requests of the lookup: count, protocol,
// wall time from the first request start to the last response end), the compute POST, and the whole lookup
// (hash change until the article is shown).

import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, rmSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";

const argv = process.argv.slice(2);
let site = "https://rcpir.github.io", chrome = process.env.CHROME || null;
const titles = [];
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === "--site") site = argv[++i];
  else if (argv[i] === "--chrome") chrome = argv[++i];
  else titles.push(argv[i]);
}
if (!titles.length) titles.push("Albert Einstein", "Israel", "Python (programming language)", "World War II", "Moon");

function findChrome() {
  if (chrome) return chrome;
  const base = join(homedir(), ".cache/ms-playwright");
  for (const d of existsSync(base) ? readdirSync(base).sort().reverse() : []) {
    for (const rel of ["chrome-headless-shell-linux64/chrome-headless-shell", "chrome-linux/chrome", "chrome-linux64/chrome"]) {
      const p = join(base, d, rel);
      if (existsSync(p)) return p;
    }
  }
  throw new Error("no Chromium found: pass --chrome PATH or set $CHROME");
}

const sleep = (t) => new Promise((r) => setTimeout(r, t));
const dir = mkdtempSync(join(tmpdir(), "site-lookup-"));
const proc = spawn(findChrome(), ["--headless", "--no-sandbox", "--remote-debugging-port=0", `--user-data-dir=${dir}`,
                                  "--no-first-run", "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
const wsUrl = await new Promise((res, rej) => {
  let buf = "";
  proc.stderr.on("data", (d) => { buf += d; const m = /DevTools listening on (ws:\/\/\S+)/.exec(buf); if (m) res(m[1]); });
  proc.once("exit", (c) => rej(new Error(`chromium exited (${c}): ${buf}`)));
});
const http = new URL(wsUrl.replace("ws://", "http://")).origin;
const target = await (await fetch(`${http}/json/new?about:blank`, { method: "PUT" })).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const waiting = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && waiting.has(d.id)) { waiting.get(d.id)(d); waiting.delete(d.id); } };
const cdp = (method, params = {}) => new Promise((r) => { const i = ++id; waiting.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async (expr) => {
  const r = await cdp("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.result?.exceptionDetails) throw new Error(r.result.exceptionDetails.exception?.description ?? "page error");
  return r.result.result.value;
};

try {
  await cdp("Page.enable");
  const t0 = Date.now();
  await cdp("Page.navigate", { url: site + "/" });
  let ready = false;
  for (let i = 0; i < 600 && !ready; i++) {
    await sleep(100);
    ready = await evaluate(`!!document.getElementById("q") && !document.getElementById("q").disabled`).catch(() => false);
  }
  if (!ready) throw new Error("site did not finish loading the title index within 60 s");
  console.log(`site ${site} ready in ${Date.now() - t0} ms (params, title index, CDN warm-up started)`);
  await evaluate(`performance.setResourceTimingBufferSize(100000); 1`);
  await sleep(1500); // let the warm-up requests finish, as for a user who reads the home page first

  for (const title of titles) {
    const r = await evaluate(`(async () => {
      performance.clearResourceTimings();
      const t0 = performance.now();
      location.hash = encodeURIComponent(${JSON.stringify(title)});
      for (let i = 0; i < 600; i++) {
        await new Promise((r) => setTimeout(r, 20));
        const c = document.body.className;
        if (/article|error|fail/.test(c) && !/loading/.test(c)) break;
      }
      const total = performance.now() - t0;
      const ents = performance.getEntriesByType("resource");
      const cols = ents.filter((e) => e.name.includes("/rc-pir/r/"));
      const q = ents.filter((e) => e.name.endsWith("/rc-pir/query"));
      const proto = {}; cols.forEach((e) => (proto[e.nextHopProtocol] = (proto[e.nextHopProtocol] ?? 0) + 1));
      const start = Math.min(...cols.map((e) => e.startTime)), end = Math.max(...cols.map((e) => e.responseEnd));
      return { state: document.body.className, total, n: cols.length, proto,
               retrieval: end - start, firstStart: start - t0,
               ttfbMedian: cols.map((e) => e.responseStart - e.startTime).sort((a, b) => a - b)[cols.length >> 1],
               compute: q.length ? q[0].responseEnd - q[0].startTime : null };
    })()`);
    console.log(`"${title}": ${r.state} | lookup total ${r.total.toFixed(0)} ms | retrieval: ${r.n} range requests ` +
                `(${Object.entries(r.proto).map(([k, v]) => `${k} ${v}`).join(", ")}), wall ${r.retrieval.toFixed(0)} ms, ` +
                `ttfb median ${r.ttfbMedian?.toFixed(0)} ms, started ${r.firstStart.toFixed(0)} ms after the click | ` +
                `compute POST ${r.compute?.toFixed(0)} ms`);
  }
} finally {
  ws.close(); proc.kill(); setTimeout(() => rmSync(dir, { recursive: true, force: true }), 500);
}
