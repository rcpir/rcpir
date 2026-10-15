#!/usr/bin/env bash
# B2/B3: compute-server throughput on 1 GiB, sweeping shape, threads and batch size.
# Shapes (T columns x L bytes): the B1-optimal shapes for c <= 4 (2^20 x 1 KiB) and c >= 16
# (2^19 x 2 KiB), and a near-square one (2^17 x 8 KiB, i.e. t = 2^17, ell = 2^16 bits).
set -euo pipefail
cd "$(dirname "$0")"
cargo build --release --manifest-path server-bench/Cargo.toml
mkdir -p results
server-bench/target/release/server-bench --shapes 1048576x1024,524288x2048,131072x8192 \
  --threads 1,8,28 --batch 1,2,4,8,16,32,64 --reps 10 | tee results/server.jsonl
