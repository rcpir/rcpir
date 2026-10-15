# @rcpir/client

TypeScript client for the √n RC-PIR over $\mathbb{F}_2$ (`docs/protocol.md`). No runtime
dependencies: it uses only `crypto.subtle`, `crypto.getRandomValues` and `fetch`, so it runs in
browsers (secure context: HTTPS or `localhost`) and in Node ≥ 19.

## Build and test

```
npm install          # dev dependencies only: typescript, @types/node
npm run build        # tsc -> dist/
npm test             # compiles src + test, runs node --test
```

## Usage

```ts
import { RcPirClient } from "@rcpir/client";

const client = await RcPirClient.connect({
  retrieval: "https://static.example.org",   // origins only, no path (protocol.md §1)
  compute: "https://compute.example.org",
  pinSha256: "…",                             // optional: SHA-256 of params.json
  timeoutMs: 30_000,                          // optional: deadline per call (default 30 s)
});
if (client.insecure) console.warn("test parameters: no privacy");
const payload = await client.retrieve(42);
```

- **`connect`** fetches `/.well-known/rc-pir.json` from both origins and requires identical copies. It
  then checks the optional pin and validates the file (`params_format.md` §4).
  `RcPirClient.fromParams(bytes, opts)` takes `params.json` from a trusted source instead.
- **`retrieve(i)`** follows `protocol.md` §4:
  1. Sample $S$ and build $q_c$.
  2. Send the $s$ GETs and the POST concurrently.
  3. Check status codes, lengths and `RC-PIR-DB-Digest`.
  4. XOR the answers and decode the block.
- **Timeout and cancellation.** Each call (`connect`, `retrieve`) runs its requests under one deadline
  of `timeoutMs` (default `DEFAULT_TIMEOUT_MS` = 30 s), including downloading the bodies. If the deadline
  passes or one request fails, the requests still in flight are aborted.
- **`client.insecure`** is true when `security` marks the test-only override
  (`"mode": "insecure-override"` or `"insecure": true`).
- **Errors.** Every failure of `connect`, `fromParams` and `retrieve` is an `RcPirError` with a `code`:

  | Code | Cause |
  |---|---|
  | `bad-argument` | Index out of range, malformed origin URL or origin with a path, `timeoutMs` ≤ 0 |
  | `network` | No complete response: DNS, connection, TLS, reset; in browsers also CORS. The original error is in `cause` (Node puts the socket error, e.g. `ECONNREFUSED`, in the message) |
  | `timeout` | The call's requests did not complete within `timeoutMs` |
  | `http-status` | A status other than 200 |
  | `bad-length` | A response body of the wrong length |
  | `params-invalid`, `params-mismatch`, `params-pin-mismatch` | `params.json` invalid, different on the two origins, or not matching the pin |
  | `digest-mismatch` | `RC-PIR-DB-Digest` differs from `params.db_digest` |
  | `decode-invalid` | Block header says `len > L-4` |

## Files

| File | Content |
|---|---|
| `src/client.ts` | `RcPirClient`: params discovery and `retrieve` |
| `src/query.ts` | Deterministic steps for a given $S$ and $i$: `buildComputeQuery`, `columnLocation`, `combineAnswers`, `decodeBlock` (exported for conformance tests) |
| `src/params.ts` | `parseParams` (validation), `isInsecure`, `sha256Hex` |
| `src/h_prg.ts` | `importHSeed`, `hColumn`: WebCrypto AES-CTR, counter `BE64(j) ‖ 0^64`, `length: 64` |
| `src/sample.ts` | `sampleSubset(m, s)`: uniform distinct indices; rejection sampling avoids modulo bias |
| `src/bits.ts` | `flipBit` (MSB-first), `xorInto`, `toHex`/`fromHex` (`Uint8Array.fromHex` is not in Node 24) |
| `src/cli.ts` | `rcpir-get` |

## CLI

```
rcpir-get --retrieval URL --compute URL --index i [--out FILE] [--pin-sha256 HEX] [--timeout-ms MS]
```

- `--timeout-ms` is the deadline of each phase (params discovery, retrieval); default 30000.
- Writes the payload to `FILE` or to stdout.
- Exit codes: 0 on success, 1 on a protocol error, 2 on a usage error.
- For self-signed development certificates set `NODE_EXTRA_CA_CERTS=ca.pem`.
- Node's `fetch` uses HTTP/1.1; browsers use HTTP/2.

## Tests

- **Cross-language vectors** (`test/vectors.test.ts`, reads `../testvectors/vectors/`): WebCrypto `h_prg`
  (162 cases, $t$ up to 131072, $j$ up to $2^{32}-1$), MSB-first packing, $q_c$ for given $S$ and $i$,
  column paths, block decoding, and the `params.json` validation fixtures.
- **End to end:** in-process `node:http` mock servers build a tiny $X$ and $R=XH$ from `h_prg`. The tests
  retrieve every block and check the failure cases: wrong or missing digest, wrong lengths, status,
  mismatching params, wrong pin, timeout, connection refused, and that the first failure aborts the
  requests still in flight.
