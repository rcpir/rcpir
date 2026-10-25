// Client cost per query in Node (no network), using the client library (client/dist), for the shape
// of every (record size, c) in results/comm_shapes.json. Steps: sample S; build q_c (s AES-CTR columns
// of H + XOR); decode (XOR of s+1 columns + header). Prints one JSON line each.
// Every configuration runs in its own Node process, one after another: in a shared process V8's JIT
// makes later configurations up to 40% slower (measured), so the order would matter.
// Usage: (cd client && npm install && npm run build) && node benchmarks/bench_client.mjs [B ...]
// (B: record sizes to run, as in comm_shapes.json, e.g. 1bit 64; default all).

import { randomBytes } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { buildComputeQuery, combineAnswers, decodeBlock, importHSeed, sampleSubset } from "../client/dist/index.js";

const recordConfigs = () =>
  JSON.parse(readFileSync(new URL("results/comm_shapes.json", import.meta.url)))
    .map(({ B, c, g, t, L, m, s }) => ({ B, g, c, t, L, m, s }));

// Driver: one child process ("one B c") per configuration, sequentially (execFileSync blocks).
if (process.argv[2] !== "one") {
  const only = process.argv.slice(2);
  for (const { B, c } of recordConfigs().filter((d) => only.length === 0 || only.includes(String(d.B)))) {
    process.stdout.write(execFileSync(process.execPath, [fileURLToPath(import.meta.url), "one", String(B), String(c)]));
  }
  process.exit(0);
}
const CONFIGS = recordConfigs().filter((d) => String(d.B) === process.argv[3] && d.c === Number(process.argv[4]));
const REPS = 100;
const WARMUP = 5;

const stats = (xs) => {
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
  const std = Math.sqrt(xs.reduce((a, b) => a + (b - mean) ** 2, 0) / xs.length);
  return { mean: +mean.toFixed(3), std: +std.toFixed(3) };
};

const key = await importHSeed(randomBytes(16));
for (const { B, g, c, t, L, s, m } of CONFIGS) {
  const times = { sample: [], query: [], decode: [] };
  for (let rep = 0; rep < WARMUP + REPS; rep++) {
    // Server answers: random bytes; the combined header says L - 4 bytes so decodeBlock copies a full payload.
    const answer = randomBytes(L);
    const columns = Array.from({ length: s }, () => randomBytes(L));
    columns.forEach((col) => col.fill(0, 0, 4));
    answer.writeUInt32BE(L - 4, 0);

    const t0 = performance.now();
    const S = sampleSubset(m, s);
    const t1 = performance.now();
    await buildComputeQuery({ t, m }, key, S, rep % t);
    const t2 = performance.now();
    decodeBlock(combineAnswers(answer, columns));
    const t3 = performance.now();
    if (rep >= WARMUP) {
      times.sample.push(t1 - t0);
      times.query.push(t2 - t1);
      times.decode.push(t3 - t2);
    }
  }
  const ms = Object.fromEntries(Object.entries(times).map(([k, v]) => [k, stats(v)]));
  const total = stats(times.sample.map((x, k) => x + times.query[k] + times.decode[k]));
  console.log(JSON.stringify({ B, g, c, t, L, m, s, reps: REPS, node: process.version, ms: { ...ms, total } }));
}
