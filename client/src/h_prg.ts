// h_prg "aes128-ctr-col-v1" (docs/h_prg.md): column j of H is the AES-128-CTR keystream with
// initial counter block BE64(j) || BE64(0), truncated to ceil(t/8) bytes, rows >= t cleared.
// WebCrypto's `length: 64` increments the low 64 bits of the counter block, as the spec requires.

export async function importHSeed(seed: Uint8Array): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", seed as BufferSource, "AES-CTR", false, ["encrypt"]);
}

/** Packed column H_{*,j}: ceil(t/8) bytes, MSB-first. */
export async function hColumn(key: CryptoKey, t: number, j: number): Promise<Uint8Array> {
  const counter = new Uint8Array(16);
  new DataView(counter.buffer).setBigUint64(0, BigInt(j)); // big-endian
  const zeros = new Uint8Array(Math.ceil(t / 8));
  const col = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-CTR", counter, length: 64 }, key, zeros));
  if (t % 8) col[col.length - 1]! &= 0xff << (8 - (t % 8));
  return col;
}
