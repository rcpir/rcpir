n = 2^33 bits (1 GiB), lambda = 128, Q = 2^32. Sizes in KiB unless noted.

LPN parameters: s chosen with the LPN estimator (Code_estimators, lpn_estimator.py): estimator bits >= lambda' = lambda + log2 Q + ceil(log2 t), and the spec's MITM and brute-force conditions.

## 1. Retrieving one fixed-size record (RC-PIR with c = 16, best number of records per block)

- Hint: one-time download before the first query (SimplePIR/DoublePIR only).
- Online: upload + download of one query; for RC-PIR compute up + down + retrieval up + down.
- RC-PIR storage: $R = XH$ on the retrieval server (≈ c × database), written once by the encoder. Clients never download it, so it does not enter any other column. Besides it, the compute server holds the database itself, as SimplePIR/DoublePIR servers do.
- SimplePIR/DoublePIR sizes: their `GetBW` (`results/bw_sweep/`), layout chosen by their `PickParams`.
- Queries until SimplePIR (DoublePIR) is cheaper: after N queries a SimplePIR (DoublePIR) client has downloaded hint + N × online, an RC-PIR client N × online; RC-PIR's total is smaller up to this many queries, beyond it the hint has paid for itself: hint / (RC-PIR online − SimplePIR online). "never": RC-PIR is also cheaper per query. Assumptions: each client downloads the hint once and reuses it for all its queries; the database does not change (after an update SimplePIR/DoublePIR clients download a new hint, so the count holds per database version); communication only (the server's time to compute the hint, measured 2.5–2.7 min for SimplePIR at every record size of the sweep and 2.8 min for DoublePIR with 1-bit entries, and the client's storage for it are not counted); upload and download are added, the hint counts as download.
- Server time: one query, one thread, mean (throughput = 1 GiB of records / mean time). SimplePIR/DoublePIR: the 5 answer times of their `*PirSingle` benchmark (`results/time_sweep/`); RC-PIR: compute server, 10 passes on the shape of this row (`results_estimator/lambda_eff/server_records.jsonl`). The retrieval server only serves static byte ranges and is not timed.
- Throughput: 1 GiB of records / mean server time, as in SimplePIR.

| record size | RC-PIR records per block | SimplePIR hint | DoublePIR hint | RC-PIR storage | SimplePIR online | DoublePIR online | RC-PIR online | queries until SimplePIR is cheaper | queries until DoublePIR is cheaper | SimplePIR server time | DoublePIR server time | RC-PIR server time | SimplePIR throughput | DoublePIR throughput | RC-PIR throughput |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 bit | 16384 | 120.7 MiB | 16 MiB | 16.1 GiB | 240 KiB | 344 KiB | 138.4 KiB | never | never | 45.8 ms | 55.5 ms | 24.4 ms | 21.8 GiB/s | 18.0 GiB/s | 41.0 GiB/s |
| 64 B | 32 | 118.8 MiB | 912 MiB | 16.1 GiB | 236 KiB | 2.0 MiB | 138.4 KiB | never | never | 43.8 ms | 65.9 ms | 24.4 ms | 22.8 GiB/s | 15.2 GiB/s | 41.0 GiB/s |
| 256 B | 8 | 118.7 MiB | 3.5 GiB | 16.1 GiB | 235 KiB | 7.3 MiB | 138.4 KiB | never | never | 44.5 ms | 63.1 ms | 24.4 ms | 22.5 GiB/s | 15.8 GiB/s | 41.0 GiB/s |
| 1 KiB | 2 | 118.5 MiB | 14.1 GiB | 16.1 GiB | 235 KiB | 28.4 MiB | 138.4 KiB | never | never | 44.7 ms | 68.2 ms | 24.4 ms | 22.4 GiB/s | 14.7 GiB/s | 41.0 GiB/s |
| 4 KiB | 1 | 121.9 MiB | 56.2 GiB | 16.0 GiB | 234 KiB | 112.7 MiB | 184.4 KiB | never | never | 42.8 ms | 92.3 ms | 22.1 ms | 23.4 GiB/s | 10.8 GiB/s | 45.2 GiB/s |
| 8 KiB | 1 | 135.4 MiB | 112.4 GiB | 16.0 GiB | 237 KiB | 225.2 MiB | 320.4 KiB | 1,663 | never | 44.6 ms | 101.4 ms | 20.6 ms | 22.4 GiB/s | 9.9 GiB/s | 48.5 GiB/s |
| 16 KiB | 1 | 162.5 MiB | 224.9 GiB | 16.0 GiB | 247 KiB | 450.2 MiB | 632.4 KiB | 432 | never | 44.0 ms | 155.4 ms | 20.8 ms | 22.7 GiB/s | 6.4 GiB/s | 48.1 GiB/s |
| 64 KiB | 1 | 211.1 MiB | 899.4 GiB | 16.0 GiB | 275 KiB | 1.8 GiB | 2.5 MiB | 94 | never | 44.1 ms | killed in Setup¹ | 23.1 ms | 22.7 GiB/s | – | 43.3 GiB/s |

¹ Killed during their `Setup` with nothing else running (31 GB RAM); the matrix is padded to 57561 × 65536 elements. Most likely out of memory.

## 1b. RC-PIR for every storage factor c: online communication / queries until SimplePIR is cheaper

Each cell: RC-PIR online communication per query (best number of records per block for that c), then, after the slash, the number of queries until SimplePIR is cheaper (as in table 1): SimplePIR hint / (RC-PIR online − SimplePIR online). "never": RC-PIR is also cheaper per query. Header: c and the retrieval-server storage. SimplePIR's hint and online communication are those of table 1; DoublePIR is cheaper for no c and record size.

| record size | c = 2 (2 GiB) | c = 4 (4 GiB) | c = 8 (8 GiB) | c = 16 (16 GiB) | c = 256 (256 GiB) |
|---|---|---|---|---|---|
| 1 bit | 275 KiB / 3,582 | 201 KiB / never | 163 KiB / never | 138 KiB / never | 102 KiB / never |
| 64 B | 275 KiB / 3,160 | 201 KiB / never | 163 KiB / never | 138 KiB / never | 102 KiB / never |
| 256 B | 275 KiB / 3,076 | 201 KiB / never | 163 KiB / never | 138 KiB / never | 102 KiB / never |
| 1 KiB | 275 KiB / 3,073 | 201 KiB / never | 163 KiB / never | 138 KiB / never | 102 KiB / never |
| 4 KiB | 630 KiB / 316 | 329 KiB / 1,317 | 233 KiB / never | 184 KiB / never | 112 KiB / never |
| 8 KiB | 1,226 KiB / 140 | 617 KiB / 365 | 417 KiB / 772 | 320 KiB / 1,663 | 176 KiB / never |
| 16 KiB | 2,458 KiB / 75 | 1,225 KiB / 170 | 825 KiB / 288 | 632 KiB / 432 | 328 KiB / 2,049 |
| 64 KiB | 10,116 KiB / 22 | 5,059 KiB / 45 | 3,395 KiB / 69 | 2,562 KiB / 94 | 1,346 KiB / 202 |

Records per block (and so the server time) differ from table 1 (c = 16) only for c = 2: 1 bit (8192 instead of 16384, server time 26.6 ms instead of 24.4 ms), 64 B (16 instead of 32, server time 26.6 ms instead of 24.4 ms), 256 B (4 instead of 8, server time 26.6 ms instead of 24.4 ms), 1 KiB (1 instead of 2, server time 26.6 ms instead of 24.4 ms); c = 4: 1 bit (8192 instead of 16384, server time 26.6 ms instead of 24.4 ms), 64 B (16 instead of 32, server time 26.6 ms instead of 24.4 ms), 256 B (4 instead of 8, server time 26.6 ms instead of 24.4 ms), 1 KiB (1 instead of 2, server time 26.6 ms instead of 24.4 ms). Otherwise the server times of table 1 hold for every c.

## 1c. Runtime per query for every storage factor c (best number of records per block for that c)

- Server time: compute server, one query, one thread (as in table 1; it depends only on the block shape, not on c). SimplePIR: table 1.
- Client time: RC-PIR client in Node, single thread, no network, mean of 100 queries: sample S, build the compute query (expand s columns of H, XOR), decode (XOR s + 1 blocks). Each configuration runs in its own Node process (`bench_client.mjs records`, `results_estimator/lambda_eff/client_records.jsonl`).
- SimplePIR/DoublePIR client: their Go client. Query build from the `*PirSingle` logs (mean of 5); SimplePIR decode = their `Recover` in their full flow `RunPIR` with the real hint, mean of 3 runs, each run alone (`./run_simplepir.sh recover-sweep`, `results/recover_sweep/`). DoublePIR decode only for 1-bit entries (its hint is 912 MiB to 899 GiB at the other record sizes).

| record size | server, c = 2 | server, c = 4 | server, c = 8 | server, c = 16 | server, c = 256 | SimplePIR server | client, c = 2 | client, c = 4 | client, c = 8 | client, c = 16 | client, c = 256 | SimplePIR client (query build + decode) | DoublePIR client (query build + decode) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 bit | 26.6 ms | 26.6 ms | 24.4 ms | 24.4 ms | 24.4 ms | 45.8 ms | 9.2 ms | 4.1 ms | 2.0 ms | 1.4 ms | 0.8 ms | 32.6 ms (25.7 + 7.0) | 202.9 ms (66.1 + 136.8) |
| 64 B | 26.6 ms | 26.6 ms | 24.4 ms | 24.4 ms | 24.4 ms | 43.8 ms | 9.8 ms | 4.0 ms | 2.0 ms | 1.5 ms | 0.7 ms | 32.1 ms (25.7 + 6.4) | 55.7 ms + decode n/a |
| 256 B | 26.6 ms | 26.6 ms | 24.4 ms | 24.4 ms | 24.4 ms | 44.5 ms | 9.2 ms | 4.2 ms | 2.0 ms | 1.5 ms | 0.8 ms | 30.4 ms (25.1 + 5.3) | 55.6 ms + decode n/a |
| 1 KiB | 26.6 ms | 26.6 ms | 24.4 ms | 24.4 ms | 24.4 ms | 44.7 ms | 9.4 ms | 4.3 ms | 2.0 ms | 1.5 ms | 0.7 ms | 33.0 ms (26.1 + 6.9) | 54.5 ms + decode n/a |
| 4 KiB | 22.1 ms | 22.1 ms | 22.1 ms | 22.1 ms | 22.1 ms | 42.8 ms | 4.5 ms | 2.2 ms | 1.5 ms | 1.2 ms | 0.6 ms | 31.8 ms (24.7 + 7.1) | 55.6 ms + decode n/a |
| 8 KiB | 20.6 ms | 20.6 ms | 20.6 ms | 20.6 ms | 20.6 ms | 44.6 ms | 4.0 ms | 2.0 ms | 1.4 ms | 1.1 ms | 0.6 ms | 30.7 ms (22.0 + 8.6) | 57.2 ms + decode n/a |
| 16 KiB | 20.8 ms | 20.8 ms | 20.8 ms | 20.8 ms | 20.8 ms | 44.0 ms | 3.8 ms | 1.9 ms | 1.3 ms | 1.0 ms | 0.5 ms | 27.5 ms (18.2 + 9.3) | 54.5 ms + decode n/a |
| 64 KiB | 23.1 ms | 23.1 ms | 23.1 ms | 23.1 ms | 23.1 ms | 44.1 ms | 4.4 ms | 2.2 ms | 1.6 ms | 1.2 ms | 0.6 ms | 27.7 ms (14.3 + 13.4) | n/a |

## 2. SimplePIR/DoublePIR layouts chosen by their `PickParams`

Matrix of rows × columns over $\mathbb{Z}_p$; a record takes Ne (elements per record) consecutive elements of one column (9–10 bits each), so a column holds rows / Ne records; 1-bit entries are packed several per element (their packing factor), so a column holds rows × packing. DoublePIR: their `SetupDB` sets X = Ne, so its hint ($\delta X n^2$ elements) and download grow linearly with the record size; for 64 KiB records its $m \ge$ `COMP_RATIO`$\cdot n = 65536$ columns exceed the $2^{14}$ records, so the matrix is padded to 4 GB.

| record size | scheme | rows | columns | p | Ne | records per column | packed DB | hint | up | down |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 bit | SimplePIR | 30893 | 30895 | 701 | 1 | 278037 | 1076 MB | 120.7 MiB | 120 | 120 |
| 1 bit | DoublePIR | 14564 | 65536 | 552 | 1 | 131076 | 1036 MB | 16 MiB | 312 | 32 |
| 64 B | SimplePIR | 30415 | 30339 | 701 | 55 | 553 | 1040 MB | 118.8 MiB | 118 | 118 |
| 64 B | DoublePIR | 14592 | 65536 | 552 | 57 | 256 | 1038 MB | 912 MiB | 257 | 1824 |
| 256 B | SimplePIR | 30380 | 29960 | 701 | 217 | 140 | 1026 MB | 118.7 MiB | 117 | 118 |
| 256 B | DoublePIR | 14400 | 65536 | 552 | 225 | 64 | 1025 MB | 3.5 GiB | 256 | 7203 |
| 1 KiB | SimplePIR | 30345 | 29960 | 701 | 867 | 35 | 1025 MB | 118.5 MiB | 117 | 118 |
| 1 KiB | DoublePIR | 14400 | 65536 | 552 | 900 | 16 | 1025 MB | 14.1 GiB | 256 | 28814 |
| 4 KiB | SimplePIR | 31203 | 29128 | 701 | 3467 | 9 | 1024 MB | 121.9 MiB | 113 | 121 |
| 4 KiB | DoublePIR | 14392 | 65536 | 552 | 3598 | 4 | 1024 MB | 56.2 GiB | 256 | 115192 |
| 8 KiB | SimplePIR | 34665 | 26215 | 701 | 6933 | 5 | 1024 MB | 135.4 MiB | 102 | 135 |
| 8 KiB | DoublePIR | 14392 | 65536 | 552 | 7196 | 2 | 1024 MB | 112.4 GiB | 256 | 230384 |
| 16 KiB | SimplePIR | 41598 | 21846 | 701 | 13866 | 3 | 1024 MB | 162.5 MiB | 85 | 162 |
| 16 KiB | DoublePIR | 14391 | 65536 | 552 | 14391 | 1 | 1024 MB | 224.9 GiB | 256 | 460736 |
| 64 KiB | SimplePIR | 54039 | 16384 | 833 | 54039 | 1 | 1024 MB | 211.1 MiB | 64 | 211 |
| 64 KiB | DoublePIR | 57561 | 65536 | 552 | 57561 | 1 | 4096 MB | 899.4 GiB | 256 | 1842851 |

## 3. RC-PIR by record size and c: best number of records per block vs one record per block

t = number of blocks, L = block size (4-byte header + records, rounded up to 8 bytes), s = blocks fetched from the retrieval server.

| record size | c | records per block | t | L (bytes) | s | storage | compute up | compute down | retrieval up | retrieval down | total | total with one record per block |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 bit | 2 | 8192 | 2^20 | 1032 | 144 | 2.0 GiB | 128.0 | 1.0 | 0.4 | 145.1 | 274.5 | infeasible |
| 1 bit | 4 | 8192 | 2^20 | 1032 | 71 | 4.0 GiB | 128.0 | 1.0 | 0.2 | 71.6 | 200.8 | infeasible |
| 1 bit | 8 | 16384 | 2^19 | 2056 | 48 | 8.0 GiB | 64.0 | 2.0 | 0.1 | 96.4 | 162.5 | infeasible |
| 1 bit | 16 | 16384 | 2^19 | 2056 | 36 | 16.1 GiB | 64.0 | 2.0 | 0.1 | 72.3 | 138.4 | infeasible |
| 1 bit | 256 | 16384 | 2^19 | 2056 | 18 | 257 GiB | 64.0 | 2.0 | 0.1 | 36.1 | 102.2 | infeasible |
| 64 B | 2 | 16 | 2^20 | 1032 | 144 | 2.0 GiB | 128.0 | 1.0 | 0.4 | 145.1 | 274.5 | 2058.0 |
| 64 B | 4 | 16 | 2^20 | 1032 | 71 | 4.0 GiB | 128.0 | 1.0 | 0.2 | 71.6 | 200.8 | 2053.0 |
| 64 B | 8 | 32 | 2^19 | 2056 | 48 | 8.0 GiB | 64.0 | 2.0 | 0.1 | 96.4 | 162.5 | 2051.4 |
| 64 B | 16 | 32 | 2^19 | 2056 | 36 | 16.1 GiB | 64.0 | 2.0 | 0.1 | 72.3 | 138.4 | 2050.5 |
| 64 B | 256 | 32 | 2^19 | 2056 | 18 | 257 GiB | 64.0 | 2.0 | 0.1 | 36.1 | 102.2 | 2049.3 |
| 256 B | 2 | 4 | 2^20 | 1032 | 144 | 2.0 GiB | 128.0 | 1.0 | 0.4 | 145.1 | 274.5 | 548.5 |
| 256 B | 4 | 4 | 2^20 | 1032 | 71 | 4.0 GiB | 128.0 | 1.0 | 0.2 | 71.6 | 200.8 | 530.2 |
| 256 B | 8 | 8 | 2^19 | 2056 | 48 | 8.0 GiB | 64.0 | 2.0 | 0.1 | 96.4 | 162.5 | 524.3 |
| 256 B | 16 | 8 | 2^19 | 2056 | 36 | 16.1 GiB | 64.0 | 2.0 | 0.1 | 72.3 | 138.4 | 521.1 |
| 256 B | 256 | 8 | 2^19 | 2056 | 18 | 257 GiB | 64.0 | 2.0 | 0.1 | 36.1 | 102.2 | 516.7 |
| 1 KiB | 2 | 1 | 2^20 | 1032 | 144 | 2.0 GiB | 128.0 | 1.0 | 0.4 | 145.1 | 274.5 | 274.5 |
| 1 KiB | 4 | 1 | 2^20 | 1032 | 71 | 4.0 GiB | 128.0 | 1.0 | 0.2 | 71.6 | 200.8 | 200.8 |
| 1 KiB | 8 | 2 | 2^19 | 2056 | 48 | 8.0 GiB | 64.0 | 2.0 | 0.1 | 96.4 | 162.5 | 176.5 |
| 1 KiB | 16 | 2 | 2^19 | 2056 | 36 | 16.1 GiB | 64.0 | 2.0 | 0.1 | 72.3 | 138.4 | 165.4 |
| 1 KiB | 256 | 2 | 2^19 | 2056 | 18 | 257 GiB | 64.0 | 2.0 | 0.1 | 36.1 | 102.2 | 147.2 |
| 4 KiB | 2 | 1 | 2^18 | 4104 | 148 | 2.0 GiB | 32.0 | 4.0 | 0.3 | 593.2 | 629.5 | 629.5 |
| 4 KiB | 4 | 1 | 2^18 | 4104 | 73 | 4.0 GiB | 32.0 | 4.0 | 0.2 | 292.6 | 328.8 | 328.8 |
| 4 KiB | 8 | 1 | 2^18 | 4104 | 49 | 8.0 GiB | 32.0 | 4.0 | 0.1 | 196.4 | 232.5 | 232.5 |
| 4 KiB | 16 | 1 | 2^18 | 4104 | 37 | 16.0 GiB | 32.0 | 4.0 | 0.1 | 148.3 | 184.4 | 184.4 |
| 4 KiB | 256 | 1 | 2^18 | 4104 | 19 | 256.5 GiB | 32.0 | 4.0 | 0.1 | 76.1 | 112.2 | 112.2 |
| 8 KiB | 2 | 1 | 2^17 | 8200 | 150 | 2.0 GiB | 16.0 | 8.0 | 0.3 | 1201.2 | 1225.5 | 1225.5 |
| 8 KiB | 4 | 1 | 2^17 | 8200 | 74 | 4.0 GiB | 16.0 | 8.0 | 0.2 | 592.6 | 616.8 | 616.8 |
| 8 KiB | 8 | 1 | 2^17 | 8200 | 49 | 8.0 GiB | 16.0 | 8.0 | 0.1 | 392.4 | 416.5 | 416.5 |
| 8 KiB | 16 | 1 | 2^17 | 8200 | 37 | 16.0 GiB | 16.0 | 8.0 | 0.1 | 296.3 | 320.4 | 320.4 |
| 8 KiB | 256 | 1 | 2^17 | 8200 | 19 | 256.2 GiB | 16.0 | 8.0 | 0.1 | 152.1 | 176.2 | 176.2 |
| 16 KiB | 2 | 1 | 2^16 | 16392 | 152 | 2.0 GiB | 8.0 | 16.0 | 0.3 | 2433.2 | 2457.5 | 2457.5 |
| 16 KiB | 4 | 1 | 2^16 | 16392 | 75 | 4.0 GiB | 8.0 | 16.0 | 0.2 | 1200.6 | 1224.8 | 1224.8 |
| 16 KiB | 8 | 1 | 2^16 | 16392 | 50 | 8.0 GiB | 8.0 | 16.0 | 0.1 | 800.4 | 824.5 | 824.5 |
| 16 KiB | 16 | 1 | 2^16 | 16392 | 38 | 16.0 GiB | 8.0 | 16.0 | 0.1 | 608.3 | 632.4 | 632.4 |
| 16 KiB | 256 | 1 | 2^16 | 16392 | 19 | 256.1 GiB | 8.0 | 16.0 | 0.1 | 304.1 | 328.2 | 328.2 |
| 64 KiB | 2 | 1 | 2^14 | 65544 | 157 | 2.0 GiB | 2.0 | 64.0 | 0.3 | 10049.2 | 10115.5 | 10115.5 |
| 64 KiB | 4 | 1 | 2^14 | 65544 | 78 | 4.0 GiB | 2.0 | 64.0 | 0.2 | 4992.6 | 5058.8 | 5058.8 |
| 64 KiB | 8 | 1 | 2^14 | 65544 | 52 | 8.0 GiB | 2.0 | 64.0 | 0.1 | 3328.4 | 3394.5 | 3394.5 |
| 64 KiB | 16 | 1 | 2^14 | 65544 | 39 | 16.0 GiB | 2.0 | 64.0 | 0.1 | 2496.3 | 2562.4 | 2562.4 |
| 64 KiB | 256 | 1 | 2^14 | 65544 | 20 | 256.0 GiB | 2.0 | 64.0 | 0.1 | 1280.2 | 1346.2 | 1346.2 |
