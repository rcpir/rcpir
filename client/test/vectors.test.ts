// Client against the cross-language vectors in testvectors/vectors/ (docs/implementation_plan.md, 1A).
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { flipBit, fromHex, toHex } from "../src/bits.js";
import { RcPirError } from "../src/errors.js";
import { hColumn, importHSeed } from "../src/h_prg.js";
import { isInsecure, parseParams } from "../src/params.js";
import { buildComputeQuery, columnLocation, decodeBlock } from "../src/query.js";
import { isWellFormed } from "./helpers.js";

// Compiled to client/build-test/test/, so the repository root is three levels up.
const load = (name: string): any =>
  JSON.parse(readFileSync(new URL(`../../../testvectors/vectors/${name}`, import.meta.url), "utf8"));

const keys = new Map<string, Promise<CryptoKey>>();
const keyFor = (seedHex: string): Promise<CryptoKey> => {
  if (!keys.has(seedHex)) keys.set(seedHex, importHSeed(fromHex(seedHex)));
  return keys.get(seedHex)!;
};

test("h_prg.json: WebCrypto AES-CTR (length: 64) columns", async () => {
  const { cases } = load("h_prg.json");
  assert.ok(cases.length >= 100);
  for (const c of cases) {
    const col = await hColumn(await keyFor(c.h_seed), c.t, c.j);
    const where = `seed=${c.h_seed} t=${c.t} j=${c.j}`;
    assert.equal(col.length, c.nbytes, where);
    if (c.col_hex !== undefined) assert.equal(toHex(col), c.col_hex, where);
    else assert.equal(createHash("sha256").update(col).digest("hex"), c.col_sha256, where);
  }
});

test("bitpack.json: MSB-first packing via flipBit; malformed vectors rejected", () => {
  const { valid, invalid } = load("bitpack.json");
  for (const c of valid) {
    const q = new Uint8Array(Math.ceil(c.t / 8));
    [...(c.bits as string)].forEach((b, r) => b === "1" && flipBit(q, r));
    assert.equal(toHex(q), c.packed_hex, c.name);
  }
  for (const c of invalid) assert.equal(isWellFormed(fromHex(c.packed_hex), c.t), false, c.name);
});

test("qc.json: q_c for a given S and i", async () => {
  for (const c of load("qc.json").cases) {
    const qc = await buildComputeQuery({ t: c.t, m: c.m }, await keyFor(c.h_seed), c.S, c.i);
    assert.equal(toHex(qc), c.qc_hex, c.name);
  }
});

test("column_location.json", () => {
  for (const c of load("column_location.json").cases) {
    assert.deepEqual(columnLocation(c.j, c.columns_per_shard, c.L), { path: c.path, offset: c.offset });
  }
});

test("db_format.json decode cases", () => {
  for (const c of load("db_format.json").decode) {
    const col = fromHex(c.column_hex);
    if (c.payload_hex !== undefined) assert.equal(toHex(decodeBlock(col)), c.payload_hex, c.name);
    else if (c.error === "length_too_large") assert.throws(() => decodeBlock(col), RcPirError, c.name);
    else assert.notEqual(col.length, c.L, c.name); // wrong_column_length: rejected by the fetch length check
  }
});

test("params.json validation fixtures", () => {
  const { valid, invalid } = load("params.json");
  const bytes = (p: unknown) => new TextEncoder().encode(JSON.stringify(p));
  for (const c of valid) assert.equal(isInsecure(parseParams(bytes(c.params))), c.insecure_override, c.name);
  for (const c of invalid) assert.throws(() => parseParams(bytes(c.params)), RcPirError, c.name);
});
