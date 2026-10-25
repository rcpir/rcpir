// B5: client cost per query in Node (no network), using the client library (client/dist).
// Steps: sample S; build q_c (s AES-CTR columns of H + XOR); decode (XOR of s+1 columns + header).
// Configurations: the B1-optimal power-of-two shapes for 1 GiB (results/comm.md §4), or with "records"
// the best shape (min. communication) of every (record size, c) in results/comm_shapes.json.
// Prints one JSON line each.
// Every configuration runs in its own Node process, one after another: in a shared
// process V8's JIT makes later configurations up to 40% slower (measured), so the order would matter.
// Usage: (cd client && npm install && npm run build) && node benchmarks/bench_client.mjs [records [B ...]]
// (B: record sizes in bytes to run; default all).

import { randomBytes } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { buildComputeQuery, combineAnswers, decodeBlock, importHSeed, sampleSubset } from "../client/dist/index.js";

const FIXED = [
  { c: 2, t: 2 ** 20, L: 1024, s: 180 },
  { c: 4, t: 2 ** 20, L: 1024, s: 90 },
  { c: 8, t: 2 ** 19, L: 2048, s: 60 },
  { c: 16, t: 2 ** 19, L: 2048, s: 45 },
];
const recordConfigs = () =>
  JSON.parse(readFileSync(new URL("results/comm_shapes.json", import.meta.url)))
    .filter((d) => d.best_comm)
    .map(({ B, c, g, t, L, m, s }) => ({ B, g, c, t, L, m, s }));

// Driver (default and "records"): one child process per configuration, sequentially (execFileSync blocks).
if (process.argv[2] !== "one" && process.argv[2] !== "fixed-one") {
  const records = process.argv[2] === "records";
  const only = process.argv.slice(3);
  const jobs = records
    ? recordConfigs().filter((d) => only.length === 0 || only.includes(String(d.B))).map(({ B, c }) => ["one", B, c])
    : FIXED.map((_, k) => ["fixed-one", k]);
  for (const job of jobs) {
    process.stdout.write(execFileSync(process.execPath, [fileURLToPath(import.meta.url), ...job.map(String)]));
  }
  process.exit(0);
}
const CONFIGS = process.argv[2] === "one"
  ? recordConfigs().filter((d) => d.B === Number(process.argv[3]) && d.c === Number(process.argv[4]))
  : [FIXED[Number(process.argv[3])]];
const REPS = 100;
const WARMUP = 5;

const stats = (xs) => {
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
  const std = Math.sqrt(xs.reduce((a, b) => a + (b - mean) ** 2, 0) / xs.length);
  return { mean: +mean.toFixed(3), std: +std.toFixed(3) };
};

const key = await importHSeed(randomBytes(16));
for (const { B, g, c, t, L, s, m: mRecord } of CONFIGS) {
  const m = mRecord ?? c * t;
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
  const record = B === undefined ? {} : { B, g };
  console.log(JSON.stringify({ ...record, c, t, L, m, s, reps: REPS, node: process.version, ms: { ...ms, total } }));
}
