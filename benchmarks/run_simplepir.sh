#!/usr/bin/env bash
# SimplePIR / DoublePIR with the authors' own code (github.com/ahenzinger/simplepir, pinned commit),
# single thread, on 1 GiB of fixed-size records for every record size B in RECORD_SIZES ("1bit" or
# bytes; LOG_N = 33 - log2(D) entries of D bits, D = 1 or 8B; layout chosen by their PickParams).
# Needs Go >= 1.18. One mode per call:
#   bw-sweep       their Test*PirBW: communication only (seconds)          -> results/bw_sweep/
#   time-sweep     their *PirSingle: 5 query/answer runs (~2-3 min per run) -> results/time_sweep/
#   recover-sweep  their full flow RunPIR with the real hint, for the decode time (~3.8 min per run,
#                  REPS runs, appended: delete the file for a fresh run)  -> results/recover_sweep/
# RECORD_SIZES and SCHEMES select runs, e.g. RECORD_SIZES=1024 SCHEMES=Double ./run_simplepir.sh time-sweep
set -euo pipefail
cd "$(dirname "$0")"
COMMIT=e9020b03bf2872c75b8954e749e32408b5db87ed
RECORD_SIZES="${RECORD_SIZES:-1bit 64 256 1024 4096 8192 16384 65536}"   # keep in sync with comm.py
SCHEMES="${SCHEMES:-Simple Double}"
MODE=${1:-}
case $MODE in bw-sweep | time-sweep | recover-sweep) ;; *) echo "usage: $0 bw-sweep|time-sweep|recover-sweep" >&2; exit 1 ;; esac
[ -d simplepir ] || git clone -q https://github.com/ahenzinger/simplepir simplepir
git -C simplepir checkout -q "$COMMIT"
cd simplepir/pir
for B in $RECORD_SIZES; do
  if [ "$B" = 1bit ]; then D=1; else D=$((8 * B)); fi
  LOG_N=33
  for ((x = D; x > 1; x /= 2)); do LOG_N=$((LOG_N - 1)); done   # 33 - log2(D)
  for scheme in $SCHEMES; do
    out=../../results/${MODE/-/_}/${scheme,,}pir_B$B.txt
    mkdir -p "$(dirname "$out")"
    case $MODE in
      bw-sweep)
        LOG_N=$LOG_N D=$D go test -run="^Test${scheme}PirBW\$" > "$out" 2>&1 || echo "FAILED (exit $?)" >> "$out"
        echo "B=$B $scheme: $(grep -c 'Online download' "$out") result(s)" ;;
      time-sweep)
        LOG_N=$LOG_N D=$D timeout 45m go test -bench "^Benchmark${scheme}PirSingle\$" -timeout 0 -run='^$' > "$out" 2>&1 \
          || echo "FAILED (exit $?)" >> "$out"
        echo "B=$B $scheme: $(grep -c 'Answering query' "$out") answer(s)" ;;
      recover-sweep)
        (cd ../../simplepir-recover && go run . "${scheme,,}" "${REPS:-3}" "$LOG_N" "$D") >> "$out" 2>&1 \
          || echo "FAILED (exit $?)" >> "$out"
        echo "B=$B $scheme: $(grep -c 'Success' "$out") decode(s) so far" ;;
    esac
  done
done
