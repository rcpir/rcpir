// Byte helpers. F_2 vectors are packed MSB-first (docs/db_format.md §3):
// element 8b+k is bit 7-k of byte b.

/** Flips bit i of a packed vector. */
export function flipBit(buf: Uint8Array, i: number): void {
  buf[i >> 3]! ^= 0x80 >> (i & 7);
}

// XOR works 32 bits at a time through Uint32Array views when the buffers allow it (4-byte aligned
// byteOffset; XOR does not depend on byte order). Buffers from fetch and WebCrypto are fresh
// ArrayBuffers, so they always are. Otherwise, and for the last length % 4 bytes, byte by byte.

/** True if a Uint32Array view of the first `n` bytes of `buf` can be created. */
function wordAligned(buf: Uint8Array, n: number): boolean {
  return (buf.byteOffset & 3) === 0 && buf.length >= n;
}

function words(buf: Uint8Array, count: number): Uint32Array {
  return new Uint32Array(buf.buffer, buf.byteOffset, count);
}

/** dst ^= src, over the first dst.length bytes (src must be at least as long). */
export function xorInto(dst: Uint8Array, src: Uint8Array): void {
  xorManyInto(dst, [src]);
}

/**
 * dst ^= srcs[0] ^ srcs[1] ^ ..., over the first dst.length bytes (every src at least as long).
 * Four sources per pass, so dst is loaded and stored once per four sources instead of once per source;
 * the 0-3 sources left over are done in one more pass.
 */
export function xorManyInto(dst: Uint8Array, srcs: readonly Uint8Array[]): void {
  const n = dst.length;
  if (srcs.some((src) => src.length < n)) throw new RangeError("xorManyInto: a source is shorter than dst");
  let done = 0;
  if (wordAligned(dst, n) && srcs.every((src) => wordAligned(src, n))) {
    const nw = n >>> 2;
    const d = words(dst, nw);
    const v = srcs.map((src) => words(src, nw));
    let i = 0;
    for (; i + 4 <= v.length; i += 4) {
      const a = v[i]!, b = v[i + 1]!, c = v[i + 2]!, e = v[i + 3]!;
      for (let w = 0; w < nw; w++) d[w]! ^= a[w]! ^ b[w]! ^ c[w]! ^ e[w]!;
    }
    const left = v.length - i; // 0..3
    if (left === 3) {
      const a = v[i]!, b = v[i + 1]!, c = v[i + 2]!;
      for (let w = 0; w < nw; w++) d[w]! ^= a[w]! ^ b[w]! ^ c[w]!;
    } else if (left === 2) {
      const a = v[i]!, b = v[i + 1]!;
      for (let w = 0; w < nw; w++) d[w]! ^= a[w]! ^ b[w]!;
    } else if (left === 1) {
      const a = v[i]!;
      for (let w = 0; w < nw; w++) d[w]! ^= a[w]!;
    }
    done = nw << 2;
  }
  for (const src of srcs) for (let k = done; k < n; k++) dst[k]! ^= src[k]!;
}

// Uint8Array.prototype.toHex / Uint8Array.fromHex are not available in Node 24, hence these two.
export function toHex(buf: Uint8Array): string {
  return Array.from(buf, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function fromHex(hex: string): Uint8Array {
  return Uint8Array.from(hex.match(/../g) ?? [], (h) => parseInt(h, 16));
}
