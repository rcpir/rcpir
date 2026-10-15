#!/usr/bin/env bash
# B4: full preprocessing of a 1 GiB database with the real encoder CLI (--device cuda, verify on),
# for c = 2, 4, 8, 16 at the B1-optimal shapes. Times each step from timestamped encoder log lines;
# wall time and peak RAM from /usr/bin/time. Needs the repo's .env with CuPy (environment.yml).
# Usage: benchmarks/bench_encode.sh [WORKDIR]   (WORKDIR: on the Linux filesystem, ~30 GiB free)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=$PWD/.env/bin/python
WORK=${1:-$PWD/benchmarks/.encode-work}
mkdir -p "$WORK" benchmarks/results

# c t payload_bytes  (payload + 4-byte header = L = 1 KiB / 2 KiB)
for cfg in "2 1048576 1020" "4 1048576 1020" "8 524288 2044" "16 524288 2044"; do
  read -r c t p <<<"$cfg"
  db=$WORK/db_$t.jsonl
  [ -f "$db" ] || $PY -c "
import base64, os, sys
with open(sys.argv[1], 'w') as f:
    for _ in range($t): f.write('{\"data\": \"' + base64.b64encode(os.urandom($p)).decode() + '\"}\n')
" "$db"
  out=$WORK/out_c$c
  rm -rf "$out"
  log=benchmarks/results/encode_c$c.log
  /usr/bin/time -v -o "$log.time" $PY -u -m rcpir_encoder "$db" --out "$out" --c "$c" --device cuda --yes 2>&1 \
    | while IFS= read -r line; do printf '%s %s\n' "$EPOCHREALTIME" "$line"; done > "$log"
  du -sb "$out/site" "$out/X.bin" >> "$log.time"
  ls "$out/site/rc-pir/r" | wc -l >> "$log.time"
  rm -rf "$out"
done
