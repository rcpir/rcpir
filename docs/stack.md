# Implementation Stack

Status: agreed.

| Component | Stack | Notes |
|---|---|---|
| Encoder | Python; CuPy 1-bit tensor-core kernel on GPU (`mma` b1 AND.POPC, `encoder/src/rcpir_encoder/gf2_cuda.py`); numpy for I/O and bit packing; `cryptography` for AES-128-CTR (`h_prg`) | numpy float32 CPU backend for tests and small DBs. |
| Compute server | Rust web server (axum/hyper, HTTP/2 over TLS) | Each query scans all of $X$ (memory-bandwidth bound). Internals: `docs/compute_server.md`. |
| Client | TypeScript, zero dependencies, ES module (`@rcpir/client`); WebCrypto `AES-CTR`, `crypto.getRandomValues`, `fetch` | Runs in browsers (secure context required) and in Node ≥ 19 / Deno (CLI, tests). Demo page. |
| Retrieval server | Any static HTTPS host serving the shards of $R$ with single byte-range requests (`206`) and CORS headers; Caddy or nginx for local development (HTTP/2) | Nothing to implement. |

Repository layout (monorepo):

```
docs/         specs
common/       Python package rcpir_common: spec primitives shared by encoder/ and testvectors/
encoder/      Python package + CLI (rcpir-encode)
server/       Rust compute server (cargo workspace)
client/       TypeScript client (+ demo page, planned)
testvectors/  cross-language test vectors and their generator
e2e/          end-to-end test and a development static server
benchmarks/   benchmarks against SimplePIR/DoublePIR
environment.yml   one conda env for all Python parts (.env/)
```

Code is shared within a language, not across languages: Python shares `common/`; the TypeScript client
and the Rust server implement the same primitives and are checked against `testvectors/`.

## Client mapping of `h_prg`

`aes128-ctr-col-v1` (`docs/h_prg.md`) in WebCrypto:

```ts
const key = await crypto.subtle.importKey("raw", seed, "AES-CTR", false, ["encrypt"]);
const counter = new Uint8Array(16);
new DataView(counter.buffer).setBigUint64(0, BigInt(j));   // BE64(j) || 0^64
const col = new Uint8Array(await crypto.subtle.encrypt(
  { name: "AES-CTR", counter, length: 64 }, key, new Uint8Array(Math.ceil(t / 8))));
if (t % 8) col[col.length - 1] &= (0xff << (8 - t % 8)) & 0xff;
```

(`length: 64` = only the rightmost 64 bits of the counter block increment. Implemented in
`client/src/h_prg.ts` and checked against `testvectors/vectors/h_prg.json`.)
