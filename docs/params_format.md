# `params.json` Format

Status: agreed spec. Written by the encoder; read by the client and both servers.
Notation follows `docs/lpn_parameters.md` and `docs/db_format.md`.

`params.json` describes one encoded database. It contains everything the client and both servers
must agree on bit-exactly, plus metadata recording why the parameters were chosen. Deployment
details (server URLs, endpoints) are **not** included; they belong in a separate client config.
HTTP servers publish it at `/.well-known/rc-pir.json` (§6).

## 1. Fields

| Field | Type | Meaning |
|---|---|---|
| `format_version` | int | Version of this format. Currently `1`. |
| `t` | int | Number of blocks = columns of $X$ = LPN dimension. |
| `ell` | int | Column length in bits ($\ell$). |
| `L` | int | Column length in bytes, $L=\ell/8$ (multiple of 8). Redundant; must equal `ell/8`. |
| `m` | int | Number of columns of $H$ and of $R=XH$ (= number of retrieval blocks). |
| `s` | int | Noise weight: the client fetches $s$ blocks of $R$ per query. |
| `h_prg` | string | Name of the rule that expands `h_seed` into $H\in\mathbb{F}_2^{t\times m}$. Currently `"aes128-ctr-col-v1"` (`docs/h_prg.md`). |
| `h_seed` | string | 16 bytes (AES-128 key), lowercase hex, 32 characters. **Public.** Drawn by the encoder from the OS CSPRNG. |
| `noise` | string | Noise distribution of $e$. Currently `"fixed-weight"`: uniformly random support of size exactly $s$. |
| `db_digest` | string | `"sha256:<hex>"` of the packed $X$ (column-major, $t$ columns of $L$ bytes, $tL$ bytes total). |
| `r_digest` | string | `"sha256:<hex>"` of all $m$ columns of $R$ in index order ($mL$ bytes total) = of the concatenation of the shards in order. |
| `columns_per_shard` | int | $C$: number of columns of $R$ per shard (`docs/protocol.md` §2). Column $j$ is in shard $\lfloor j/C\rfloor$ at byte offset $(j \bmod C)L$. |
| `security` | object | Audit metadata; not needed by the protocol (see §2). |
| `created` | string | UTC timestamp, ISO 8601 (e.g. `"2026-10-09T12:00:00Z"`). |
| `encoder_version` | string | Version of the encoder that produced the file. |

Fixed by spec, therefore **not** stored: block header (u32 big-endian payload length), bit order
(MSB-first, see `db_format.md` §3), shard paths (`docs/protocol.md` §2).

## 2. `security` object

| Field | Meaning |
|---|---|
| `lambda` | Target security level $\lambda$. |
| `log2_Q` | Lifetime query budget per $H$, $\log_2 Q$ (currently 32). |
| `lambda_eff` | $\lambda'=\lambda+\log_2 Q+\lceil\log_2 t\rceil$. |
| `c_eff` | $m/t$, rounded to 4 decimals. |
| `attack_bits` | `{"prange": …, "mitm": …, "brute_force": …}`: the lower bounds of `lpn_parameters.md` §3, rounded to 0.1 bit. |
| `binding_attack` | The cheaper of `"prange"` and `"mitm"` (ties: `"prange"`). |
| `mode` | `"A"` (given $c$) or `"B"` (given target communication), with its input (`c` or `target_comm_bits`), or `"insecure-override"` (below). |
| `insecure` | Present (`true`) only with `mode = "insecure-override"`. |

**Insecure override (tests only).** The encoder's `--insecure-m M --insecure-s S` skips parameter selection.
It then writes `"mode": "insecure-override"` and `"insecure": true`; the other fields are computed as usual.
Readers treat a file as insecure if `security.insecure == true` **or** `security.mode == "insecure-override"`,
accept it, and warn (the client exposes `client.insecure`). The compute server does not read `security`.

## 3. Example

```json
{
  "format_version": 1,
  "t": 131072,
  "ell": 32768,
  "L": 4096,
  "m": 2097152,
  "s": 45,
  "h_prg": "aes128-ctr-col-v1",
  "h_seed": "3f9c0a1b2c3d4e5f60718293a4b5c6e1",
  "noise": "fixed-weight",
  "db_digest": "sha256:…",
  "r_digest": "sha256:…",
  "columns_per_shard": 16384,
  "security": {
    "lambda": 128, "log2_Q": 32, "lambda_eff": 177, "c_eff": 16.0,
    "attack_bits": {"prange": 180.0, "mitm": 348.9, "brute_force": 697.9},
    "binding_attack": "prange",
    "mode": "A", "c": 16
  },
  "created": "2026-10-09T12:00:00Z",
  "encoder_version": "0.1.0"
}
```
(Values follow the Mode A rule for $\lambda=128$, $t=2^{17}$, $c=16$, and the default 64 MiB shard bound:
$C=2^{26}/4096$; seed and digests are placeholders.)

## 4. Validation (the client and the encoder must reject the file otherwise)

- The 12 protocol fields (`format_version` … `columns_per_shard`) are present. `security`, `created` and
  `encoder_version` are optional metadata; unknown fields are ignored (forward compatibility).
- `format_version`, `t`, `ell`, `L`, `m`, `s`, `columns_per_shard` are JSON integers (not strings, booleans or fractions).
  Note: JavaScript cannot tell `3` from `3.0`, so the client accepts an integer-valued float that the
  Python and Rust validators reject; the encoder never writes one.
- `format_version == 1`; `h_prg` and `noise` are known values.
- `t ≥ 1`, `1 ≤ s ≤ m ≤ 2^32`, `L ≥ 8`, `L % 8 == 0`, `ell == 8 * L`, `1 ≤ columns_per_shard ≤ m`.
- `h_seed` is exactly 32 lowercase hex characters.
- Digests have the form `sha256:` followed by 64 lowercase hex characters.

Implementations: `common/src/rcpir_common/params.py` (Python; the encoder validates what it writes) and
`client/src/params.ts`, both tested against `testvectors/vectors/params.json`.

**Compute server.** It reads only the fields it uses, `format_version`, `t`, `L` and `db_digest`, and
applies the rules above to them; all other fields are ignored (they protect the client, which validates
them). `server/crates/rcpir-core/src/params.rs` is tested against the same fixtures: it rejects exactly
the invalid fixtures that violate a rule on one of its four fields. The server still serves the file
byte-identical (§6).

## 5. Usage of the digests

- Each server reports the `db_digest` it serves (and the retrieval host can check `r_digest` after upload).
  The client aborts if they differ from `params.json`, which catches servers holding different DB
  versions or encodings (otherwise decoding silently returns garbage).

## 6. Publication over HTTP

An HTTP(S) server that hosts an RC-PIR database (the retrieval host, and the compute server if it
speaks HTTP) serves this file at the well-known path (RFC 8615):

```
GET /.well-known/rc-pir.json
```

- Content: exactly the `params.json` produced by the encoder (byte-identical, so a pinned SHA-256 matches).
- `Content-Type: application/json`.
- For browser (WASM) clients on another origin, the server should send `Access-Control-Allow-Origin`.
- Every server of one deployment serves the same file. The client fetches it from both servers and
  requires byte-identical copies (`protocol.md` §4), in addition to the `db_digest` check of §5.
  A client given `params.json` from a trusted source skips this fetch.

## 7. Trust

The client must obtain `params.json` from a trusted source (or pin its SHA-256). A malicious host
could otherwise substitute a crafted `h_seed` or a smaller `s`; this is outside the semi-honest model.
