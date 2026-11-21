#!/usr/bin/env bash
# One-time server setup times for B1, in order, one job at a time:
#   1. DoublePIR hint (their Setup): 1 bit (1 run, cross-check with results/recover_sweep/), 64 B, 256 B (3 runs)
#   2. DoublePIR hint at 1 KiB, only if the peak RSS measured at 256 B predicts it fits in RAM
#      (4 KiB - 16 KiB are not run: their Setup holds the 56-225 GiB hint in memory)
#   3. RC-PIR encoder (GPU) at the c = 16 block shape of every record size (bench_encode.sh records)
#   4. results/encode.md and results/comm.md regenerated
# SimplePIR's hint times are already in results/recover_sweep/ and are not rerun.
# Total ~1-1.5 h. Run nothing else on the machine meanwhile. Log: benchmarks/results/run_setup_times.log
# Usage: PY=/path/to/python-with-cupy benchmarks/run_setup_times.sh   (default PY: the repo's .env)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
BENCH=$ROOT/benchmarks
RES=$BENCH/results
export PY=${PY:-$ROOT/.env/bin/python}
LOG=$RES/run_setup_times.log

die() { echo "ERROR: $*" >&2; exit 1; }
step() { echo; echo "=== $(date '+%F %T') $*"; }

# ---- preflight (before anything is written) ----
[ -x "$PY" ] || die "no Python at $PY; run with PY=/path/to/python (needs CuPy), e.g.
  PY=/home/shahar/projects/rc-pir/.harness/work/19202dd4/.env/bin/python $0"
"$PY" -c "import cupy" 2>/dev/null || die "$PY cannot import cupy"
command -v go >/dev/null || die "go not found (needs Go >= 1.18)"
command -v nvidia-smi >/dev/null || die "nvidia-smi not found"
[ -f "$RES/comm_shapes.json" ] || die "missing $RES/comm_shapes.json (run python3 benchmarks/comm.py first)"
for d in setup_sweep encode_records; do
  [ ! -e "$RES/$d" ] || die "$RES/$d exists (results would be appended); move or delete it first"
done
[ -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ] || die "another process is using the GPU"
load=$(cut -d' ' -f1 /proc/loadavg)
awk -v l="$load" 'BEGIN { exit !(l < 2) }' || die "load average is $load; stop other jobs first"
free_gib=$(df -BG --output=avail "$BENCH" | tail -1 | tr -dc 0-9)
[ "$free_gib" -ge 30 ] || die "only ${free_gib} GiB free on $BENCH; need ~30 GiB"

exec > >(tee "$LOG") 2>&1
step "start (PY=$PY, load $load, ${free_gib} GiB free)"

# ---- 1. DoublePIR hint: 1 bit, 64 B, 256 B ----
cd "$BENCH"
step "DoublePIR hint, 1 bit (1 run)"
RECORD_SIZES=1bit REPS=1 SCHEMES=Double ./run_simplepir.sh setup-sweep
step "DoublePIR hint, 64 B and 256 B (3 runs each)"
RECORD_SIZES="64 256" REPS=3 SCHEMES=Double ./run_simplepir.sh setup-sweep

# ---- 2. DoublePIR hint, 1 KiB, if it fits ----
peak_kb=$(grep -o 'Peak RSS: [0-9]*' "$RES/setup_sweep/doublepir_B256.txt" | grep -o '[0-9]*$' | sort -n | tail -1 || true)
mem_kb=$(awk '/^MemTotal:/ { print $2 }' /proc/meminfo)
if [ -n "$peak_kb" ]; then
  pred_kb=$((peak_kb + 13 * 1024 * 1024))       # the hint grows by 14.1 - 3.5 GiB from 256 B to 1 KiB
  step "256 B peak RSS $((peak_kb / 1024)) MiB -> predicted 1 KiB peak $((pred_kb / 1024)) MiB (RAM $((mem_kb / 1024)) MiB)"
  if [ "$pred_kb" -lt $((mem_kb - 4 * 1024 * 1024)) ]; then
    step "DoublePIR hint, 1 KiB (3 runs)"
    RECORD_SIZES=1024 REPS=3 SCHEMES=Double ./run_simplepir.sh setup-sweep
  else
    step "skipping DoublePIR 1 KiB: predicted peak too close to RAM"
  fi
else
  step "skipping DoublePIR 1 KiB: no peak RSS in the 256 B log"
fi

# ---- 3. RC-PIR encoder at every B1 shape ----
step "RC-PIR encoder, c = 16, every B1 block shape (GPU)"
"$BENCH/bench_encode.sh" records

# ---- 4. reports ----
step "reports"
python3 "$BENCH/encode_report.py" > "$RES/encode.md"
python3 "$BENCH/comm.py" > "$RES/comm.md"

# ---- summary ----
step "summary"
for f in "$RES"/setup_sweep/*.txt; do
  echo "$(basename "$f"): setup $(grep -o 'Elapsed: .*' "$f" | cut -d' ' -f2 | tr '\n' ' ')| $(grep -h 'Peak RSS' "$f" | tail -1)"
done
grep -l "FAILED\|signal: killed" "$RES"/setup_sweep/*.txt 2>/dev/null | sed 's/^/FAILED: /' || true
for f in "$RES"/encode_records/*.log; do
  echo "$(basename "$f"): $(grep -o 'verify: OK.*' "$f" || echo 'NO verify: OK')"
done
step "done; send the log ($LOG) for review"
