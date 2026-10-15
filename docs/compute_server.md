# Compute Server

Status: agreed design. Stack: Rust web server (axum/hyper, HTTP/2 over TLS), `docs/stack.md`.
Endpoints: `docs/protocol.md`.

## 1. Answer computation

$Xq_c$ over $\mathbb{F}_2$ with $X$ column-major (exactly `X.bin`): the XOR of the columns $j$ with
$q_j=1$. A pseudorandom $q_c$ selects about $t/2$ columns, so a query reads about half of $X$,
sequentially, and is memory-bandwidth bound.

- **Memory:** `X.bin` is loaded fully into RAM, into a heap buffer (`std::fs::read`). RAM ≥ |X| is required.
  `db_digest` is verified at startup (`--no-verify-digest` skips it). (Huge pages were measured: +17–20%
  single-threaded but ≤4% with 28 threads, so they are not used.)
- **Parallelism (one pass): column split.** The columns are cut into blocks (a multiple of 64 columns,
  about 1 MiB of $X$, at least 8 blocks per worker). Workers claim blocks from a shared atomic counter,
  so slower cores (E-cores) simply take fewer blocks. Each worker XORs the selected columns into its own
  accumulators; the workers' accumulators are XOR-reduced at the end. Every worker therefore reads long
  contiguous runs of whole columns.
- **Inner loop:** per block, the selected columns (OR over the batch) are listed first from the query
  words, so unselected columns cost no branch misprediction. The column 4 KiB ahead in that list is
  software-prefetched, one cache line per 64 bytes XORed. The XOR uses AVX2 (runtime-detected, with a
  portable fallback), 128 bytes per step: each chunk of a column is loaded once and XORed into every
  query of the batch that selects it.
- **Batching (one pass, $k$ queries):** $X\cdot[q^{(1)}\cdots q^{(k)}]$ with $X$ read once. Columns are
  processed in strips (byte ranges) of width $W=\min(L,\ 256\text{ KiB}/k)$: whole columns unless a large
  batch needs narrower strips to keep its accumulators in L2; each strip is one column-split pass.
  A Four-Russians table (256 combinations per 8 columns) is a later optimization for large $k$ (from
  $k\approx64$ the pass is compute bound).
- **Measured** (i7-14700KF, WSL2, 2 GiB, $k=1$): the pass reaches the machine's read bandwidth (≈80 GB/s)
  from about 8 threads: ≈13.3–14.5 ms for $L$ from 2 KiB to 32 KiB, ≈17.5 ms at 256 B (the floor, half
  of $X$ at 80 GB/s, is ≈13.4 ms). The first version split $[0,L)$
  into one byte range per thread, so each thread read only $L/\text{threads}$ bytes per column; it took
  167 / 50 / 23 ms at $L$ = 256 B / 2 KiB / 8 KiB with 28 threads. Batches cost ≈1.7–2.2 ms per query
  at $k=16$. Rejected after measuring: cutting long columns into fixed 4–8 KiB strips (13–33% slower),
  letting the compiler vectorize the XOR instead of the AVX2 kernel, and per-query safe slices instead
  of loading each chunk once for all queries (both up to ~20% slower for batches, equal for $k=1$).
- **Backend:** CPU only in v1, behind a trait so a GPU backend (X in VRAM) can be added:
  ```rust
  trait Backend {
      /// One pass over X answering all queries; queries[i] is ceil(t/8) bytes, out[i] is L bytes.
      fn answer_batch(&self, queries: &[&[u8]], out: &mut [&mut [u8]]);
  }
  ```

## 2. Configuration (all settable for evaluation)

| Option | Default | Meaning |
|---|---|---|
| `--threads N` | all cores | Worker threads per pass. `--threads 1` = single-core results; sweep for scaling. |
| `--pin-cores LIST` | none | Pin worker $i$ to the $i$-th listed core (reproducible benchmarks; on hybrid CPUs such as the i7-14700KF choose P-cores vs E-cores explicitly). Under WSL2, pinning applies to vCPUs and may not map to fixed physical cores. |
| `--max-batch K` | 16 | Max queries per pass. **`--max-batch 1` disables batching**: every request is its own pass. |
| `--max-wait US` | 0 | How long the first queued request waits for others. **`--max-wait 0`** (default) starts a pass immediately with whatever is already queued; queries that arrive during a pass share the next one (natural batching). A wait only helps an idle server catch a burst, and costs every lone query that much latency. |
| `--max-queue N` | 1024 | Max queries waiting for a pass. When full, a query is rejected at once with `503` + `Retry-After` (load shedding; the client retries). Queries whose client has gone are skipped. |

## 3. Endpoints (see `docs/protocol.md` §3)

- `POST /rc-pir/query`: one query; goes through the micro-batching queue (§2). Bodies longer than
  $\lceil t/8\rceil$ bytes are rejected with `413` before they are read. There is no batch endpoint:
  a client with several queries sends them concurrently and micro-batching merges them.
- `GET /.well-known/rc-pir.json`, CORS / `OPTIONS` handling (`docs/protocol.md` §5).

## 4. Benchmark harness (`benchmarks/server-bench/`)

A separate binary `server-bench` calls `CpuBackend` directly (no HTTP, no TLS) so that compute cost
is measured in isolation, on a random 1 GiB $X$ with fresh uniform queries for every pass:

```
server-bench --shapes T1xL1,T2xL2 --threads 1,28 --batch 1,2,4 --reps 20
```

- Prints one JSON line per (shape, threads, batch): time per pass and time per query.
- `benchmarks/run_server.sh` runs the sweep; results go to `benchmarks/results/server.jsonl` and
  are summarized in `benchmarks/README.md`.
- End-to-end HTTP latency is measured separately with the client.

## 5. Out of scope (v1)

- Query-budget enforcement: not enforced. The $Q=2^{32}$ bound is documented only (`docs/protocol.md` §4);
  re-encoding is the operator's responsibility.
- Rate limiting and authentication (each query costs a full scan, so this matters for public deployments).
