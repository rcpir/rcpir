# Benchmarks: RC-PIR vs SimplePIR/DoublePIR (1 GiB database)

| Script | Benchmark | Output |
|---|---|---|
| `python3 comm.py` | B1: communication and storage (analytic, encoder's LPN parameter selection, $\lambda=128$) | `results/comm.md` |
| `./run_server.sh` | B2/B3: compute-server time per pass over shape, threads and batch size (`server-bench/`, calls `CpuBackend` directly, no HTTP) | `results/server.jsonl` |
| `./bench_encode.sh`, `python3 encode_report.py` | B4: full preprocessing of a 1 GiB DB with the real encoder CLI (`--device cuda`, verify on), $c=2,4,8,16$; needs the repo's `.env` with CuPy | `results/encode_c*.log`, `results/encode.md` |
| `node bench_client.mjs` | B5: client time per query in Node, no network (sample $S$, build $q_c$, decode); needs `(cd ../client && npm install && npm run build)` | `results/client.jsonl` |
| `./run_simplepir.sh [recover\|batch]` | SimplePIR/DoublePIR with the authors' own benchmarks (pinned commit, $2^{33}\times$1-bit entries, single thread) | `results/*pir_*.txt` |

Throughput is defined as in SimplePIR: database size × queries / server time. The retrieval
server does no computation and is not measured here.

Machine: i7-14700KF (8P + 12E, 28 threads, AVX2), 31 GB RAM, WSL2. Threads are not pinned.

## Results
Run on 2026-10-15. SimplePIR/DoublePIR: the 5 answer times in their logs (mean, min); they are
noisy (SimplePIR 46–64 ms, DoublePIR 56–109 ms), probably because the unpinned thread sometimes
runs on an E-core. Ours: 10 passes with fresh random queries (std < 3%), shape
$t\times\ell = 2^{19}\times 2^{14}$ bits (B1-optimal for $c=16$). Throughput = $2^{33}$ bits /
mean time for all rows (SimplePIR prints 20.1 / 14.8 "GB/s" because it counts its packed
database, 1075 / 1036 MiB).

### 1 GiB, one query, single thread

| Scheme | Offline download (hint) | Online up | Online down | Server storage | Server time mean (min) | Throughput |
|---|---|---|---|---|---|---|
| SimplePIR | 120.7 MiB | 120 KiB | 120 KiB | 1 GiB (+ hint) | 53.2 ms (45.8) | 19.3 GiB/s |
| DoublePIR | 16 MiB | 312 KiB | 32 KiB | 1 GiB (+ hint) | 73.7 ms (55.8) | 13.9 GiB/s |
| RC-PIR, $c=2$ | none | 128.5 KiB | 181 KiB | 1 GiB + 2 GiB static | 26.1 ms ($t=2^{20}$) | 38.3 GiB/s |
| RC-PIR, $c=4$ | none | 128.2 KiB | 91 KiB | 1 GiB + 4 GiB static | 26.1 ms ($t=2^{20}$) | 38.3 GiB/s |
| RC-PIR, $c=8$ | none | 64.2 KiB | 122 KiB | 1 GiB + 8 GiB static | 24.2 ms | 41.3 GiB/s |
| RC-PIR, $c=16$ | none | 64.1 KiB | 92 KiB | 1 GiB + 16 GiB static | 24.2 ms | 41.3 GiB/s |

RC-PIR server time and throughput are those of the compute server; "online up" adds the
compute query and the $s$ retrieval addresses (analytic, $s\lceil\log_2 m\rceil$ bits; real HTTP
requests are larger), "online down" adds $X q_c$ and the $s$ retrieved columns. All $c$ in
`results/comm.md`.

### Compute server: time per query (ms) for shape $2^{19}\times$2 KiB, by batch size $k$

| threads | k=1 | 2 | 4 | 8 | 16 | 32 | 64 |
|---|---|---|---|---|---|---|---|
| 1 | 24.2 | 17.2 | 10.9 | 7.3 | 6.9 | 7.9 | 10.5 |
| 8 | 7.2 | 5.0 | 3.0 | 1.6 | 0.94 | 0.98 | 1.5 |
| 28 | 6.9 | 4.9 | 3.1 | 1.6 | 0.81 | 0.79 | 0.89 |

### Observations
- Single thread, one query: RC-PIR is ≈2.2× faster than SimplePIR and ≈3× faster than DoublePIR
  (≈1.9× and ≈2.3× against their best runs). A query reads about
  half of $X$ (columns with $q_j=0$ are skipped) and only XORs; SimplePIR reads all of it and
  multiplies by 32-bit values.
- From 8 threads one query is memory bound (≈77 GB/s for half of 1 GiB); 28 threads do not help
  at $k=1$. SimplePIR's benchmarks are single-threaded only.
- Batching: a batch of $k$ reads a fraction $1-2^{-k}$ of $X$, so the gain from skipping fades,
  but the pass is shared. Best per-query time: 6.9 ms (1 thread, $k=16$), 0.79 ms (28 threads,
  $k=32$). Beyond that the accumulators no longer fit in cache and the time per query rises.
  (SimplePIR's batch benchmark is not comparable: their batch splits the database into chunks,
  one query per chunk; it is not run by default.)
- Shape: wide columns are faster single-threaded (19.4 ms for $2^{17}\times$8 KiB vs 26.1 ms for
  $2^{20}\times$1 KiB) but cost more communication (B1); multi-threaded the shapes are within 10%.
- SimplePIR on this machine is 2× its paper number (10 GB/s/core on c5n.metal), so only
  same-machine comparisons are meaningful.

### Client time per query (B5, Node 24, single thread, 100 runs)

| Scheme | Build query | Decode | Total |
|---|---|---|---|
| SimplePIR (Go) | 26.8 ms | 7.1 ms (6.7) | 33.9 ms |
| DoublePIR (Go) | 86.6 ms | 128.9 ms (122.6) | 215.5 ms |
| RC-PIR, $c=2$ ($t=2^{20}$, $s=180$, $L=1$ KiB) | 37.2 ms | 0.26 ms | 37.6 ms |
| RC-PIR, $c=4$ ($t=2^{20}$, $s=90$, $L=1$ KiB) | 19.1 ms | 0.14 ms | 19.3 ms |
| RC-PIR, $c=8$ ($t=2^{19}$, $s=60$, $L=2$ KiB) | 6.9 ms | 0.17 ms | 7.1 ms |
| RC-PIR, $c=16$ ($t=2^{19}$, $s=45$, $L=2$ KiB) | 5.1 ms | 0.12 ms | 5.2 ms |

Sampling $S$ takes ≤ 0.2 ms. Building $q_c$ expands $s$ columns of $H$ ($s\cdot t/8$ bytes of AES-CTR
keystream: 22.5 MiB at $c=2$, 11.25 MiB at $c=4$, 3.75 MiB at $c=8$, 2.8 MiB at $c=16$) and XORs them. A separate split of that step: at
$c=4$ about 4.6 ms AES (WebCrypto) and 6.3 ms XOR; at $c=16$ 1.3 ms and 1.6 ms. `xorInto` XORs byte by
byte in JavaScript, so a wider XOR (32-bit words) should shorten the query step.

SimplePIR/DoublePIR: query time from their single-query benchmark (`results/*pir_single.txt`, mean
of 5). Decode = their `Recover`, mean (min) of 3 runs of their full flow `pir.RunPIR` (real hint,
correctness checked; `RunPIR` times each phase separately, so the one-time hint computation,
≈2.6 min per run, is not included), called unmodified from `simplepir-recover/` (`./run_simplepir.sh recover`;
`results/*pir_recover.txt`). SimplePIR's decode computes hint × secret ($\approx 30893\times1024$
products); DoublePIR's also strips the second level. Their client is Go, ours JavaScript.

### Preprocessing (B4): full encoder run, 1 GiB, RTX 4070 SUPER

One complete run of `rcpir-encode --device cuda --c C --yes` per $c$ on a random 1 GiB `DB.jsonl`
(B1 shapes), verify on (spot check of 1000 columns). Step times from timestamped log lines
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
