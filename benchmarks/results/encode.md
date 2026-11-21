| c | t | m | s | λ' | attack bits prange / mitm / brute force | scan | report + estimate | pack X.bin | R = XH (all panels) | r_digest + verify + params | total (wall) | peak RAM | R size | shards |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | 1048576 | 2097152 | 180 | 180 | 180.0 / 1215.7 / 2431.5 | 4 s | 0 s | 5 s | 112 s | 125 s | 4:05.30 | 4.0 GiB | 2.0 GiB | 32 |
| 4 | 1048576 | 4194304 | 90 | 180 | 180.0 / 697.9 / 1395.7 | 4 s | 0 s | 4 s | 223 s | 123 s | 5:55.55 | 4.0 GiB | 4.0 GiB | 64 |
| 8 | 524288 | 4194304 | 60 | 179 | 180.0 / 482.8 / 965.6 | 3 s | 0 s | 4 s | 258 s | 71 s | 5:36.30 | 4.1 GiB | 8.0 GiB | 128 |
| 16 | 524288 | 8388608 | 45 | 179 | 180.0 / 393.9 / 787.9 | 3 s | 0 s | 4 s | 533 s | 78 s | 10:19.21 | 3.9 GiB | 16.0 GiB | 256 |

c = 16 at the block shape of each record size of B1 (`bench_encode.sh records`):

| record sizes | t | L (bytes) | m | s | λ' | attack bits prange / mitm / brute force | scan + report + pack | R = XH (all panels) | r_digest + params | total without verify (wall) | verify | total (wall) | peak RAM | R size | shards |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 bit, 64 B, 256 B, 1 KiB | 524288 | 2056 | 8388608 | 45 | 179 | 180.0 / 393.9 / 787.9 | 8 s | 473 s | 11 s | 492 s | 57 s | 9:08.95 | 4.1 GiB | 16.1 GiB | 258 |
| 4 KiB | 262144 | 4104 | 4194304 | 45 | 178 | 180.0 / 371.4 / 742.9 | 7 s | 209 s | 11 s | 227 s | 31 s | 4:18.06 | 4.1 GiB | 16.0 GiB | 257 |
| 8 KiB | 131072 | 8200 | 2097152 | 45 | 177 | 180.0 / 348.9 / 697.9 | 7 s | 102 s | 10 s | 120 s | 23 s | 2:23.27 | 4.1 GiB | 16.0 GiB | 257 |
| 16 KiB | 65536 | 16392 | 1048576 | 44 | 176 | 176.0 / 319.9 / 639.8 | 6 s | 51 s | 11 s | 69 s | 22 s | 1:30.35 | 3.6 GiB | 16.0 GiB | 257 |
| 64 KiB | 16384 | 65544 | 262144 | 44 | 174 | 176.0 / 275.9 / 551.8 | 6 s | 13 s | 13 s | 33 s | 23 s | 0:55.50 | 3.3 GiB | 16.0 GiB | 257 |
