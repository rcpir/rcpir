// The deterministic protocol steps (docs/protocol.md §2, §4; docs/db_format.md §3).
// No I/O and no randomness: the caller supplies S, so conformance tests can drive them directly.

import { flipBit, xorInto } from "./bits.js";
import { RcPirError } from "./errors.js";
import { hColumn } from "./h_prg.js";
import type { Params } from "./params.js";

/**
 * Location of column j of R on the retrieval server: the L bytes at `offset` in the shard at `path`,
 * /rc-pir/r/<shard as 8 hex digits>, shard = floor(j / columns_per_shard).
 */
export function columnLocation(j: number, columnsPerShard: number, L: number): { path: string; offset: number } {
  const shard = Math.floor(j / columnsPerShard);
  return { path: `/rc-pir/r/${shard.toString(16).padStart(8, "0")}`, offset: (j % columnsPerShard) * L };
}

/** q_c = XOR of the columns H_{*,j} for j in S, with bit i flipped. */
export async function buildComputeQuery(
  p: Pick<Params, "t" | "m">,
  hKey: CryptoKey,
  S: readonly number[],
  i: number,
): Promise<Uint8Array> {
  if (!Number.isInteger(i) || i < 0 || i >= p.t) throw new RcPirError("bad-argument", `index ${i} not in [0, ${p.t})`);
  if (S.some((j) => !Number.isInteger(j) || j < 0 || j >= p.m) || new Set(S).size !== S.length) {
    throw new RcPirError("bad-argument", "S must contain distinct indices in [0, m)");
  }
  const qc = new Uint8Array(Math.ceil(p.t / 8));
  for (const col of await Promise.all(S.map((j) => hColumn(hKey, p.t, j)))) xorInto(qc, col);
  flipBit(qc, i);
  return qc;
}

/** Column i of X = X q_c XOR (XOR of the retrieved columns R_{*,j}, j in S). */
export function combineAnswers(computeAnswer: Uint8Array, retrieved: readonly Uint8Array[]): Uint8Array {
  const col = computeAnswer.slice();
  for (const r of retrieved) xorInto(col, r);
  return col;
}

/** Block payload: u32 big-endian length header, then the payload. Rejects len > L-4. */
export function decodeBlock(column: Uint8Array): Uint8Array {
  const len = new DataView(column.buffer, column.byteOffset, column.byteLength).getUint32(0);
  if (len > column.length - 4) {
    throw new RcPirError("decode-invalid", `block header says ${len} bytes, at most ${column.length - 4} fit`);
  }
  return column.slice(4, 4 + len);
}
