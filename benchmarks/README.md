# Benchmarks: RC-PIR vs SimplePIR/DoublePIR (1 GiB database)

| Script | Benchmark | Output |
|---|---|---|
| `python3 comm.py` | B1: communication and storage by record size (analytic for RC-PIR: encoder's LPN parameter selection, $\lambda=128$; SimplePIR/DoublePIR from `results/bw_sweep/`), plus the server and client times measured by the runs below. Run it before and after them | `results/comm.md`, `results/comm_shapes.json` (RC-PIR shape per record size and $c$) |
| `./run_server.sh` | B2/B3: compute-server time per pass over shape, threads and batch size (`server-bench/`, calls `CpuBackend` directly, no HTTP) | `results/server.jsonl` |
| `./run_server.sh records` | Compute-server time for every shape in `results/comm_shapes.json`, one thread, one query, 10 passes | `results/server_records.jsonl` |
| `./bench_encode.sh`, `python3 encode_report.py` | B4: full preprocessing of a 1 GiB DB with the real encoder CLI (`--device cuda`, verify on), $c=2,4,8,16$; needs the repo's `.env` with CuPy | `results/encode_c*.log`, `results/encode.md` |
| `node bench_client.mjs` | Client time per query in Node, no network (sample $S$, build $q_c$, decode), for every shape in `results/comm_shapes.json`, one Node process per configuration; needs `(cd ../client && npm install && npm run build)` | `results/client_records.jsonl` |
| `./run_simplepir.sh bw-sweep` | SimplePIR/DoublePIR with the authors' own code (pinned commit, single thread): their `Test*PirBW` (communication only, layout from their `PickParams`) for 1 GiB of fixed-size records, record size 1 bit, 64 B … 64 KiB | `results/bw_sweep/` |
| `./run_simplepir.sh time-sweep` | Their `*PirSingle` benchmark (5 answers, single thread) at the same record sizes | `results/time_sweep/` |
| `(cd simplepir-query-split && go run .)` | Time of the steps of SimplePIR's client `Query` (their functions, 64-byte records; needs `simplepir/` from `run_simplepir.sh`) | `results/simplepir_query_split.txt` |
| `./run_simplepir.sh recover-sweep` | Their decode time at the same record sizes: their `RunPIR` with the real hint (`simplepir-recover/`, ≈ 3.8 min per run; `REPS`, `RECORD_SIZES`, `SCHEMES` select runs) | `results/recover_sweep/` (appended) |

Throughput is defined as in SimplePIR: database size × queries / server time. The retrieval
server does no computation and is not measured here.

Machine: i7-14700KF (8P + 12E, 28 threads, AVX2), 31 GB RAM, WSL2. Threads are not pinned.

## Database layout

All schemes store 1 GiB of fixed-size records (record size 1 bit to 64 KiB), and the client wants
one record per query; anything else a query returns is discarded. Each scheme chooses its own layout
for the record size:

- **SimplePIR** (`PickParams` → `ApproxSquareDatabaseDims`): the database is a near-square matrix over
  $\mathbb{Z}_p$ ($p\approx 700$, 9 bits per element). A record occupies consecutive elements of one
  column (the number of rows is rounded up so that records never cross columns), so one column holds
  many records: 553 for 64-byte records, 1 for 64 KiB records; 1-bit entries are packed 9 per element,
  278,037 per column. A query returns a whole column;
  `Recover` decodes all of it but keeps only the requested record. The square shape balances upload
  (one element per column) and download (one element per row), so the online communication stays
  ≈ 235–240 KiB for every record size up to 4 KiB.
- **DoublePIR** (`ApproxDatabaseDims`, at least `COMP_RATIO`$\cdot n$ = 65536 columns): returns only the
  requested record. Its `SetupDB` sets X = Ne (the number of elements per record), so its hint and
  download grow linearly with the record size.
- **RC-PIR**: several records are packed into one block (one column of $X$, the unit a query returns);
  the number of records per block is a power of two and a record never spans two blocks. Block size =
  4-byte header + records per block × record size, rounded up to 8 bytes; number of blocks $t$ = 1 GiB /
  (records per block × record size). The $i$-th record of a block starts at byte $4 + i\,\times$ record
  size (fixed-size records, one header per block; variable-size records would need an index).
  `comm.py` chooses the number of records per block with the smallest total communication. The
  optimum is not square but near $t\approx(s+1)\ell$ (`docs/db_format.md` §5). The encoder itself does
  not pack: the deployer writes the packed records as one JSONL line per block.

## Results

### Communication by record size (B1, `results/comm.md`)

What one client pays to retrieve records, and the server time per query, with each scheme using its
best layout for the record size (layout chosen for communication; RC-PIR with $c=16$). Columns are
grouped by metric: sizes downloaded once or stored, online communication, the resulting query
count, server time, throughput.

- **Hint**: one-time download before the first query (SimplePIR/DoublePIR only; RC-PIR has none).
- **Online**: upload + download of one query. For RC-PIR, compute server and retrieval server together.
- **RC-PIR storage**: $R=XH$ on the retrieval server (≈ $c$ × database), written once by the encoder.
  Clients never download it, so it does not enter any other column. Besides it, the compute server
  holds the database itself, as SimplePIR/DoublePIR servers do.
- **Queries until SimplePIR / DoublePIR is cheaper**: after $N$ queries a SimplePIR client has
  downloaded hint + $N$ × online, an RC-PIR client $N$ × online. The column gives the number of queries
  up to which RC-PIR's total is smaller, hint / (RC-PIR online − SimplePIR online); beyond it the hint
  has paid for itself. "never": RC-PIR is also cheaper per query, so the other scheme never catches up.
  Assumptions:
  - each client downloads the hint once and reuses it for all its queries;
  - the database does not change: after an update SimplePIR/DoublePIR clients download a new hint, so
    the count holds per database version;
  - communication only: the server's time to compute the hint (measured 2.5–2.7 min for SimplePIR at
    every record size of the sweep, 2.7–2.8 min for DoublePIR with 1-bit entries) and the client's storage for
    it are not counted;
  - upload and download are added; the hint counts as download.
- **Server time**: one query, one thread, mean. **Throughput** = 1 GiB of records / mean server time
  (as in SimplePIR). SimplePIR/DoublePIR: the 5 answer times of their `*PirSingle` benchmark
  (`results/time_sweep/`, spread ≤ ±8%); RC-PIR: compute server, 10 passes on the shape of the row
  (`results/server_records.jsonl`, std < 4%). The retrieval server only serves static byte ranges and is
  not timed. Run on 2026-10-25, each run alone, threads not pinned.

| Record size | RC-PIR records per block | SimplePIR hint | DoublePIR hint | RC-PIR storage | SimplePIR online | DoublePIR online | RC-PIR online | Queries until SimplePIR is cheaper | Queries until DoublePIR is cheaper | SimplePIR server time | DoublePIR server time | RC-PIR server time | SimplePIR throughput | DoublePIR throughput | RC-PIR throughput |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 bit | 16384 | 120.7 MiB | 16 MiB | 16.1 GiB | 240 KiB | 344 KiB | 156.5 KiB | never | never | 45.8 ms | 55.5 ms | 22.6 ms | 21.8 GiB/s | 18.0 GiB/s | 44.3 GiB/s |
| 64 B | 32 | 118.8 MiB | 912 MiB | 16.1 GiB | 236 KiB | 2.0 MiB | 156.5 KiB | never | never | 43.8 ms | 65.9 ms | 22.6 ms | 22.8 GiB/s | 15.2 GiB/s | 44.3 GiB/s |
| 256 B | 8 | 118.7 MiB | 3.5 GiB | 16.1 GiB | 235 KiB | 7.3 MiB | 156.5 KiB | never | never | 44.5 ms | 63.1 ms | 22.6 ms | 22.5 GiB/s | 15.8 GiB/s | 44.3 GiB/s |
| 1 KiB | 2 | 118.5 MiB | 14.1 GiB | 16.1 GiB | 235 KiB | 28.4 MiB | 156.5 KiB | never | never | 44.7 ms | 68.2 ms | 22.6 ms | 22.4 GiB/s | 14.7 GiB/s | 44.3 GiB/s |
| 4 KiB | 1 | 121.9 MiB | 56.2 GiB | 16.0 GiB | 234 KiB | 112.7 MiB | 216.5 KiB | never | never | 42.8 ms | 92.3 ms | 20.6 ms | 23.4 GiB/s | 10.8 GiB/s | 48.5 GiB/s |
| 8 KiB | 1 | 135.4 MiB | 112.4 GiB | 16.0 GiB | 237 KiB | 225.2 MiB | 384.5 KiB | 940 | never | 44.6 ms | 101.4 ms | 20.2 ms | 22.4 GiB/s | 9.9 GiB/s | 49.5 GiB/s |
| 16 KiB | 1 | 162.5 MiB | 224.9 GiB | 16.0 GiB | 247 KiB | 450.2 MiB | 728.5 KiB | 346 | never | 44.0 ms | 155.4 ms | 19.6 ms | 22.7 GiB/s | 6.4 GiB/s | 50.9 GiB/s |
| 64 KiB | 1 | 211.1 MiB | 899.4 GiB | 16.0 GiB | 275 KiB | 1.8 GiB | 2.8 MiB | 83 | never | 44.1 ms | killed in Setup¹ | 22.4 ms | 22.7 GiB/s | – | 44.7 GiB/s |

¹ Killed during their `Setup` with nothing else running (31 GB RAM); the matrix is padded to 57561 × 65536 elements. Most likely out of memory.

- Up to 4 KiB records, RC-PIR ($c=16$) costs less per query than SimplePIR and has no hint. From 8 KiB
  on, the $s$ blocks fetched from the retrieval server ($s\approx 44$) dominate, and SimplePIR becomes
  cheaper after 940 (8 KiB), 346 (16 KiB) and 83 (64 KiB) queries. A larger storage factor $c$ means
  fewer fetched blocks; see the table for every $c$ below.
- Packing matters for small records: with 64-byte records and one record per block ($2^{24}$ blocks), a
  query costs 2.0 MiB, mostly the compute query (one bit per block); with 32 records per block it costs
  156.5 KiB.
- Server time: RC-PIR's compute server is ≈ 2× faster than SimplePIR at every record size (19.6–22.6 ms
  vs 42.8–45.8 ms). A query reads about half of $X$ (columns with $q_j=0$ are skipped) and only XORs;
  SimplePIR reads all of its matrix and multiplies by 32-bit values. Both make one pass over the
  database, so their times barely depend on the record size; DoublePIR's grows with it (55 → 155 ms).
- DoublePIR (its implementation's `GetBW`) costs more than RC-PIR per query at every record size, so it
  never catches up. Its hint and download grow linearly with the record size (see Database layout); it
  is closest for 1-bit entries (16 MiB hint, 344 KiB online against RC-PIR's 156.5 KiB).

### RC-PIR for every storage factor $c$ (`results/comm.md` §1b)

The table above uses $c=16$. Here the same comparison with SimplePIR for every $c$ in the sweep; the
column header gives $c$ and the resulting storage on the retrieval server.

**How to read a cell**, e.g. "311 KiB / 1,600" ($c=2$, 1 KiB records):
- **Before the slash: RC-PIR's online communication per query**, 311 KiB (best number of records per
  block for that $c$).
- **After the slash: the number of queries until SimplePIR is cheaper** (the column of the same name
  in the table above). A SimplePIR client pays 235 KiB per query, 76 KiB less than RC-PIR, but first
  downloads a 118.5 MiB (121,380 KiB) hint. It catches up after 121,380 / 76 ≈ 1,600 queries: a client
  making fewer queries downloads less in total with RC-PIR, beyond that SimplePIR is cheaper. "never":
  RC-PIR is also cheaper per query, so SimplePIR never catches up. Same assumptions as above.

| Record size | c = 2 (2 GiB) | c = 4 (4 GiB) | c = 8 (8 GiB) | c = 16 (16 GiB) | c = 256 (256 GiB) |
|---|---|---|---|---|---|
| 1 bit | 311 KiB / 1,744 | 220 KiB / never | 187 KiB / never | 156 KiB / never | 112 KiB / never |
| 64 B | 311 KiB / 1,625 | 220 KiB / never | 187 KiB / never | 156 KiB / never | 112 KiB / never |
| 256 B | 311 KiB / 1,602 | 220 KiB / never | 187 KiB / never | 156 KiB / never | 112 KiB / never |
| 1 KiB | 311 KiB / 1,600 | 220 KiB / never | 187 KiB / never | 156 KiB / never | 112 KiB / never |
| 4 KiB | 750 KiB / 242 | 393 KiB / 785 | 277 KiB / 2,928 | 216 KiB / never | 128 KiB / never |
| 8 KiB | 1,442 KiB / 115 | 737 KiB / 277 | 497 KiB / 534 | 384 KiB / 940 | 208 KiB / never |
| 16 KiB | 2,842 KiB / 64 | 1,433 KiB / 140 | 969 KiB / 231 | 728 KiB / 346 | 376 KiB / 1,287 |
| 64 KiB | 11,204 KiB / 20 | 5,635 KiB / 40 | 3,779 KiB / 62 | 2,882 KiB / 83 | 1,474 KiB / 180 |

- SimplePIR's hint and online communication are those of the table above. DoublePIR is not shown: it
  is cheaper for no $c$ and record size.
- Records per block, and so the server time, are those of the table above except at $c=2$ and $c=4$
  with records up to 1 KiB: half as many records per block (1032-byte blocks), 26.3 ms instead of 22.6 ms.
- Storage buys communication: at $c=2$ (2 GiB) SimplePIR is cheaper after ≈ 1,600–1,750 queries even for
  small records; at $c=256$ (256 GiB) RC-PIR is cheaper per query for every record size up to 8 KiB.
  From 16 KiB on, no $c$ in the sweep makes RC-PIR cheaper per query; a larger $c$ only moves the
  point where SimplePIR becomes cheaper (16 KiB: 64 queries at $c=2$, 1,287 at $c=256$).

### Runtime per query for every storage factor $c$ (`results/comm.md` §1c)

Same layouts as the table above (best number of records per block for each $c$), grouped by metric.

- **Server time**: compute server, one query, one thread, as in the main table. It depends only on the
  block shape, not on $c$; it differs between $c$ only where the best number of records per block does
  ($c=2, 4$ with records up to 1 KiB).
- **Client time**: RC-PIR client in Node 24, single thread, no network, mean of 100 queries: sample the
  $s$ columns, build the compute query (expand $s$ columns of $H$ with AES-CTR, XOR them), decode (XOR
  $s+1$ blocks). Each configuration runs in its own Node process (`node bench_client.mjs records`,
  `results/client_records.jsonl`; repeated runs differ by 1–3% median, 8% at most): in one shared
  process V8's JIT made later configurations up to 40% slower. The client XORs 32-bit words, four
  sources per pass (`xorManyInto` in `client/src/bits.ts`).
- **SimplePIR client**: their Go client, query build + decode. Query build from the same `*PirSingle`
  logs (mean of 5). Decode = their `Recover` inside their full flow `RunPIR` with the real hint, mean of 3
  runs, each run alone (`./run_simplepir.sh recover-sweep`, `results/recover_sweep/`); it grows with the
  record size because the column (hint × secret, $l\times 1024$) gets longer ($l$ = 30415 → 54039). Their
  correctness check passed in every run; for records over 64 bits it compares the record folded into a
  wrapping `uint64` on both sides, so it is weaker than for small entries.
- **DoublePIR client**: measured like SimplePIR's, but its decode only for 1-bit entries (16 MiB hint);
  at the other record sizes the real hint is 912 MiB to 899 GiB, so only the query build is shown.

| Record size | server, c = 2 | server, c = 4 | server, c = 8 | server, c = 16 | server, c = 256 | SimplePIR server | client, c = 2 | client, c = 4 | client, c = 8 | client, c = 16 | client, c = 256 | SimplePIR client (query build + decode) | DoublePIR client (query build + decode) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 bit | 26.3 ms | 26.3 ms | 22.6 ms | 22.6 ms | 22.6 ms | 45.8 ms | 10.7 ms | 5.2 ms | 2.3 ms | 1.7 ms | 0.8 ms | 32.6 ms (25.7 + 7.0) | 202.9 ms (66.1 + 136.8) |
| 64 B | 26.3 ms | 26.3 ms | 22.6 ms | 22.6 ms | 22.6 ms | 43.8 ms | 10.2 ms | 4.6 ms | 2.2 ms | 1.6 ms | 0.8 ms | 32.1 ms (25.7 + 6.4) | 55.7 ms + decode n/a |
| 256 B | 26.3 ms | 26.3 ms | 22.6 ms | 22.6 ms | 22.6 ms | 44.5 ms | 10.1 ms | 4.6 ms | 2.2 ms | 1.6 ms | 0.8 ms | 30.4 ms (25.1 + 5.3) | 55.6 ms + decode n/a |
| 1 KiB | 26.3 ms | 26.3 ms | 22.6 ms | 22.6 ms | 22.6 ms | 44.7 ms | 10.7 ms | 4.9 ms | 2.2 ms | 1.7 ms | 0.9 ms | 33.0 ms (26.1 + 6.9) | 54.5 ms + decode n/a |
| 4 KiB | 20.6 ms | 20.6 ms | 20.6 ms | 20.6 ms | 20.6 ms | 42.8 ms | 4.9 ms | 2.6 ms | 1.7 ms | 1.4 ms | 0.7 ms | 31.8 ms (24.7 + 7.1) | 55.6 ms + decode n/a |
| 8 KiB | 20.2 ms | 20.2 ms | 20.2 ms | 20.2 ms | 20.2 ms | 44.6 ms | 4.5 ms | 2.3 ms | 1.6 ms | 1.2 ms | 0.6 ms | 30.7 ms (22.0 + 8.6) | 57.2 ms + decode n/a |
| 16 KiB | 19.6 ms | 19.6 ms | 19.6 ms | 19.6 ms | 19.6 ms | 44.0 ms | 4.1 ms | 2.2 ms | 1.4 ms | 1.1 ms | 0.6 ms | 27.5 ms (18.2 + 9.3) | 54.5 ms + decode n/a |
| 64 KiB | 22.4 ms | 22.4 ms | 22.4 ms | 22.4 ms | 22.4 ms | 44.1 ms | 4.7 ms | 2.3 ms | 1.7 ms | 1.3 ms | 0.7 ms | 27.7 ms (14.3 + 13.4) | n/a |

- **Why the client time depends on $c$.** Per query the client builds the compute query from $s$
  columns of $H$ ($s\cdot t$ bits of AES-CTR keystream, XORed) and decodes by XORing $s+1$ blocks of
  $L$ bytes, so both steps scale with the noise weight $s$. Security fixes $s$: the binding attack
  (Prange) costs $\approx s\log_2(m/t) = s\log_2 c$ bits, which must reach
  $\lambda'=\lambda+\log_2 Q+\lceil\log_2 t\rceil\approx 180$ (`docs/lpn_parameters.md`; `lpn.mode_a`), so
  $s\approx\lambda'/\log_2 c$: 180 at $c=2$, 45 at $c=16$, 23 at $c=256$. For small records a large $s$
  also moves the communication optimum ($t\approx(s+1)\ell$) to more, smaller blocks ($2^{20}$ at
  $c\le4$ vs $2^{19}$), which doubles $t$. Building the query dominates at every record size: AES-CTR
  in WebCrypto, whose cost grows with the keystream ($s\cdot t$ bits) and with the number of calls ($s$,
  one per column). Decoding takes at most 0.9 ms (64 KiB records, $c=2$). So the ratio between $c=2$
  and $c=16$ lies between the ratio of $s$ (≈ 4×) and of $s\cdot t$:

  | Record size | Query build at $c=2$ vs $c=16$ | Predicted $c=2$ : $c=16$ | Measured (total) |
  |---|---|---|---|
  | ≤ 1 KiB | $s$ = 180 vs 45 calls, $s\cdot t$ = $180\cdot2^{20}$ vs $45\cdot2^{19}$ bits (22.5 vs 2.8 MiB) | 4–8× | 10.1–10.7 vs 1.6–1.7 ms, 6.2–6.4× |
  | 4 KiB | same $t=2^{18}$: $s$ = 178 vs 45 | 4.0× | 4.9 vs 1.36 ms, 3.6× |
  | 64 KiB | same $t=2^{14}$ (2 KiB per column): $s$ = 174 vs 44 | 4.0× | 4.7 vs 1.35 ms, 3.5× |

  Measured ratios are a little below the predictions because some costs do not grow with $s$
  (sampling $S$, allocating $q_c$, starting the WebCrypto calls).

  The same $s$ sets the retrieval download ($s$ blocks), so $c$ trades retrieval-server storage
  ($c\cdot n$) against both communication and client time, but only through $\log_2 c$: going from
  16 GiB to 256 GiB of storage halves $s$ once more (45 → 23). The server time does not depend on $s$
  (the compute server only reads $X$).
- Against SimplePIR's whole client (27.5–33.0 ms): RC-PIR's client (0.6–10.7 ms) is faster for every $c$
  and record size, by 3× at $c=2$ with records up to 1 KiB and by 19–26× at $c=16$.
- **Note: SimplePIR's client time was probably not optimized**, so these client comparisons favour
  RC-PIR more than a tuned SimplePIR client would. Timing the steps of their `Query` with their own
  functions (64-byte records, `simplepir-query-split/`, `results/simplepir_query_split.txt`): of
  24–26 ms, 19–20 ms (≈ 78%) is drawing the error vector (30339 discrete-Gaussian samples, their
  `GaussSample`: rejection sampling that needs ≈ 16 tries per sample and creates a new random-number
  generator for every sample), and only 5–6 ms is the LWE product $A\cdot s$ (124 MB of $A$). Their
  work, as far as we can tell, focuses on server throughput; we did not write a faster sampler, so we
  report their client as is. With a fast sampler their query would approach the 5–6 ms of $A\cdot s$
  (an estimate, not measured), so their whole client would take ≈ 10–13 ms for records up to 1 KiB:
  about as fast as RC-PIR's at $c=2$ (10.1–10.7 ms), and still slower than RC-PIR's at $c\ge4$
  (0.8–5.2 ms). In the other direction, their benchmark keeps $A$ in memory and does not time
  generating it.

### Compute server: time per query (ms) for shape $2^{19}\times$2 KiB, by batch size $k$ (run on 2026-10-15)

| threads | k=1 | 2 | 4 | 8 | 16 | 32 | 64 |
|---|---|---|---|---|---|---|---|
| 1 | 24.2 | 17.2 | 10.9 | 7.3 | 6.9 | 7.9 | 10.5 |
| 8 | 7.2 | 5.0 | 3.0 | 1.6 | 0.94 | 0.98 | 1.5 |
| 28 | 6.9 | 4.9 | 3.1 | 1.6 | 0.81 | 0.79 | 0.89 |

### Observations
- From 8 threads one query is memory bound (≈77 GB/s for half of 1 GiB); 28 threads do not help
  at $k=1$. SimplePIR's benchmarks are single-threaded only.
- Batching: a batch of $k$ reads a fraction $1-2^{-k}$ of $X$, so the gain from skipping fades,
  but the pass is shared. Best per-query time: 6.9 ms (1 thread, $k=16$), 0.79 ms (28 threads,
  $k=32$). Beyond that the accumulators no longer fit in cache and the time per query rises.
  (SimplePIR's batch benchmark is not comparable: their batch splits the database into chunks,
  one query per chunk.)
- Shape: wide columns are faster single-threaded (19.4 ms for $2^{17}\times$8 KiB vs 26.1 ms for
  $2^{20}\times$1 KiB) but cost more communication (B1); multi-threaded the shapes are within 10%.
- SimplePIR on this machine (≈ 22 GiB/s, main table) is about 2× its paper number (10 GB/s/core on
  c5n.metal), so only same-machine comparisons are meaningful.

### Preprocessing (B4): full encoder run, 1 GiB, RTX 4070 SUPER

One complete run of `rcpir-encode --device cuda --c C --yes` per $c$ on a random 1 GiB `DB.jsonl`
(shapes as in the table), verify on (spot check of 1000 columns). Step times from timestamped log lines
(`results/encode.md` also lists the attack costs).

| $c$ | $t$ | $m$ | $s$ | $\lambda'$ | min attack (bits) | $R=XH$ (all panels) | $r$-digest + verify | total wall | peak RAM | $R$ on disk | shards |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | $2^{20}$ | $2^{21}$ | 180 | 180 | 180.0 | 112 s | 125 s | 4 min 05 s | 4.0 GiB | 2 GiB | 32 |
| 4 | $2^{20}$ | $2^{22}$ | 90 | 180 | 180.0 | 223 s | 123 s | 5 min 56 s | 4.0 GiB | 4 GiB | 64 |
| 8 | $2^{19}$ | $2^{22}$ | 60 | 179 | 180.0 | 258 s | 71 s | 5 min 36 s | 4.1 GiB | 8 GiB | 128 |
| 16 | $2^{19}$ | $2^{23}$ | 45 | 179 | 180.0 | 533 s | 78 s | 10 min 19 s | 3.9 GiB | 16 GiB | 256 |

- Security: Mode A of the encoder; in every run the cheapest attack (Prange) costs $\ge\lambda'
  = \lambda+\log_2 Q+\lceil\log_2 t\rceil$ with $\lambda=128$, $Q=2^{32}$ (`docs/lpn_parameters.md`).
- Scan, report and packing `X.bin` take ≤ 9 s together. $R=XH$ (PRG on the CPU, 1-bit GPU kernel,
  shard writes, not overlapped) runs at $n\cdot m$ / time ≈ $1.4$–$1.6\cdot10^{14}$ bit operations/s,
  so it grows linearly with $m$.
- Verify is the second largest step: ≈120 s at $t=2^{20}$, ≈70 s at $t=2^{19}$ (`docs/encoder.md` §2
  estimates ~20 s for 1 GiB). Three separate reruns of `verify()` on the $c=4$ output took 119–128 s.
