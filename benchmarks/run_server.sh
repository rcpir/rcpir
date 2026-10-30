#!/usr/bin/env bash
# B2/B3: compute-server throughput on 1 GiB, sweeping shape, threads and batch size.
# Shapes (T columns x L bytes): the B1-optimal shapes for c <= 4 (2^20 x 1 KiB) and c >= 16
# (2^19 x 2 KiB), and a near-square one (2^17 x 8 KiB, i.e. t = 2^17, ell = 2^16 bits).
# Pass "records" to time instead every shape of comm.py's record-size sweep (one thread, one query);
# RESULTS_DIR (default results, relative to benchmarks/) selects where comm_shapes.json is read and
# server_records.jsonl written.
set -euo pipefail
cd "$(dirname "$0")"
cargo build --release --manifest-path server-bench/Cargo.toml
mkdir -p results
if [ "${1:-}" = records ]; then   # shapes of comm.py's record-size sweep ($RESULTS_DIR/comm_shapes.json), 1 thread, 1 query
  dir=${RESULTS_DIR:-results}
  shapes=$(python3 -c "import json, sys; print(','.join(sorted({f\"{d['t']}x{d['L']}\" for d in json.load(open(sys.argv[1]))})))" "$dir/comm_shapes.json")
  server-bench/target/release/server-bench --shapes "$shapes" --threads 1 --batch 1 --reps 10 | tee "$dir/server_records.jsonl"
  exit 0
fi
server-bench/target/release/server-bench --shapes 1048576x1024,524288x2048,131072x8192 \
  --threads 1,8,28 --batch 1,2,4,8,16,32,64 --reps 10 | tee results/server.jsonl
