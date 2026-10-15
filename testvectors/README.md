# Cross-language test vectors

Vectors for the formats that cross language boundaries between the encoder (Python), the client
(TypeScript) and the compute server (Rust). They are produced by `gen.py`, which uses the shared
Python primitives of `common/` (`rcpir_common`; not the encoder). They are verified by being consumed
by independent implementations in other languages: WebCrypto (`h_prg`, $q_c$), the Rust server
(`X.bin` layout, packing), and three `params.json` validators (see Consumers).

No full-scheme vectors (encoded DB + queries + answers) are here; the full scheme is checked by the
encoder's verify step and by `e2e/run.sh`.

## Files (`vectors/`)

Every file is JSON with a common header:
`{"format": "rc-pir-testvectors", "version": 1, "file": <name>, "spec": <doc>, "description": …}`.
Byte strings are lowercase hex. Integers fit in a JS `number` (≤ 2^32 + 1).

| File | Spec | Content | Consumers |
|---|---|---|---|
| `h_prg.json` | `docs/h_prg.md` | `cases[]`: `h_seed`, `t`, `j`, `nbytes`, and `col_hex` (t ≤ 1000) or `col_sha256` + `col_prefix_hex` + `col_suffix_hex` (first/last 32 bytes, t = 131072). 3 seeds × t ∈ {1,7,8,9,127,128,129,1000,131072} × j ∈ {0,1,255,256,2^31,2^32−1}. | encoder, client |
| `bitpack.json` | `docs/db_format.md` §3 | `valid[]`: `t`, `bits` (string of `0`/`1`, element 0 first), `packed_hex`. `invalid[]`: `t`, `packed_hex`, `reason` ∈ {`wrong_length`, `trailing_bits_nonzero`}. | client (packs q_c), server (parses q_c), encoder |
| `qc.json` | `docs/protocol.md` §4 | `cases[]`: `h_seed`, `t`, `m`, `S`, `i`, `qc_hex` = ⊕_{j∈S} H[*,j] ⊕ e_i, packed. | client |
| `column_location.json` | `docs/protocol.md` §2 | `cases[]`: `j`, `columns_per_shard`, `L`, `path` (shard, e.g. `/rc-pir/r/0000000f`), `offset` (bytes). | encoder (writes), client (fetches) |
| `db_format.json` | `docs/db_format.md` | `valid[]`: `jsonl_hex` (exact input bytes; `jsonl` is the same text), `t`, `max_payload`, `sum_payload`, `L`, `ell`, `payloads_hex`, `x_bin_hex` (X.bin, column-major), `db_digest`. `invalid[]`: `jsonl_hex`, `error_line` (1-based; `null` for the empty file), `reason`. `decode[]`: `L`, `column_hex`, and either `payload_hex` or `error` ∈ {`length_too_large`, `wrong_column_length`}. | encoder (valid, invalid), client (decode), server (X.bin layout, `db_digest`) |
| `params.json` | `docs/params_format.md` §4 | `valid[]` / `invalid[]`: `name`, `verdict`, `params` (the parsed object). Invalid fixtures are the spec example with exactly one rule broken (`violated_rule`). `insecure_override: true` marks the test-only override (`security.mode = "insecure-override"`, `security.insecure = true`): valid, but clients should warn. | encoder (writes valid files), client and server (validate) |

`reason` / `error` strings are informative; a consumer only has to reject (and, for JSONL, report the
right line). Matching the exact category is optional.

## Consumers

| Component | Test file | Checks |
|---|---|---|
| `common/` (Python) | `common/tests/test_common.py` | `h_column`/`h_panel`, packing, $q_c$, paths, block encode/decode, params validation |
| `encoder/` | `encoder/tests/test_vectors.py` | JSONL scan/pack (`x_bin_hex`, `db_digest`, `t`, `L`), rejection with the right line number |
| `client/` (TS) | `client/test/vectors.test.ts` | WebCrypto `h_prg`, packing via `flipBit`, $q_c$, paths, decoding, params validation |
| `server/` (Rust) | `server/crates/rcpir-core/tests/vectors.rs` | $q_c$ well-formedness, params validation, `X.bin` digest and $Xe_j$ |

The insecure-override fixture's `security` object is exactly what the encoder writes for
`--insecure-m 48 --insecure-s 4` on a $t=3$ database.

## Regenerating and testing

Uses the repository's Python env (`environment.yml`; `gen.py` adds `common/src` to `sys.path` itself):

```
.env/bin/python testvectors/gen.py           # rewrite vectors/*.json
.env/bin/python testvectors/gen.py --check   # exit 1 if vectors/ is stale
```

The output is deterministic (fixed seeds; payloads from SHA-256 in counter mode), so regenerating
without code changes gives byte-identical files.

## Not covered (deliberately)

- Payloads ≥ 2^32 bytes (too large for vectors).
- Cases the spec leaves open: non-canonical base64 trailing bits (e.g. `"QR=="`), CRLF line endings,
  duplicate `"data"` keys. Only the encoder reads JSONL, so these are not cross-language issues.
- Integer-valued floats in `params.json` (e.g. `"t": 3.0`): Python and Rust reject them, but JavaScript
  cannot tell them apart from integers (`params_format.md` §4).
