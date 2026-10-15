#!/usr/bin/env bash
# Large single-shard test: all of R in ONE file (columns_per_shard = m), past the 2^31 and 2^32 byte offsets.
#
#   e2e/single_shard.sh [M]     (default M = 5120: R = 5 GiB; needs the same tools as e2e/run.sh, ~6 GiB disk)
#
# Shape: t = 64 blocks, L = 1 MiB, insecure test parameters (m = M, s = 40). Only the layout is under test;
# n*m is kept small (cost ~ 8 t |R|) so the CPU encoder finishes in minutes.
# Checks: (1) the encoder writes one shard of m*L bytes and columns_per_shard = m (peak RSS reported);
# (2) the client's columnLocation + a Range GET return the right bytes for columns around 2^31 and 2^32 bytes
# and the last column; (3) every block is retrieved correctly through client, static server and compute server.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
PY=${PY:-$ROOT/.env/bin/python}
PORT=${BASE_PORT:-18280}
M=${1:-5120}
L=$((1 << 20))
WORK=$(mktemp -d)
PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done; rm -rf "$WORK"; }
trap cleanup EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
wait_up() { for _ in $(seq 300); do curl -s -o /dev/null "$1" && return 0; sleep 0.1; done; fail "$1 did not come up"; }

echo "== build"
(cd client && npm run -s build)
(cd server && cargo build --release -q)
export PYTHONPATH="$ROOT/encoder/src:$ROOT/common/src"

echo "== DB: t = 64 blocks, block 0 has the largest payload (L - 4 bytes), so L = 1 MiB"
"$PY" - "$WORK/db.jsonl" "$L" <<'EOF'
import base64, json, random, sys
path, L = sys.argv[1], int(sys.argv[2])
rng = random.Random(7)
lengths = [L - 4, 0] + [rng.randint(0, L - 4) for _ in range(62)]
with open(path, "w") as f:
    for n in lengths:
        f.write(json.dumps({"data": base64.b64encode(rng.randbytes(n)).decode()}) + "\n")
EOF

echo "== encode: m = $M, R = $((M * L >> 20)) MiB, --shard-mib $(((M * L >> 20) + 1)) (one shard)"
/usr/bin/time -v "$PY" -m rcpir_encoder "$WORK/db.jsonl" --out "$WORK/out" --insecure-m "$M" --insecure-s 40 \
  --shard-mib $(((M * L >> 20) + 1)) --yes >"$WORK/enc.out" 2>"$WORK/enc.log" || { tail -20 "$WORK/enc.log"; fail "encoder"; }
grep -E "^R: " "$WORK/enc.out" || true
grep -E "Elapsed \(wall|Maximum resident" "$WORK/enc.log" | sed 's/^\s*/  /'
SHARDS=$(find "$WORK/out/site/rc-pir/r" -type f | wc -l)
SIZE=$(stat -c %s "$WORK/out/site/rc-pir/r/00000000")
CPS=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['columns_per_shard'])" "$WORK/out/params.json")
[[ $SHARDS == 1 && $SIZE == $((M * L)) && $CPS == "$M" ]] || fail "layout: $SHARDS shards, $SIZE bytes, columns_per_shard = $CPS"
echo "ok: one shard of $SIZE bytes, columns_per_shard = m = $CPS (encoder verify step passed)"

echo "== serve"
"$PY" e2e/static_server.py "$WORK/out/site" --port "$PORT" & PIDS+=($!)
server/target/release/rcpir-server --params "$WORK/out/params.json" --x "$WORK/out/X.bin" \
  --listen "127.0.0.1:$((PORT + 1))" --threads 4 --plain >"$WORK/server.log" 2>&1 & PIDS+=($!)
wait_up "http://localhost:$PORT/.well-known/rc-pir.json"
wait_up "http://localhost:$((PORT + 1))/.well-known/rc-pir.json"

echo "== boundary columns: client columnLocation + Range GET vs. the shard file"
node --input-type=module - "$WORK/out/site/rc-pir/r/00000000" "http://localhost:$PORT" "$M" "$L" <<'EOF'
import { openSync, readSync } from "node:fs";
import { columnLocation } from "./client/dist/query.js";
const [file, base, m, L] = [process.argv[2], process.argv[3], Number(process.argv[4]), Number(process.argv[5])];
const fd = openSync(file, "r");
const marks = [2 ** 31, 2 ** 32].map((b) => Math.floor(b / L)).filter((j) => j < m);
const js = [...new Set([0, ...marks.flatMap((j) => [j - 1, j]), m - 1])].filter((j) => j >= 0 && j < m);
for (const j of js) {
  const { path, offset } = columnLocation(j, m, L);
  const r = await fetch(base + path, { headers: { Range: `bytes=${offset}-${offset + L - 1}` } });
  const got = new Uint8Array(await r.arrayBuffer());
  const want = new Uint8Array(L);
  readSync(fd, want, 0, L, offset);
  const ok = r.status === 206 && got.length === L && Buffer.compare(Buffer.from(got), Buffer.from(want)) === 0;
  console.log(`  j = ${j}: ${path} bytes ${offset}-${offset + L - 1} (${(offset / 2 ** 30).toFixed(3)} GiB) -> ${r.status} ${ok ? "ok" : "MISMATCH"}`);
  if (!ok) process.exit(1);
}
EOF

echo "== retrieve every block (client + static server + compute server)"
node e2e/retrieve_all.mjs "$WORK/db.jsonl" "http://localhost:$PORT" "http://localhost:$((PORT + 1))"
echo "single-shard test passed"
