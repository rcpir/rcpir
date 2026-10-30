# Benchmarks with LPN parameters from the LPN estimator

The benchmarks in `../results/` use the spec's parameter selection (`docs/lpn_parameters.md` §3):
$s\log_2 c \ge \lambda' = \lambda + \log_2 Q + \lceil\log_2 t\rceil$, a lower bound that counts Prange
iterations but no work per iteration. Here $s$ is instead the smallest noise weight for which the LPN
estimator of Yu, Yang, Wang et al. ([lpnestimator.com](https://lpnestimator.com)) reaches the target,
for dual exact LPN ($H\in\mathbb{F}_2^{t\times m}$, fixed-weight noise): the minimum over its attacks
(Pooled Gauss, SD, SD 2.0, SD-ISD, BJMM-ISD), as its `analysisfordual2`. The spec's MITM and
brute-force conditions must hold too (the estimator does not cover them). Code:
`../lpn_estimator.py`; estimator: the float version in github.com/shachy12/Code_estimators,
commit 82a6b00 (results within $1.2\cdot10^{-13}$ bits of the original, 1000× faster).

| Folder | Target | Meaning |
|---|---|---|
| `../results/` | spec: $s\log_2 c \ge \lambda'$ | the published benchmarks (unchanged) |
| `lambda_eff/` | estimator $\ge \lambda' = 128 + 32 + \lceil\log_2 t\rceil$ | the spec's 128-bit level with its margins for $Q=2^{32}$ queries and the $t$ possible indices, measured by the estimator instead of the lower bound |
| `128/` | estimator $\ge 128$ | a single LPN instance at 128 bits, **without** those margins: less conservative than the spec's threat model |

Each folder has the same files as `../results/` for RC-PIR: `comm_shapes.json` (the selected
parameters and shapes), `server_records.jsonl`, `client_records.jsonl` and the full report `comm.md`.
SimplePIR/DoublePIR numbers are read from `../results/` (they do not depend on our parameters).

## Reproduce

From the repository root, one command at a time (the estimator in `~/projects/Code_estimators`, or set
`LPN_ESTIMATOR`; the client built with `(cd client && npm install && npm run build)`):

```bash
T=lambda_eff   # or 128
D=benchmarks/results_estimator/$T
RCPIR_LPN=estimator RCPIR_LPN_TARGET=$T RCPIR_RESULTS=$D python3 benchmarks/comm.py > $D/comm.md   # parameters
RESULTS_DIR=results_estimator/$T benchmarks/run_server.sh records                                  # server
SHAPES=$D/comm_shapes.json node benchmarks/bench_client.mjs > $D/client_records.jsonl             # client
RCPIR_LPN=estimator RCPIR_LPN_TARGET=$T RCPIR_RESULTS=$D python3 benchmarks/comm.py > $D/comm.md   # report
```

Without these variables the scripts behave as before (`comm.py` reproduces `../results/comm.md` byte
for byte).

## Results (run on 2026-10-30, each benchmark alone, threads not pinned)

Each cell: spec / estimator $\ge\lambda'$ / estimator $\ge 128$. Estimated bits are the estimator's
for the selected $s$; online = all traffic of one query; client = Node, one query, no network;
"queries until SimplePIR is cheaper" as in `../results/comm.md` (SimplePIR's hint and online
communication are unchanged).

### $c = 16$ (16 GiB of retrieval storage)

| Record size | $s$ | Estimated bits | Online (KiB) | Queries until SimplePIR is cheaper | Client (ms) |
|---|---|---|---|---|---|
| 1 bit – 1 KiB | 45 / 36 / 23 | 215 / 181 / 132 | 156.5 / 138.4 / 112.3 | never / never / never | 1.6–1.7 / 1.4–1.5 / 0.9–1.0 |
| 4 KiB | 45 / 37 / 23 | 212 / 182 / 129 | 216.5 / 184.4 / 128.2 | never / never / never | 1.36 / 1.16 / 0.72 |
| 8 KiB | 45 / 37 / 24 | 209 / 179 / 129 | 384.5 / 320.4 / 216.3 | 940 / 1,663 / never | 1.17 / 1.05 / 0.72 |
| 16 KiB | 44 / 38 / 25 | 203 / 180 / 130 | 728.5 / 632.4 / 424.3 | 346 / 432 / 939 | 1.10 / 1.01 / 0.68 |
| 64 KiB | 44 / 39 / 27 | 194 / 176 / 131 | 2882 / 2562 / 1794 | 83 / 94 / 142 | 1.35 / 1.22 / 0.88 |

### $c = 2$ (2 GiB) and $c = 256$ (256 GiB)

| Record size | $c$ | $s$ | Online (KiB) | Queries until SimplePIR is cheaper | Client (ms) |
|---|---|---|---|---|---|
| 1 KiB | 2 | 180 / 144 / 89 | 310.9 / 274.5 / 218.9 | 1,600 / 3,073 / never | 10.7 / 9.4 / 5.3 |
| 16 KiB | 2 | 176 / 152 / 101 | 2842 / 2458 / 1641 | 64 / 75 / 119 | 4.11 / 3.81 / 2.46 |
| 64 KiB | 2 | 174 / 157 / 109 | 11204 / 10116 / 7043 | 20 / 22 / 32 | 4.70 / 4.43 / 3.09 |
| 1 KiB | 256 | 23 / 18 / 12 | 112.3 / 102.2 / 84.1 | never / never / never | 0.85 / 0.72 / 0.42 |
| 16 KiB | 256 | 22 / 19 / 13 | 376.2 / 328.2 / 232.1 | 1,287 / 2,049 / never | 0.58 / 0.53 / 0.39 |
| 64 KiB | 256 | 22 / 20 / 15 | 1474 / 1346 / 1026 | 180 / 202 / 288 | 0.71 / 0.61 / 0.50 |

All record sizes and $c\in\{2,4,8,16,256\}$: `lambda_eff/comm.md`, `128/comm.md`.

- **The spec is conservative:** its parameters have 190–219 estimated bits against a target of
  174–180. With the margins kept (`lambda_eff/`), $s$ drops by 9–22%, online communication by
  9–17% and client time by 4–21% (over all 40 configurations); no shape changes.
- **Without the margins** (`128/`), $s$ drops by 32–51%; online communication by 25–44% and client
  time by 30–65%. At $c = 4$ and $c = 256$ the smaller $s$ moves small records to
  blocks twice as large ($t$ halves; 8 of the 40 configurations). At $c = 256$ with small records the
  spec's MITM condition, not the estimator, sets $s$.
- **Server time does not depend on $s$** (the compute server only reads $X$); it was re-measured on
  the same shapes and differs from `../results/` by run-to-run noise (up to 8%).

## RC-PIR for every storage factor $c$ (`comm.md` §1b of each folder)

As the table "RC-PIR for every storage factor $c$" in `../README.md`, with the estimator's parameters;
the column header gives $c$ and the resulting storage on the retrieval server.

**How to read a cell**, e.g. "275 KiB / 3,073" (margins kept, $c=2$, 1 KiB records):
- **Before the slash: RC-PIR's online communication per query**, 275 KiB (best number of records per
  block for that $c$).
- **After the slash: the number of queries until SimplePIR is cheaper.** A SimplePIR client pays
  235 KiB per query, 40 KiB less than RC-PIR, but first downloads a 118.5 MiB (121,380 KiB) hint. It
  catches up after 121,380 / 39.5 ≈ 3,073 queries. "never": RC-PIR is also cheaper per query, so
  SimplePIR never catches up. Same assumptions as in `../README.md`.

### Estimator $\ge \lambda'$ (margins kept, `lambda_eff/`)

| Record size | c = 2 (2 GiB) | c = 4 (4 GiB) | c = 8 (8 GiB) | c = 16 (16 GiB) | c = 256 (256 GiB) |
|---|---|---|---|---|---|
| 1 bit | 275 KiB / 3,582 | 201 KiB / never | 163 KiB / never | 138 KiB / never | 102 KiB / never |
| 64 B | 275 KiB / 3,160 | 201 KiB / never | 163 KiB / never | 138 KiB / never | 102 KiB / never |
| 256 B | 275 KiB / 3,076 | 201 KiB / never | 163 KiB / never | 138 KiB / never | 102 KiB / never |
| 1 KiB | 275 KiB / 3,073 | 201 KiB / never | 163 KiB / never | 138 KiB / never | 102 KiB / never |
| 4 KiB | 630 KiB / 316 | 329 KiB / 1,317 | 233 KiB / never | 184 KiB / never | 112 KiB / never |
| 8 KiB | 1,226 KiB / 140 | 617 KiB / 365 | 417 KiB / 772 | 320 KiB / 1,663 | 176 KiB / never |
| 16 KiB | 2,458 KiB / 75 | 1,225 KiB / 170 | 825 KiB / 288 | 632 KiB / 432 | 328 KiB / 2,049 |
| 64 KiB | 10,116 KiB / 22 | 5,059 KiB / 45 | 3,395 KiB / 69 | 2,562 KiB / 94 | 1,346 KiB / 202 |

### Estimator $\ge 128$ (single instance, no margins, `128/`)

| Record size | c = 2 (2 GiB) | c = 4 (4 GiB) | c = 8 (8 GiB) | c = 16 (16 GiB) | c = 256 (256 GiB) |
|---|---|---|---|---|---|
| 1 bit | 219 KiB / never | 156 KiB / never | 126 KiB / never | 112 KiB / never | 84 KiB / never |
| 64 B | 219 KiB / never | 156 KiB / never | 126 KiB / never | 112 KiB / never | 84 KiB / never |
| 256 B | 219 KiB / never | 156 KiB / never | 126 KiB / never | 112 KiB / never | 84 KiB / never |
| 1 KiB | 219 KiB / never | 156 KiB / never | 126 KiB / never | 112 KiB / never | 84 KiB / never |
| 4 KiB | 417 KiB / 682 | 224 KiB / never | 160 KiB / never | 128 KiB / never | 84 KiB / never |
| 8 KiB | 809 KiB / 242 | 417 KiB / 772 | 280 KiB / 3,200 | 216 KiB / never | 120 KiB / never |
| 16 KiB | 1,641 KiB / 119 | 825 KiB / 288 | 552 KiB / 545 | 424 KiB / 939 | 232 KiB / never |
| 64 KiB | 7,043 KiB / 32 | 3,459 KiB / 68 | 2,370 KiB / 103 | 1,794 KiB / 142 | 1,026 KiB / 288 |

- SimplePIR's hint and online communication are those of `../results/`. DoublePIR is not shown: it is
  cheaper for no $c$ and record size (also with these parameters).
- Records per block, and so the server time, are those of $c = 16$ except for records up to 1 KiB:
  with margins kept at $c = 2$ and $c = 4$ (1032-byte blocks, 26.6 ms instead of 24.4 ms); at 128 bits
  at $c = 2$ (1032-byte blocks, 26.9 ms instead of 23.7 ms) and at $c = 256$ (4104-byte blocks,
  22.0 ms instead of 23.7 ms).
- Compared with the spec (`../README.md`): with margins kept, small records at $c = 2$ need about
  3,100–3,600 queries before SimplePIR is cheaper (spec: 1,600–1,750), and $c = 8$ is cheaper per query
  up to 4 KiB (spec: up to 1 KiB). At 128 bits RC-PIR is cheaper per query for records up to 1 KiB at
  every $c$, and at $c = 256$ up to 16 KiB; at 64 KiB SimplePIR is still cheaper after 32–288 queries.

## Caveats

- The estimator models single-instance attacks with a specific cost per iteration; it is a model,
  not a proof. `lambda_eff/` keeps the spec's margins on top of it; `128/` drops them, which the spec's
  threat model (up to $2^{32}$ queries per $H$) does not cover.
- The estimator's repository has no license; the fork is used here as an external tool, not shipped.
- The encoder still uses the spec's selection; these results only show what the estimator would change.
