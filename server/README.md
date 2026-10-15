# RC-PIR compute server (Rust)

The compute server answers $Xq_c$ over $\mathbb{F}_2$. Specs: `docs/compute_server.md` §1–3,
`docs/protocol.md` §3 and §5, `docs/params_format.md`, and `docs/db_format.md`. The server never uses
$H$ or `h_prg`.

## Layout

```
server/
  crates/rcpir-core/        library (also for the 2C benchmarks)
    params.rs               params.json: the 4 fields the server uses
    xdb.rs                  load X.bin into RAM, SHA-256 check
    backend.rs              Backend trait + CpuBackend (X q over F_2: column split, AVX2, prefetch)
    bits.rs                 MSB-first bit helpers (get_bit, tail_mask, is_well_formed)
    fixture.rs              random test DBs and a slow bit-level reference answer
    tests/vectors.rs        conformance with testvectors/vectors/ (q_c parsing, params, X.bin layout)
  crates/rcpir-server/
    main.rs                 startup + listener (axum-server: TLS via rustls, or plain)
    config.rs               command-line options (clap)
    app.rs                  routes, request validation, CORS (tower-http)
    batcher.rs              pass executor with micro-batching
    tests/http.rs           HTTP handler tests
```

## Build, test, run

```
cd server
cargo test                      # unit tests + HTTP handler tests
cargo build --release
target/release/rcpir-server --params DIR/params.json --x DIR/X.bin --tls-cert cert.pem --tls-key key.pem
target/release/rcpir-server --params DIR/params.json --x DIR/X.bin --plain --listen 127.0.0.1:8080
```

| Option | Default | Meaning |
|---|---|---|
| `--params`, `--x` | required | `params.json` and the packed `X.bin` from the encoder |
| `--listen ADDR` | `127.0.0.1:8443` | listen address |
| `--tls-cert`, `--tls-key` | | PEM certificate chain and key; HTTP/2 and HTTP/1.1 over TLS |
| `--plain` | off | no TLS: HTTP/1.1, and HTTP/2 with prior knowledge. Exactly one of TLS or `--plain` is required |
| `--threads N` | all cores | worker threads per pass |
| `--pin-cores 0,2,4` | none | pin worker *i* to the *i*-th listed core |
| `--max-batch K` | 16 | max queries per pass; `1` disables batching |
| `--max-wait US` | 0 | how long the first queued query waits for others; `0` = start right away (queries arriving during a pass share the next one) |
| `--max-queue N` | 1024 | max queries waiting for a pass; when full, queries get `503` with `Retry-After: 1` |
| `--cors-origin` | `*` | value of `Access-Control-Allow-Origin` |
| `--no-verify-digest` | off | skip the SHA-256 check of `X.bin` at startup |
| `--log-file PATH` | none | also append the log to `PATH` (created if missing, no colors); the log always goes to stdout |

The log level comes from `RUST_LOG` (default `info`); `RUST_LOG=debug` logs every pass. Errors that stop
the server and panics are logged at `ERROR`. Test databases come from the encoder (`--insecure-m/--insecure-s` for
tiny ones); the end-to-end check, including HTTP/2 over TLS and h2c, is `e2e/run.sh` at the repository root.

## Behaviour

- **Startup:**
  - Read `format_version`, `t`, `L` and `db_digest` from `params.json` and check them
    (`params_format.md` §4). All other fields are ignored: they matter to the client, which
    validates the whole file.
  - Read `X.bin` into RAM, check that its size is `t·L`, and check its SHA-256 against
    `db_digest`.
- **Backend** (`docs/compute_server.md` §1):
  - The columns are cut into blocks that the workers claim dynamically. Each worker XORs whole
    selected columns into its own accumulators, and these are XOR-reduced at the end.
  - Per block, the selected columns are listed from the query words; the column ~4 KiB ahead is
    prefetched, and the XOR uses AVX2 when the CPU has it.
  - A batch loads each column chunk once for all queries that select it. If `k·L` exceeds
    256 KiB, columns are processed in narrower strips so the accumulators stay in L2.
- **Executor:** one thread runs the passes one after another.
  - Queries wait at most `--max-wait`, counted from the first query's arrival, so that
    others can join. At most `--max-batch` queries share a pass. With the default
    `--max-wait 0`, batching is natural: queries that arrive during a pass share the next one.
  - At most `--max-queue` queries wait. When the queue is full, a query gets `503` with
    `Retry-After: 1` at once; retrying is up to the client.
  - A query whose client has gone (disconnect, timeout) while queued is skipped: it takes no
    slot in a pass.
  - A panic during a pass (a bug) does not stop the server. It is logged at `ERROR` (message,
    thread, location and backtrace), the queries of that pass get `500`, and the next queries are
    answered normally.
- **HTTP:**
  - `POST /rc-pir/query` takes exactly `ceil(t/8)` bytes with zero trailing bits. A shorter body
    or non-zero trailing bits give 400; a longer body gives 413 from the body limit. A full queue
    gives 503, a failed pass 500.
  - `GET /.well-known/rc-pir.json` serves `params.json` byte for byte.
  - Answers are `application/octet-stream` and carry `RC-PIR-DB-Digest`.
  - CORS comes from `tower-http`:
    - `Access-Control-Allow-Origin` on every response;
    - `Access-Control-Expose-Headers: rc-pir-db-digest, retry-after` on non-preflight responses;
    - preflight answered with `Allow-Methods: GET,POST`, `Allow-Headers: content-type` and
      `Max-Age: 86400`.

## Not in this crate (later levels)

- `rcpir-server-bench` and the thread/batch sweeps (2C).
- Four-Russians batching and a GPU backend (3C).
- Rate limiting, authentication and query-budget enforcement (out of scope for v1).
