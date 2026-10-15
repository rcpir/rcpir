// Byte helpers. F_2 vectors are packed MSB-first (docs/db_format.md §3):
// element 8b+k is bit 7-k of byte b.

/** Flips bit i of a packed vector. */
export function flipBit(buf: Uint8Array, i: number): void {
  buf[i >> 3]! ^= 0x80 >> (i & 7);
}

/** dst ^= src */
export function xorInto(dst: Uint8Array, src: Uint8Array): void {
  for (let k = 0; k < dst.length; k++) dst[k]! ^= src[k]!;
}

// Uint8Array.prototype.toHex / Uint8Array.fromHex are not available in Node 24, hence these two.
export function toHex(buf: Uint8Array): string {
  return Array.from(buf, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function fromHex(hex: string): Uint8Array {
  return Uint8Array.from(hex.match(/../g) ?? [], (h) => parseInt(h, 16));
}
