// Retrieves blocks with the client library and compares them with the encoder's input JSONL.
//
//   node e2e/retrieve_all.mjs DB.jsonl RETRIEVAL_ORIGIN COMPUTE_ORIGIN [MAX_BLOCKS]
//
// Checks every block if MAX_BLOCKS is omitted, otherwise the first, the last and random ones.

import { readFileSync } from "node:fs";
import { RcPirClient } from "../client/dist/index.js";

const [dbPath, retrieval, compute, maxBlocks] = process.argv.slice(2);
const expected = readFileSync(dbPath, "utf8")
  .split("\n")
  .filter((line) => line !== "")
  .map((line) => new Uint8Array(Buffer.from(JSON.parse(line).data, "base64")));

const client = await RcPirClient.connect({ retrieval, compute });
const t = client.params.t;
if (t !== expected.length) throw new Error(`params.t = ${t}, but the JSONL has ${expected.length} blocks`);

let indices = [...Array(t).keys()];
if (maxBlocks !== undefined && Number(maxBlocks) < t) {
  const rest = indices.slice(1, -1).sort(() => Math.random() - 0.5);
  indices = [0, t - 1, ...rest.slice(0, Number(maxBlocks) - 2)];
}

const start = performance.now();
for (const i of indices) {
  const got = await client.retrieve(i);
  if (Buffer.compare(Buffer.from(got), Buffer.from(expected[i])) !== 0) {
    throw new Error(`block ${i}: got ${got.length} bytes, expected ${expected[i].length}`);
  }
}
const ms = (performance.now() - start) / indices.length;
console.log(`ok: ${indices.length} of ${t} blocks retrieved correctly (${ms.toFixed(1)} ms per block, s = ${client.params.s})`);
