#!/usr/bin/env bash
# B4: full preprocessing of a 1 GiB database with the real encoder CLI (--device cuda, verify on).
# Times each step from timestamped encoder log lines; wall time and peak RAM from /usr/bin/time.
# Needs a Python with CuPy (default: the repo's .env, environment.yml; override with PY=...). The encoder
# and rcpir_common are always taken from this checkout (PYTHONPATH), not from an installed copy.
#   benchmarks/bench_encode.sh [WORKDIR]           c = 2, 4, 8, 16 at L = 1 KiB / 2 KiB
#                                                  -> results/encode_c*.log
#   benchmarks/bench_encode.sh records [WORKDIR]   c = 16 at the exact block shape of every record size of
#                                                  results/comm_shapes.json (B1), one run per distinct shape
#                                                  -> results/encode_records/encode_t*_L*.log
# WORKDIR: on the Linux filesystem, ~30 GiB free (default benchmarks/.encode-work, deleted at the end of
# records mode). Run nothing else meanwhile.
set -euo pipefail
cd "$(dirname "$0")/.."
MODE=c-sweep
if [ "${1:-}" = records ]; then MODE=records; shift; fi
PY=${PY:-$PWD/.env/bin/python}
export PYTHONPATH=$PWD/encoder/src:$PWD/common/src
WORK=${1:-$PWD/benchmarks/.encode-work}
mkdir -p "$WORK" benchmarks/results

# encode C T PAYLOAD LOG: random DB of T blocks of PAYLOAD bytes, one encoder run, timestamped log
encode() {
  local c=$1 t=$2 p=$3 log=$4
  local db=$WORK/db_${t}_$p.jsonl out=$WORK/out
  [ -f "$db" ] || $PY -c "
import base64, os, sys
with open(sys.argv[1], 'w') as f:
    for _ in range($t): f.write('{\"data\": \"' + base64.b64encode(os.urandom($p)).decode() + '\"}\n')
" "$db"
  rm -rf "$out"
  /usr/bin/time -v -o "$log.time" $PY -u -m rcpir_encoder "$db" --out "$out" --c "$c" --device cuda --yes 2>&1 \
    | while IFS= read -r line; do printf '%s %s\n' "$EPOCHREALTIME" "$line"; done > "$log"
  du -sb "$out/site" "$out/X.bin" >> "$log.time"
  ls "$out/site/rc-pir/r" | wc -l >> "$log.time"
  rm -rf "$out"
}

if [ "$MODE" = c-sweep ]; then
  # c t payload_bytes  (payload + 4-byte header = L = 1 KiB / 2 KiB)
  for cfg in "2 1048576 1020" "4 1048576 1020" "8 524288 2044" "16 524288 2044"; do
    read -r c t p <<<"$cfg"
    encode "$c" "$t" "$p" "benchmarks/results/encode_c$c.log"
  done
  exit 0
fi

# records: distinct (t, payload, L) of the c = 16 shapes; payload = records per block x record size
mkdir -p benchmarks/results/encode_records
$PY - benchmarks/results/comm_shapes.json <<'EOF' > "$WORK/shapes.txt"
import json, sys
seen = []
for r in json.load(open(sys.argv[1])):
    if r["c"] != 16:
        continue
    bits = 1 if r["B"] == "1bit" else 8 * int(r["B"])
    p = -(-r["g"] * bits // 8)
    assert -(-(4 + p) // 8) * 8 == r["L"], r       # the encoder's L = roundup_8(4 + payload)
    if (r["t"], p, r["L"]) not in seen:
        seen.append((r["t"], p, r["L"]))
for t, p, L in seen:
    print(t, p, L)
EOF
while read -r t p L; do
  echo "c = 16, t = $t, payload = $p B, L = $L B" >&2
  encode 16 "$t" "$p" "benchmarks/results/encode_records/encode_t${t}_L$L.log"
  rm -f "$WORK/db_${t}_$p.jsonl"
done < "$WORK/shapes.txt"
rm -rf "$WORK"
