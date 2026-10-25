import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { test } from "node:test";
import { xorInto, xorManyInto } from "../src/bits.js";

/** View of `n` random bytes at byte offset `offset` of a larger buffer (offset != 0 mod 4: not word-aligned). */
function randomView(n: number, offset: number): Uint8Array {
  const backing = new Uint8Array(randomBytes(offset + n + 5));
  return backing.subarray(offset, offset + n);
}

function reference(dst: Uint8Array, srcs: readonly Uint8Array[]): Uint8Array {
  const out = dst.slice();
  for (const src of srcs) for (let k = 0; k < out.length; k++) out[k]! ^= src[k]!;
  return out;
}

test("xorManyInto matches byte-by-byte XOR: lengths, offsets (aligned or not), 0-9 sources", () => {
  for (const n of [0, 1, 3, 4, 5, 8, 31, 64, 67, 1032]) {
    for (const dstOffset of [0, 1, 4]) {
      for (const srcOffset of [0, 2, 8]) {
        for (let count = 0; count <= 9; count++) {
          const dst = randomView(n, dstOffset);
          // Sources may be longer than dst; only the first dst.length bytes are used.
          const srcs = Array.from({ length: count }, (_, k) => randomView(n + (k % 3), srcOffset));
          const expected = reference(dst, srcs);
          const before = srcs.map((src) => src.slice());
          xorManyInto(dst, srcs);
          assert.deepEqual(dst, expected, `n=${n} dstOffset=${dstOffset} srcOffset=${srcOffset} count=${count}`);
          srcs.forEach((src, k) => assert.deepEqual(src, before[k]));
        }
      }
    }
  }
});

test("xorInto equals xorManyInto with one source", () => {
  for (const n of [0, 5, 64, 1027]) {
    const dst = randomView(n, n % 4);
    const src = randomView(n, 0);
    const expected = reference(dst, [src]);
    xorInto(dst, src);
    assert.deepEqual(dst, expected);
  }
});

test("a source shorter than dst is rejected, dst unchanged", () => {
  const dst = randomView(16, 0);
  const before = dst.slice();
  assert.throws(() => xorManyInto(dst, [randomView(16, 0), randomView(15, 0)]), RangeError);
  assert.throws(() => xorInto(dst, randomView(3, 0)), RangeError);
  assert.deepEqual(dst, before);
});
