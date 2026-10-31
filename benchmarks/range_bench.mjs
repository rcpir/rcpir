#!/usr/bin/env node
// Retrieval-host benchmark: what one RC-PIR lookup costs on a static host, the way the browser client fetches.
//
//   node benchmarks/range_bench.mjs [options] URL [URL ...]
//
// URL ... are the objects (shards) a lookup reads from, all on the same origin (e.g. the shards of R). Flow, as in
// the client and the demo site:
//   1. Warm-up / size discovery: one 1-byte range request per URL (the demo site does exactly this at startup so
//      the CDN edge holds the shards). Skipped with --no-warm, which then needs --size.
//   2. --queries lookups, one after the other. Each picks --s distinct random columns of --len bytes, uniformly
//      over all columns of all URLs (like the client's S), and requests them all at once.
// Engines:
//   --engine node     Node's http2 module: one multiplexed HTTP/2 session per origin, as a browser does. Hosts
//                     without HTTP/2 get --h1-conns keep-alive HTTP/1.1 connections (a browser uses 6 per host).
//   --engine browser  Headless Chromium over the DevTools protocol, fetch() from a page on the hosts' origin
//                     (same-origin, so no CORS setup is needed). Real browser behaviour: HTTP/2 or HTTP/3, cache.
// Options:
//   --s N          ranges per lookup (default 88)          --len BYTES   range length (default 4096)
//   --queries N    lookups (default 5)                      --gap MS      pause between lookups (default 500)
//   --no-warm      skip step 1 (cold CDN); needs --size     --size BYTES  object size, if not discovered
//   --cache MODE   browser fetch cache mode: default (as the client) or no-store (default: default)
//   --h1-conns N   HTTP/1.1 connections for the node engine (default 6)
//   --page MODE    browser page: vendor (same-origin page on the host), local (127.0.0.1 page, cross-origin,
//                  needs CORS on the host, like a deployed client), auto (vendor if it works; default)
//   --chrome PATH  Chromium binary (default: $CHROME or Playwright's headless shell)
//   --json FILE    also write all per-request records as JSON
//   --header "Name: value"  extra request header, repeatable (node engine only; browsers forbid e.g. Cookie),
//                  e.g. a guest session cookie for a cloud drive
// Every response is checked: status 206, Content-Range of the requested range, body of exactly --len bytes. If a
// cross-origin page cannot read Content-Range (not in Access-Control-Expose-Headers), status and length are checked,
// as the client does, and object sizes must be given with --size.

import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, readdirSync, existsSync, writeFileSync } from "node:fs";
import http2 from "node:http2";
import { createServer } from "node:http";
import https from "node:https";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import tls from "node:tls";
import { randomInt } from "node:crypto";

// ---------------------------------------------------------------------------------------------- options
const argv = process.argv.slice(2);
const opt = { engine: "node", s: 88, len: 4096, queries: 5, gap: 500, warm: true, size: null, cache: "default",
              h1Conns: 6, page: "auto", chrome: process.env.CHROME || null, json: null, headers: {}, urls: [] };
for (let i = 0; i < argv.length; i++) {
  const a = argv[i], next = () => argv[++i];
  if (a === "--engine") opt.engine = next();
  else if (a === "--s") opt.s = +next();
  else if (a === "--len") opt.len = +next();
  else if (a === "--queries") opt.queries = +next();
  else if (a === "--gap") opt.gap = +next();
  else if (a === "--no-warm") opt.warm = false;
  else if (a === "--size") opt.size = +next();
  else if (a === "--cache") opt.cache = next();
  else if (a === "--h1-conns") opt.h1Conns = +next();
  else if (a === "--header") { const h = next(), k = h.indexOf(":"); opt.headers[h.slice(0, k).trim().toLowerCase()] = h.slice(k + 1).trim(); }
  else if (a === "--page") opt.page = next();
  else if (a === "--chrome") opt.chrome = next();
  else if (a === "--json") opt.json = next();
  else if (a.startsWith("--")) usage(`unknown option ${a}`);
  else opt.urls.push(a);
}
function usage(msg) {
  console.error(`${msg}\nusage: node benchmarks/range_bench.mjs [--engine node|browser] [--s 88] [--len 4096] ` +
    `[--queries 5] [--no-warm --size BYTES] URL [URL ...]`);
  process.exit(2);
}
if (!opt.urls.length) usage("no URL given");
if (!["node", "browser"].includes(opt.engine)) usage("--engine must be node or browser");
if (!["auto", "vendor", "local"].includes(opt.page)) usage("--page must be auto, vendor or local");
if (Object.keys(opt.headers).length && opt.engine !== "node") usage("--header works with --engine node only");
if (!opt.warm && !opt.size) usage("--no-warm needs --size (object sizes are discovered by the warm-up requests)");
const origins = [...new Set(opt.urls.map((u) => new URL(u).origin))];
if (origins.length > 1) usage(`all URLs must be on one origin (got ${origins.join(", ")})`);
const ORIGIN = origins[0];

// ---------------------------------------------------------------------------------------------- helpers
const pick = (h) => Object.fromEntries(["x-cache", "x-cache-hits", "cf-cache-status", "age", "x-served-by",
  "server", "via", "x-goog-storage-class", "cf-ray"].filter((k) => h[k] != null).map((k) => [k, String(h[k])]));
const pct = (v, q) => { const s = [...v].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(q * s.length))]; };
const ms = (x) => `${x.toFixed(0)} ms`;
const sleep = (t) => new Promise((r) => setTimeout(r, t));

/** Plan one lookup: s distinct random (url, offset) pairs, uniform over all columns of all objects. */
function plan(sizes) {
  const cols = opt.urls.map((u) => Math.floor(sizes[u] / opt.len));
  const total = cols.reduce((a, b) => a + b, 0);
  if (total < opt.s) throw new Error(`only ${total} columns of ${opt.len} bytes, fewer than s = ${opt.s}`);
  const chosen = new Set();
  while (chosen.size < opt.s) chosen.add(randomInt(total));
  return [...chosen].map((j) => {
    let k = 0;
    while (j >= cols[k]) j -= cols[k++];
    return { url: opt.urls[k], offset: j * opt.len };
  });
}

/** Check a range response the way the client does (fetchBytes in client/src/client.ts, plus Content-Range). */
function check(r, offset, len) {
  if (r.error) return r.error;
  if (r.status !== 206) return `status ${r.status}`;
  // A cross-origin browser fetch sees Content-Range only if the host lists it in Access-Control-Expose-Headers.
  // The client does not need it (it checks status and length), so then check what the client checks.
  if (r.contentRange == null) return r.bytes === len ? "ok" : `length ${r.bytes}`;
  const m = /^bytes (\d+)-(\d+)\/(\d+|\*)$/.exec(r.contentRange);
  if (!m || +m[1] !== offset || +m[2] !== offset + len - 1) return `content-range ${r.contentRange}`;
  if (r.bytes !== len) return `length ${r.bytes}`;
  return "ok";
}

// ---------------------------------------------------------------------------------------------- node engine
async function nodeEngine() {
  const u = new URL(ORIGIN);
  const t0 = performance.now();
  const socket = tls.connect({ host: u.hostname, port: u.port || 443, servername: u.hostname,
                               ALPNProtocols: ["h2", "http/1.1"] });
  await new Promise((res, rej) => { socket.once("secureConnect", res); socket.once("error", rej); });
  const conn = { alpn: socket.alpnProtocol || "http/1.1", tlsMs: performance.now() - t0 };
  let session = null, agent = null;
  if (conn.alpn === "h2") {
    // Flow-control windows as Chrome sets them (6 MiB per stream, 15 MiB per connection). With Node's defaults
    // (64 KiB for the whole connection) a lookup of 88 x 4 KiB stalls on WINDOW_UPDATE round trips.
    session = http2.connect(ORIGIN, { createConnection: () => socket, settings: { initialWindowSize: 6 << 20 } });
    session.on("error", () => {});
    await new Promise((res) => (session.connecting ? session.once("connect", res) : res()));
    session.setLocalWindowSize(15 << 20);
  } else {
    socket.destroy();
    agent = new https.Agent({ keepAlive: true, maxSockets: opt.h1Conns });
  }
  const sessions = new Set(); // distinct TCP connections used (HTTP/1.1)

  function get(url, range) {
    const p = new URL(url);
    const start = performance.now();
    return new Promise((resolve) => {
      const rec = { start, protocol: conn.alpn };
      const done = (extra) => resolve(Object.assign(rec, { end: performance.now() }, extra));
      if (session) {
        const req = session.request({ ":path": p.pathname + p.search, ...opt.headers, range });
        const chunks = [];
        req.on("response", (h) => Object.assign(rec, { ttfb: performance.now(), status: h[":status"],
          contentRange: h["content-range"], headers: pick(h) }));
        req.on("data", (c) => chunks.push(c));
        req.on("end", () => done({ bytes: chunks.reduce((a, c) => a + c.length, 0) }));
        req.on("error", (e) => done({ error: String(e) }));
        req.end();
      } else {
        const req = https.request(url, { agent, headers: { ...opt.headers, range } }, (res) => {
          sessions.add(res.socket);
          Object.assign(rec, { ttfb: performance.now(), status: res.statusCode,
                               contentRange: res.headers["content-range"], headers: pick(res.headers) });
          let n = 0;
          res.on("data", (c) => (n += c.length));
          res.on("end", () => done({ bytes: n }));
        });
        req.on("error", (e) => done({ error: String(e) }));
        req.end();
      }
    });
  }
  return { conn, get, connections: () => (session ? 1 : sessions.size), close: () => { session?.close(); agent?.destroy(); } };
}

// ---------------------------------------------------------------------------------------------- browser engine
/** Why a cross-origin browser fetch fails: replay it from Node with and without the headers a browser adds. */
async function diagnose(origin) {
  const ask = async (extra) => {
    try {
      const r = await fetch(opt.urls[0], { headers: { range: "bytes=0-0", origin, ...extra } });
      return `${r.status}, Access-Control-Allow-Origin: ${r.headers.get("access-control-allow-origin") ?? "none"}`;
    } catch (e) { return String(e); }
  };
  const plain = await ask({}), browserLike = await ask({ "sec-fetch-site": "cross-site", "sec-fetch-mode": "cors", "sec-fetch-dest": "empty" });
  return `Replayed from Node: with Origin only -> ${plain}; with the browser's Sec-Fetch-* headers -> ${browserLike}. ` +
         (plain !== browserLike ? "The host treats browser (cross-site) requests differently, so a browser client cannot use it." :
          "The host sends no usable CORS headers for browser requests.");
}

function findChrome() {
  if (opt.chrome) return opt.chrome;
  const base = join(homedir(), ".cache/ms-playwright");
  for (const d of existsSync(base) ? readdirSync(base).sort().reverse() : []) {
    for (const rel of ["chrome-headless-shell-linux64/chrome-headless-shell", "chrome-linux/chrome",
                       "chrome-linux64/chrome"]) {
      const p = join(base, d, rel);
      if (existsSync(p)) return p;
    }
  }
  throw new Error("no Chromium found: pass --chrome PATH or set $CHROME");
}

async function browserEngine() {
  const conn = { alpn: "(browser)", tlsMs: NaN, page: null };
  let server = null;
  const dir = mkdtempSync(join(tmpdir(), "range-bench-"));
  const proc = spawn(findChrome(), ["--headless", "--no-sandbox", "--remote-debugging-port=0", `--user-data-dir=${dir}`,
                                    "--no-first-run", "about:blank"], { stdio: ["ignore", "ignore", "pipe"], detached: true });
  // Always stop Chromium (its whole process group: it forks helper processes) and delete its profile, also when the
  // run ends with an error.
  process.on("exit", () => {
    try { process.kill(-proc.pid, "SIGKILL"); } catch {}
    try { rmSync(dir, { recursive: true, force: true, maxRetries: 5 }); } catch {}
  });
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
  // Page to run the requests from. "vendor": a page on the host's origin (any path; a 404 page is fine), so the
  // requests are same-origin and need no CORS. Some hosts serve sandboxed error pages (opaque origin) where fetch
  // fails, so "auto" probes it and otherwise uses "local": a blank page served by this script on 127.0.0.1, i.e.
  // cross-origin requests that need the host's CORS headers, exactly like a deployed client on another origin.
  await cdp("Page.enable");
  const goto = async (url, origin) => {
    await cdp("Page.navigate", { url });
    for (let i = 0; i < 100 && (await evaluate("location.origin").catch(() => "")) !== origin; i++) await sleep(100);
  };
  const probe = () => evaluate(`fetch(${JSON.stringify(opt.urls[0])}, { headers: { Range: "bytes=0-0" }, cache: "no-store" })
    .then((r) => r.status === 206).catch(() => false)`);
  let page = null;
  if (opt.page !== "local") {
    await goto(`${ORIGIN}/__range_bench_${Date.now()}`, ORIGIN);
    if (opt.page === "vendor" || ((await evaluate("location.origin")) === ORIGIN && (await probe()))) page = "vendor";
  }
  if (!page) {
    server = createServer((_, res) => res.writeHead(200, { "content-type": "text/html" }).end("<!doctype html><title>range-bench</title>"));
    await new Promise((r) => server.listen(0, "127.0.0.1", r));
    const local = `http://127.0.0.1:${server.address().port}`;
    await goto(`${local}/`, local);
    page = "local";
    if (!(await probe())) throw new Error(`a browser page on ${local} cannot fetch ${opt.urls[0]}. ${await diagnose(local)}`);
  }
  conn.page = page;
  await evaluate(`performance.setResourceTimingBufferSize(100000); 1`);

  // All requests of a batch are issued inside the page (one evaluate per request would serialize them via CDP).
  const batch = async (reqs) => evaluate(`(async () => {
    const reqs = ${JSON.stringify(reqs)}; const keys = ${JSON.stringify(["x-cache", "x-cache-hits", "cf-cache-status", "age", "x-served-by", "server", "via", "x-goog-storage-class", "cf-ray"])};
    const t0 = performance.now();
    const out = await Promise.all(reqs.map(async ({ url, range }) => {
      const rec = { start: performance.now() };
      try {
        const res = await fetch(url, { headers: { Range: range }, cache: ${JSON.stringify(opt.cache)} });
        rec.ttfb = performance.now(); rec.status = res.status; rec.contentRange = res.headers.get("content-range");
        rec.headers = {}; for (const k of keys) { const v = res.headers.get(k); if (v != null) rec.headers[k] = v; }
        rec.bytes = (await res.arrayBuffer()).byteLength;
      } catch (e) { rec.error = String(e); }
      rec.end = performance.now(); return rec;
    }));
    // protocol per request from Resource Timing (entries in start order; match by URL in order)
    const ents = performance.getEntriesByType("resource").filter((e) => e.startTime >= t0 - 1);
    const byUrl = new Map(); for (const e of ents) { if (!byUrl.has(e.name)) byUrl.set(e.name, []); byUrl.get(e.name).push(e); }
    reqs.forEach((r, i) => { const e = byUrl.get(new URL(r.url, location.href).href)?.shift(); out[i].protocol = e?.nextHopProtocol || "?"; });
    performance.clearResourceTimings();
    return out;
  })()`);
  return { conn, batch, connections: () => "?",
           close: () => { ws.close(); server?.close(); process.exit(0); } };
}

// ---------------------------------------------------------------------------------------------- main
const eng = opt.engine === "node" ? await nodeEngine() : await browserEngine();
const runBatch = eng.batch ?? ((reqs) => Promise.all(reqs.map((r) => eng.get(r.url, r.range))));
const records = [];
console.log(`origin ${ORIGIN} | engine ${opt.engine}${opt.engine === "node" ? ` (${eng.conn.alpn}, TLS ${ms(eng.conn.tlsMs)})` : ` (cache: ${opt.cache}, page: ${eng.conn.page})`} | ` +
            `${opt.urls.length} object(s) | s = ${opt.s} ranges of ${opt.len} B per lookup | ${opt.queries} lookups`);

// 1. warm-up / size discovery
const sizes = Object.fromEntries(opt.urls.map((u) => [u, opt.size]));
if (opt.warm) {
  const t = performance.now();
  const res = await runBatch(opt.urls.map((url) => ({ url, range: "bytes=0-0" })));
  const wall = performance.now() - t;
  res.forEach((r, i) => {
    const m = /\/(\d+)$/.exec(r.contentRange ?? "");
    if (r.status !== 206) throw new Error(`warm-up of ${opt.urls[i]}: status ${r.status} ${r.error ?? ""}`);
    if (m) sizes[opt.urls[i]] = +m[1];
    else if (!opt.size) throw new Error(`warm-up of ${opt.urls[i]}: 206 but Content-Range is not readable (the host does ` +
      `not expose it to cross-origin pages via Access-Control-Expose-Headers); pass the object size with --size`);
    records.push({ phase: "warm", url: opt.urls[i], ...r });
  });
  const cache = [...new Set(res.map((r) => r.headers?.["x-cache"] ?? r.headers?.["cf-cache-status"] ?? "-"))].join("/");
  const hidden = res.some((r) => r.contentRange == null);
  console.log(`warm-up: ${res.length} x 1-byte request in ${ms(wall)} (cache: ${cache}); object sizes ` +
              `${[...new Set(Object.values(sizes))].join(", ")} B` +
              (hidden ? " (Content-Range not exposed to the page: checking status and length only, as the client does)" : ""));
}

// 2. lookups
const walls = [];
for (let q = 1; q <= opt.queries; q++) {
  const reqs = plan(sizes).map(({ url, offset }) => ({ url, offset, range: `bytes=${offset}-${offset + opt.len - 1}` }));
  const t = performance.now();
  const res = await runBatch(reqs);
  const wall = performance.now() - t;
  walls.push(wall);
  const checks = res.map((r, i) => check(r, reqs[i].offset, opt.len));
  const bad = checks.filter((c) => c !== "ok");
  const ttfb = res.filter((r) => r.ttfb).map((r) => r.ttfb - r.start), dur = res.map((r) => r.end - r.start);
  const tally = (f) => Object.entries(res.reduce((a, r) => ((a[f(r)] = (a[f(r)] ?? 0) + 1), a), {})).map(([k, v]) => `${k} ${v}`).join(", ");
  console.log(`lookup ${q}: wall ${ms(wall)} | per request: ttfb p50 ${ms(pct(ttfb, .5))}, p90 ${ms(pct(ttfb, .9))}, ` +
              `max ${ms(Math.max(...dur))} | ${res.length - bad.length}/${res.length} ok${bad.length ? ` (${[...new Set(bad)].slice(0, 3).join("; ")})` : ""} | ` +
              `proto: ${tally((r) => r.protocol)} | cache: ${tally((r) => r.headers?.["x-cache"] ?? r.headers?.["cf-cache-status"] ?? "-")}`);
  res.forEach((r, i) => records.push({ phase: `lookup${q}`, url: reqs[i].url, offset: reqs[i].offset, check: checks[i], ...r }));
  if (q < opt.queries) await sleep(opt.gap);
}
console.log(`summary: lookup wall p50 ${ms(pct(walls, .5))}, min ${ms(Math.min(...walls))}, max ${ms(Math.max(...walls))}` +
            (opt.engine === "node" ? ` | connections used: ${eng.connections()}` : ""));
if (opt.json) writeFileSync(opt.json, JSON.stringify({ opt, sizes, records }, null, 1));
eng.close();
