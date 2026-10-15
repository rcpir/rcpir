// B5: client cost per query in Node (no network), using the client library (client/dist).
// Steps: sample S; build q_c (s AES-CTR columns of H + XOR); decode (XOR of s+1 columns + header).
// Configurations: the B1-optimal shapes for 1 GiB (results/comm.md). Prints one JSON line each.
// Usage: (cd client && npm install && npm run build) && node benchmarks/bench_client.mjs

import { randomBytes } from "node:crypto";
import { buildComputeQuery, combineAnswers, decodeBlock, importHSeed, sampleSubset } from "../client/dist/index.js";

const CONFIGS = [
  { c: 2, t: 2 ** 20, L: 1024, s: 180 },
  { c: 4, t: 2 ** 20, L: 1024, s: 90 },
  { c: 8, t: 2 ** 19, L: 2048, s: 60 },
  { c: 16, t: 2 ** 19, L: 2048, s: 45 },
];
const REPS = 100;
const WARMUP = 5;

const stats = (xs) => {
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
  const std = Math.sqrt(xs.reduce((a, b) => a + (b - mean) ** 2, 0) / xs.length);
  return { mean: +mean.toFixed(3), std: +std.toFixed(3) };
};

const key = await importHSeed(randomBytes(16));
for (const { c, t, L, s } of CONFIGS) {
  const m = c * t;
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
  console.log(JSON.stringify({ c, t, L, m, s, reps: REPS, node: process.version, ms: { ...ms, total } }));
}
