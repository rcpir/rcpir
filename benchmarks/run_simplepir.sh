#!/usr/bin/env bash
# SimplePIR / DoublePIR on a 1 GiB database (2^33 x 1-bit entries), single thread, using the
# authors' own benchmarks (github.com/ahenzinger/simplepir, pinned commit). Needs Go >= 1.18.
# Pass "recover" to also measure their decode time, or "batch" for their batch benchmarks (Fig. 9, ~1.5 compute-hours).
# Pass "bw-sweep" to only print their communication for 1 GiB of B-byte records, B in RECORD_SIZES
# (LOG_N = 33 - log2(8B), D = 8B; layout chosen by their PickParams), for comm.py, or "time-sweep"
# for their single-query benchmark at the same sizes (single thread, ~2-3 min per run, 45 min cap), or
# "recover-sweep" for their decode time at the same sizes (RunPIR with the real hint, REPS runs each,
# appended to results/recover_sweep/).
set -euo pipefail
cd "$(dirname "$0")"
COMMIT=e9020b03bf2872c75b8954e749e32408b5db87ed
RECORD_SIZES="${RECORD_SIZES:-64 256 1024 4096 8192 16384 65536}"   # bytes; keep in sync with comm.py
SCHEMES="${SCHEMES:-Simple Double}"   # sweeps only; e.g. RECORD_SIZES=1024 SCHEMES=Double ./run_simplepir.sh time-sweep
[ -d simplepir ] || git clone -q https://github.com/ahenzinger/simplepir simplepir
git -C simplepir checkout -q "$COMMIT"
mkdir -p results
cd simplepir/pir
if [ "${1:-}" = time-sweep ]; then   # their single-query benchmark (5 answers) per record size
  for B in $RECORD_SIZES; do
    D=$((8 * B)); LOG_N=33
    for ((x = D; x > 1; x /= 2)); do LOG_N=$((LOG_N - 1)); done
    for scheme in $SCHEMES; do
      out=../../results/time_sweep/${scheme,,}pir_B$B.txt
      mkdir -p "$(dirname "$out")"
      LOG_N=$LOG_N D=$D timeout 45m go test -bench "^Benchmark${scheme}PirSingle\$" -timeout 0 -run='^$' > "$out" 2>&1 \
        || echo "FAILED (exit $?)" >> "$out"
      echo "B=$B $scheme: $(grep -c 'Answering query' "$out") answer(s)"
    done
  done
  exit 0
fi
if [ "${1:-}" = recover-sweep ]; then   # their decode time per record size (RunPIR: real hint, ~3 min per rep)
  for B in $RECORD_SIZES; do
    D=$((8 * B)); LOG_N=33
    for ((x = D; x > 1; x /= 2)); do LOG_N=$((LOG_N - 1)); done
    for scheme in $SCHEMES; do
      out=../../results/recover_sweep/${scheme,,}pir_B$B.txt     # appended: delete for a fresh run
      mkdir -p "$(dirname "$out")"
      (cd ../../simplepir-recover && go run . "${scheme,,}" "${REPS:-3}" "$LOG_N" "$D") >> "$out" 2>&1 \
        || echo "FAILED (exit $?)" >> "$out"
      echo "B=$B $scheme: $(grep -c 'Success' "$out") decode(s) so far"
    done
  done
  exit 0
fi
if [ "${1:-}" = bw-sweep ]; then
  for B in $RECORD_SIZES; do
    D=$((8 * B)); LOG_N=33
    for ((x = D; x > 1; x /= 2)); do LOG_N=$((LOG_N - 1)); done   # 33 - log2(D)
    for scheme in $SCHEMES; do
      out=../../results/bw_sweep/${scheme,,}pir_B$B.txt
      mkdir -p "$(dirname "$out")"
      LOG_N=$LOG_N D=$D go test -run="^Test${scheme}PirBW\$" > "$out" 2>&1 || echo "FAILED (exit $?)" >> "$out"
      echo "B=$B $scheme: $(grep -c 'Online download' "$out") result(s)"
    done
  done
  exit 0
fi
export LOG_N=33 D=1
go test -run=BW | tee ../../results/simplepir_bw.txt
go test -bench SimplePirSingle -timeout 0 -run='^$' | tee ../../results/simplepir_single.txt
go test -bench DoublePirSingle -timeout 0 -run='^$' | tee ../../results/doublepir_single.txt
if [ "${1:-}" = recover ]; then     # decode time via their RunPIR (includes computing the hint)
  (cd ../../simplepir-recover && go run . simple 3) | tee ../../results/simplepir_recover.txt
  (cd ../../simplepir-recover && go run . double 3) | tee ../../results/doublepir_recover.txt
fi
if [ "${1:-}" = batch ]; then
  go test -bench PirBatchLarge -timeout 0 -run='^$' | tee ../../results/simplepir_batch.txt
  cp simple-batch.log double-batch.log ../../results/
fi
