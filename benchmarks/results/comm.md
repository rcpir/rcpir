n = 2^33 bits (1 GiB), lambda = 128, Q = 2^32. Sizes in KiB unless noted.

## 1. Retrieving one fixed-size record (RC-PIR with c = 16, best number of records per block)

- Hint: one-time download before the first query (SimplePIR/DoublePIR only).
- Online: upload + download of one query; for RC-PIR compute up + down + retrieval up + down.
- RC-PIR storage: $R = XH$ on the retrieval server (≈ c × database), written once by the encoder. Clients never download it, so it does not enter any other column. Besides it, the compute server holds the database itself, as SimplePIR/DoublePIR servers do.
- SimplePIR/DoublePIR sizes: their `GetBW` (`results/bw_sweep/`), layout chosen by their `PickParams`.
- Queries until SimplePIR (DoublePIR) is cheaper: after N queries a SimplePIR (DoublePIR) client has downloaded hint + N × online, an RC-PIR client N × online; RC-PIR's total is smaller up to this many queries, beyond it the hint has paid for itself: hint / (RC-PIR online − SimplePIR online). "never": RC-PIR is also cheaper per query. Assumptions: each client downloads the hint once and reuses it for all its queries; the database does not change (after an update SimplePIR/DoublePIR clients download a new hint, so the count holds per database version); communication only (the server's time to compute the hint, measured 2.5–2.7 min for SimplePIR at every record size of the sweep and 2.8 min for DoublePIR with 1-bit entries, and the client's storage for it are not counted); upload and download are added, the hint counts as download.
- Server time: one query, one thread, mean (throughput = 1 GiB of records / mean time). SimplePIR/DoublePIR: the 5 answer times of their `*PirSingle` benchmark (`results/time_sweep/`); RC-PIR: compute server, 10 passes on the shape of this row (`results/server_records.jsonl`). The retrieval server only serves static byte ranges and is not timed.
- Throughput: 1 GiB of records / mean server time, as in SimplePIR.

| record size | RC-PIR records per block | SimplePIR hint | DoublePIR hint | RC-PIR storage | SimplePIR online | DoublePIR online | RC-PIR online | queries until SimplePIR is cheaper | queries until DoublePIR is cheaper | SimplePIR server time | DoublePIR server time | RC-PIR server time | SimplePIR throughput | DoublePIR throughput | RC-PIR throughput |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 64 B | 32 | 118.8 MiB | 912 MiB | 16.1 GiB | 236 KiB | 2.0 MiB | 156.5 KiB | never | never | 43.8 ms | 65.9 ms | 22.6 ms | 22.8 GiB/s | 15.2 GiB/s | 44.3 GiB/s |
| 256 B | 8 | 118.7 MiB | 3.5 GiB | 16.1 GiB | 235 KiB | 7.3 MiB | 156.5 KiB | never | never | 44.5 ms | 63.1 ms | 22.6 ms | 22.5 GiB/s | 15.8 GiB/s | 44.3 GiB/s |
| 1 KiB | 2 | 118.5 MiB | 14.1 GiB | 16.1 GiB | 235 KiB | 28.4 MiB | 156.5 KiB | never | never | 44.7 ms | 68.2 ms | 22.6 ms | 22.4 GiB/s | 14.7 GiB/s | 44.3 GiB/s |
| 4 KiB | 1 | 121.9 MiB | 56.2 GiB | 16.0 GiB | 234 KiB | 112.7 MiB | 216.5 KiB | never | never | 42.8 ms | 92.3 ms | 20.6 ms | 23.4 GiB/s | 10.8 GiB/s | 48.5 GiB/s |
| 8 KiB | 1 | 135.4 MiB | 112.4 GiB | 16.0 GiB | 237 KiB | 225.2 MiB | 384.5 KiB | 940 | never | 44.6 ms | 101.4 ms | 20.2 ms | 22.4 GiB/s | 9.9 GiB/s | 49.5 GiB/s |
| 16 KiB | 1 | 162.5 MiB | 224.9 GiB | 16.0 GiB | 247 KiB | 450.2 MiB | 728.5 KiB | 346 | never | 44.0 ms | 155.4 ms | 19.6 ms | 22.7 GiB/s | 6.4 GiB/s | 50.9 GiB/s |
| 64 KiB | 1 | 211.1 MiB | 899.4 GiB | 16.0 GiB | 275 KiB | 1.8 GiB | 2.8 MiB | 83 | never | 44.1 ms | killed in Setup¹ | 22.4 ms | 22.7 GiB/s | – | 44.7 GiB/s |

¹ Killed during their `Setup` with nothing else running (31 GB RAM); the matrix is padded to 57561 × 65536 elements. Most likely out of memory.

## 1b. RC-PIR for every storage factor c: online communication / queries until SimplePIR is cheaper

Each cell: RC-PIR online communication per query (best number of records per block for that c), then, after the slash, the number of queries until SimplePIR is cheaper (as in table 1): SimplePIR hint / (RC-PIR online − SimplePIR online). "never": RC-PIR is also cheaper per query. Header: c and the retrieval-server storage. SimplePIR's hint and online communication are those of table 1; DoublePIR is cheaper for no c and record size.

| record size | c = 2 (2 GiB) | c = 4 (4 GiB) | c = 8 (8 GiB) | c = 16 (16 GiB) | c = 256 (256 GiB) |
|---|---|---|---|---|---|
| 64 B | 311 KiB / 1,625 | 220 KiB / never | 187 KiB / never | 156 KiB / never | 112 KiB / never |
| 256 B | 311 KiB / 1,602 | 220 KiB / never | 187 KiB / never | 156 KiB / never | 112 KiB / never |
| 1 KiB | 311 KiB / 1,600 | 220 KiB / never | 187 KiB / never | 156 KiB / never | 112 KiB / never |
| 4 KiB | 750 KiB / 242 | 393 KiB / 785 | 277 KiB / 2,928 | 216 KiB / never | 128 KiB / never |
| 8 KiB | 1,442 KiB / 115 | 737 KiB / 277 | 497 KiB / 534 | 384 KiB / 940 | 208 KiB / never |
| 16 KiB | 2,842 KiB / 64 | 1,433 KiB / 140 | 969 KiB / 231 | 728 KiB / 346 | 376 KiB / 1,287 |
| 64 KiB | 11,204 KiB / 20 | 5,635 KiB / 40 | 3,779 KiB / 62 | 2,882 KiB / 83 | 1,474 KiB / 180 |

Records per block (and so the server time) differ from table 1 (c = 16) only for c = 2: 64 B (16 instead of 32, server time 26.3 ms instead of 22.6 ms), 256 B (4 instead of 8, server time 26.3 ms instead of 22.6 ms), 1 KiB (1 instead of 2, server time 26.3 ms instead of 22.6 ms); c = 4: 64 B (16 instead of 32, server time 26.3 ms instead of 22.6 ms), 256 B (4 instead of 8, server time 26.3 ms instead of 22.6 ms), 1 KiB (1 instead of 2, server time 26.3 ms instead of 22.6 ms). Otherwise the server times of table 1 hold for every c.

## 1c. Runtime per query for every storage factor c (best number of records per block for that c)

- Server time: compute server, one query, one thread (as in table 1; it depends only on the block shape, not on c). SimplePIR: table 1.
- Client time: RC-PIR client in Node, single thread, no network, mean of 100 queries: sample S, build the compute query (expand s columns of H, XOR), decode (XOR s + 1 blocks). Each configuration runs in its own Node process (`bench_client.mjs records`, `results/client_records.jsonl`).
- SimplePIR/DoublePIR client: their Go client. Query build from the `*PirSingle` logs (mean of 5); SimplePIR decode = their `Recover` in their full flow `RunPIR` with the real hint, mean of 3 runs, each run alone (`./run_simplepir.sh recover-sweep`, `results/recover_sweep/`). DoublePIR decode not measured (its hint is 912 MiB to 899 GiB at these record sizes).

| record size | server, c = 2 | server, c = 4 | server, c = 8 | server, c = 16 | server, c = 256 | SimplePIR server | client, c = 2 | client, c = 4 | client, c = 8 | client, c = 16 | client, c = 256 | SimplePIR client (query build + decode) | DoublePIR query build |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 64 B | 26.3 ms | 26.3 ms | 22.6 ms | 22.6 ms | 22.6 ms | 43.8 ms | 38.6 ms | 18.3 ms | 6.6 ms | 4.9 ms | 2.5 ms | 32.1 ms (25.7 + 6.4) | 55.7 ms |
| 256 B | 26.3 ms | 26.3 ms | 22.6 ms | 22.6 ms | 22.6 ms | 44.5 ms | 37.0 ms | 18.1 ms | 6.6 ms | 4.9 ms | 2.5 ms | 30.4 ms (25.1 + 5.3) | 55.6 ms |
| 1 KiB | 26.3 ms | 26.3 ms | 22.6 ms | 22.6 ms | 22.6 ms | 44.7 ms | 36.5 ms | 18.0 ms | 6.7 ms | 4.9 ms | 2.4 ms | 33.0 ms (26.1 + 6.9) | 54.5 ms |
| 4 KiB | 20.6 ms | 20.6 ms | 20.6 ms | 20.6 ms | 20.6 ms | 42.8 ms | 12.8 ms | 6.3 ms | 4.2 ms | 3.0 ms | 1.6 ms | 31.8 ms (24.7 + 7.1) | 55.6 ms |
| 8 KiB | 20.2 ms | 20.2 ms | 20.2 ms | 20.2 ms | 20.2 ms | 44.6 ms | 9.5 ms | 4.9 ms | 3.2 ms | 2.4 ms | 1.2 ms | 30.7 ms (22.0 + 8.6) | 57.2 ms |
| 16 KiB | 19.6 ms | 19.6 ms | 19.6 ms | 19.6 ms | 19.6 ms | 44.0 ms | 9.7 ms | 4.7 ms | 3.1 ms | 2.4 ms | 1.2 ms | 27.5 ms (18.2 + 9.3) | 54.5 ms |
| 64 KiB | 22.4 ms | 22.4 ms | 22.4 ms | 22.4 ms | 22.4 ms | 44.1 ms | 18.1 ms | 9.6 ms | 6.1 ms | 4.7 ms | 2.3 ms | 27.7 ms (14.3 + 13.4) | n/a |

## 1d. RC-PIR (c = 16): records per block chosen for communication vs for server time

Same measurements as table 1 (one query, one thread); every power-of-two number of records per block with 2^12 <= number of blocks <= 2^24 was timed. Communication from the encoder's parameter selection.

| record size | records per block (min. communication) | online | server time | records per block (min. server time) | online | server time | SimplePIR server time |
|---|---|---|---|---|---|---|---|
| 64 B | 32 | 156.5 KiB | 22.6 ms (44.3 GiB/s) | 256 | 728.5 KiB | 19.6 ms (50.9 GiB/s) | 43.8 ms (22.8 GiB/s) |
| 256 B | 8 | 156.5 KiB | 22.6 ms (44.3 GiB/s) | 64 | 728.5 KiB | 19.6 ms (50.9 GiB/s) | 44.5 ms (22.5 GiB/s) |
| 1 KiB | 2 | 156.5 KiB | 22.6 ms (44.3 GiB/s) | 16 | 728.5 KiB | 19.6 ms (50.9 GiB/s) | 44.7 ms (22.4 GiB/s) |
| 4 KiB | 1 | 216.5 KiB | 20.6 ms (48.5 GiB/s) | 4 | 728.5 KiB | 19.6 ms (50.9 GiB/s) | 42.8 ms (23.4 GiB/s) |
| 8 KiB | 1 | 384.5 KiB | 20.2 ms (49.5 GiB/s) | 2 | 728.5 KiB | 19.6 ms (50.9 GiB/s) | 44.6 ms (22.4 GiB/s) |
| 16 KiB | 1 | 728.5 KiB | 19.6 ms (50.9 GiB/s) | 1 | 728.5 KiB | 19.6 ms (50.9 GiB/s) | 44.0 ms (22.7 GiB/s) |
| 64 KiB | 1 | 2882.4 KiB | 22.4 ms (44.7 GiB/s) | 4 | 11264.9 KiB | 21.5 ms (46.4 GiB/s) | 44.1 ms (22.7 GiB/s) |

## 2. SimplePIR/DoublePIR layouts chosen by their `PickParams`

Matrix of rows × columns over $\mathbb{Z}_p$; a record takes Ne (elements per record) consecutive elements of one column (9–10 bits each), so a column holds rows / Ne records. DoublePIR: their `SetupDB` sets X = Ne, so its hint ($\delta X n^2$ elements) and download grow linearly with the record size; for 64 KiB records its $m \ge$ `COMP_RATIO`$\cdot n = 65536$ columns exceed the $2^{14}$ records, so the matrix is padded to 4 GB.

| record size | scheme | rows | columns | p | Ne | records per column | packed DB | hint | up | down |
|---|---|---|---|---|---|---|---|---|---|---|
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
| 64 B | 2 | 16 | 2^20 | 1032 | 180 | 2.0 GiB | 128.0 | 1.0 | 0.5 | 181.4 | 310.9 | 2061.6 |
| 64 B | 4 | 16 | 2^20 | 1032 | 90 | 4.0 GiB | 128.0 | 1.0 | 0.2 | 90.7 | 220.0 | 2054.8 |
| 64 B | 8 | 32 | 2^19 | 2056 | 60 | 8.0 GiB | 64.0 | 2.0 | 0.2 | 120.5 | 186.6 | 2052.6 |
| 64 B | 16 | 32 | 2^19 | 2056 | 45 | 16.1 GiB | 64.0 | 2.0 | 0.1 | 90.4 | 156.5 | 2051.5 |
| 64 B | 256 | 32 | 2^19 | 2056 | 23 | 257 GiB | 64.0 | 2.0 | 0.1 | 46.2 | 112.3 | 2049.8 |
| 256 B | 2 | 4 | 2^20 | 1032 | 180 | 2.0 GiB | 128.0 | 1.0 | 0.5 | 181.4 | 310.9 | 559.7 |
| 256 B | 4 | 4 | 2^20 | 1032 | 90 | 4.0 GiB | 128.0 | 1.0 | 0.2 | 90.7 | 220.0 | 536.0 |
| 256 B | 8 | 8 | 2^19 | 2056 | 60 | 8.0 GiB | 64.0 | 2.0 | 0.2 | 120.5 | 186.6 | 528.2 |
| 256 B | 16 | 8 | 2^19 | 2056 | 45 | 16.1 GiB | 64.0 | 2.0 | 0.1 | 90.4 | 156.5 | 524.3 |
| 256 B | 256 | 8 | 2^19 | 2056 | 23 | 257 GiB | 64.0 | 2.0 | 0.1 | 46.2 | 112.3 | 518.3 |
| 1 KiB | 2 | 1 | 2^20 | 1032 | 180 | 2.0 GiB | 128.0 | 1.0 | 0.5 | 181.4 | 310.9 | 310.9 |
| 1 KiB | 4 | 1 | 2^20 | 1032 | 90 | 4.0 GiB | 128.0 | 1.0 | 0.2 | 90.7 | 220.0 | 220.0 |
| 1 KiB | 8 | 2 | 2^19 | 2056 | 60 | 8.0 GiB | 64.0 | 2.0 | 0.2 | 120.5 | 186.6 | 189.6 |
| 1 KiB | 16 | 2 | 2^19 | 2056 | 45 | 16.1 GiB | 64.0 | 2.0 | 0.1 | 90.4 | 156.5 | 174.5 |
| 1 KiB | 256 | 2 | 2^19 | 2056 | 23 | 257 GiB | 64.0 | 2.0 | 0.1 | 46.2 | 112.3 | 152.3 |
| 4 KiB | 2 | 1 | 2^18 | 4104 | 178 | 2.0 GiB | 32.0 | 4.0 | 0.4 | 713.4 | 749.8 | 749.8 |
| 4 KiB | 4 | 1 | 2^18 | 4104 | 89 | 4.0 GiB | 32.0 | 4.0 | 0.2 | 356.7 | 392.9 | 392.9 |
| 4 KiB | 8 | 1 | 2^18 | 4104 | 60 | 8.0 GiB | 32.0 | 4.0 | 0.2 | 240.5 | 276.6 | 276.6 |
| 4 KiB | 16 | 1 | 2^18 | 4104 | 45 | 16.0 GiB | 32.0 | 4.0 | 0.1 | 180.4 | 216.5 | 216.5 |
| 4 KiB | 256 | 1 | 2^18 | 4104 | 23 | 256.5 GiB | 32.0 | 4.0 | 0.1 | 92.2 | 128.3 | 128.3 |
| 8 KiB | 2 | 1 | 2^17 | 8200 | 177 | 2.0 GiB | 16.0 | 8.0 | 0.4 | 1417.4 | 1441.8 | 1441.8 |
| 8 KiB | 4 | 1 | 2^17 | 8200 | 89 | 4.0 GiB | 16.0 | 8.0 | 0.2 | 712.7 | 736.9 | 736.9 |
| 8 KiB | 8 | 1 | 2^17 | 8200 | 59 | 8.0 GiB | 16.0 | 8.0 | 0.1 | 472.5 | 496.6 | 496.6 |
| 8 KiB | 16 | 1 | 2^17 | 8200 | 45 | 16.0 GiB | 16.0 | 8.0 | 0.1 | 360.4 | 384.5 | 384.5 |
| 8 KiB | 256 | 1 | 2^17 | 8200 | 23 | 256.2 GiB | 16.0 | 8.0 | 0.1 | 184.2 | 208.3 | 208.3 |
| 16 KiB | 2 | 1 | 2^16 | 16392 | 176 | 2.0 GiB | 8.0 | 16.0 | 0.4 | 2817.4 | 2841.7 | 2841.7 |
| 16 KiB | 4 | 1 | 2^16 | 16392 | 88 | 4.0 GiB | 8.0 | 16.0 | 0.2 | 1408.7 | 1432.9 | 1432.9 |
| 16 KiB | 8 | 1 | 2^16 | 16392 | 59 | 8.0 GiB | 8.0 | 16.0 | 0.1 | 944.5 | 968.6 | 968.6 |
| 16 KiB | 16 | 1 | 2^16 | 16392 | 44 | 16.0 GiB | 8.0 | 16.0 | 0.1 | 704.3 | 728.5 | 728.5 |
| 16 KiB | 256 | 1 | 2^16 | 16392 | 22 | 256.1 GiB | 8.0 | 16.0 | 0.1 | 352.2 | 376.2 | 376.2 |
| 64 KiB | 2 | 1 | 2^14 | 65544 | 174 | 2.0 GiB | 2.0 | 64.0 | 0.3 | 11137.4 | 11203.7 | 11203.7 |
| 64 KiB | 4 | 1 | 2^14 | 65544 | 87 | 4.0 GiB | 2.0 | 64.0 | 0.2 | 5568.7 | 5634.9 | 5634.9 |
| 64 KiB | 8 | 1 | 2^14 | 65544 | 58 | 8.0 GiB | 2.0 | 64.0 | 0.1 | 3712.5 | 3778.6 | 3778.6 |
| 64 KiB | 16 | 1 | 2^14 | 65544 | 44 | 16.0 GiB | 2.0 | 64.0 | 0.1 | 2816.3 | 2882.4 | 2882.4 |
| 64 KiB | 256 | 1 | 2^14 | 65544 | 22 | 256.0 GiB | 2.0 | 64.0 | 0.1 | 1408.2 | 1474.2 | 1474.2 |

## 4. Fixed shapes: one query returns one block of $\ell/8 - 4$ bytes

Best power-of-two shape $t\times\ell$ per c. SimplePIR for comparison: one query returns a full column of its 1-bit-entry layout, 30893 elements × 9 bits ≈ 33.9 KiB, for 240 KiB online (`results/simplepir_bw.txt`).

| c | t | ell | s | retrieval storage | compute up | compute down | retrieval up | retrieval down | total | data per query | comm / data |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | 2^20 | 2^13 | 180 | 2 GiB | 128.0 | 1.0 | 0.5 | 180.0 | 309.5 | 1020 B | 311× |
| 4 | 2^20 | 2^13 | 90 | 4 GiB | 128.0 | 1.0 | 0.2 | 90.0 | 219.2 | 1020 B | 220× |
| 8 | 2^19 | 2^14 | 60 | 8 GiB | 64.0 | 2.0 | 0.2 | 120.0 | 186.2 | 2.0 KiB | 93× |
| 16 | 2^19 | 2^14 | 45 | 16 GiB | 64.0 | 2.0 | 0.1 | 90.0 | 156.1 | 2.0 KiB | 78× |
| 256 | 2^19 | 2^14 | 23 | 256 GiB | 64.0 | 2.0 | 0.1 | 46.0 | 112.1 | 2.0 KiB | 56× |
