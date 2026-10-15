#!/usr/bin/env bash
# End-to-end test: encoder -> retrieval (static) server + compute server -> client.
#
#   e2e/run.sh            (needs: the Python env of environment.yml in .env/, cargo, node, openssl)
#
# Case 1: tiny DB, insecure test parameters, plain HTTP; every block, the rcpir-get CLI, h2c.
# Case 2: secure Mode A parameters (c = 16), R in several 1 MiB shards, both servers over HTTPS with a
#         self-signed certificate, HTTP/2 via ALPN on the compute server.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
PY=${PY:-$ROOT/.env/bin/python}
PORT=${BASE_PORT:-18080}
WORK=$(mktemp -d)
PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done; rm -rf "$WORK"; }
trap cleanup EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== build"
(cd client && npm run -s build)
(cd server && cargo build --release -q)
ENCODE=("$PY" -m rcpir_encoder)
export PYTHONPATH="$ROOT/encoder/src:$ROOT/common/src"

make_db() {  # $1 = path, $2 = t, $3 = max payload bytes, $4 = seed
  "$PY" - "$@" <<'EOF'
import base64, json, random, sys
path, t, max_len, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
rng = random.Random(seed)
lengths = [max_len, 0] + [rng.randint(0, max_len) for _ in range(t - 2)]
with open(path, "w") as f:
    for k, n in enumerate(lengths):
        f.write(json.dumps({"data": base64.b64encode(rng.randbytes(n)).decode(), "key": f"block-{k}"}) + "\n")
EOF
}

wait_up() {  # $1 = URL
  for _ in $(seq 100); do curl -sk -o /dev/null "$1" && return 0; sleep 0.1; done
  fail "$1 did not come up"
}

serve() {  # $1 = encoder output dir, $2 = scheme (http|https); sets RETRIEVAL and COMPUTE
  local out=$1 scheme=$2 tls_static=() tls_compute=(--plain)
  if [[ $scheme == https ]]; then
    tls_static=(--tls-cert "$WORK/cert.pem" --tls-key "$WORK/key.pem")
    tls_compute=(--tls-cert "$WORK/cert.pem" --tls-key "$WORK/key.pem")
  fi
  "$PY" e2e/static_server.py "$out/site" --port "$PORT" "${tls_static[@]}" & PIDS+=($!)
  server/target/release/rcpir-server --params "$out/params.json" --x "$out/X.bin" \
    --listen "127.0.0.1:$((PORT + 1))" --threads 4 "${tls_compute[@]}" >"$WORK/server.log" 2>&1 & PIDS+=($!)
  RETRIEVAL="$scheme://localhost:$PORT"
  COMPUTE="$scheme://localhost:$((PORT + 1))"
  wait_up "$RETRIEVAL/.well-known/rc-pir.json"
  wait_up "$COMPUTE/.well-known/rc-pir.json"
}

http_version() {  # $1 = URL, $2.. = curl flags; prints the HTTP version curl used
  local url=$1; shift
  curl -s -o /dev/null -w '%{http_version}' "$@" "$url"
}

stop() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; wait "$p" 2>/dev/null || true; done; PIDS=(); }

echo "== case 1: t = 50, insecure override (m = 400, s = 6), plain HTTP"
make_db "$WORK/db1.jsonl" 50 100 1
"${ENCODE[@]}" "$WORK/db1.jsonl" --out "$WORK/out1" --insecure-m 400 --insecure-s 6 --seed 000102030405060708090a0b0c0d0e0f >/dev/null 2>"$WORK/enc1.log" \
  || { cat "$WORK/enc1.log"; fail "encoder"; }
serve "$WORK/out1" http
node e2e/retrieve_all.mjs "$WORK/db1.jsonl" "$RETRIEVAL" "$COMPUTE"
# CLI: block 0 has the largest payload
node client/dist/cli.js --retrieval "$RETRIEVAL" --compute "$COMPUTE" --index 0 --out "$WORK/b0.bin" 2>"$WORK/cli.err"
"$PY" -c "import base64,json,sys; d=base64.b64decode(json.loads(open(sys.argv[1]).readline())['data']); sys.exit(open(sys.argv[2],'rb').read()!=d)" \
  "$WORK/db1.jsonl" "$WORK/b0.bin" || fail "rcpir-get output differs"
grep -q "insecure" "$WORK/cli.err" || fail "rcpir-get did not warn about insecure parameters"
echo "ok: rcpir-get CLI"
[[ $(http_version "$COMPUTE/.well-known/rc-pir.json" --http2-prior-knowledge) == 2 ]] || fail "compute server: no h2c"
echo "ok: compute server speaks HTTP/2 without TLS (h2c)"
stop

echo "== case 2: t = 600, secure Mode A (c = 16), shards of at most 1 MiB, HTTPS"
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 1 -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" -keyout "$WORK/key.pem" -out "$WORK/cert.pem" 2>/dev/null
make_db "$WORK/db2.jsonl" 600 600 2
"${ENCODE[@]}" "$WORK/db2.jsonl" --out "$WORK/out2" --c 16 --shard-mib 1 >"$WORK/enc2.out" 2>"$WORK/enc2.log" \
  || { cat "$WORK/enc2.out" "$WORK/enc2.log"; fail "encoder"; }
grep -E "m = |total communication|^R: " "$WORK/enc2.out"
serve "$WORK/out2" https
NODE_EXTRA_CA_CERTS="$WORK/cert.pem" node e2e/retrieve_all.mjs "$WORK/db2.jsonl" "$RETRIEVAL" "$COMPUTE" 40
[[ $(http_version "$COMPUTE/.well-known/rc-pir.json" --cacert "$WORK/cert.pem") == 2 ]] || fail "compute server: no HTTP/2 over TLS"
echo "ok: compute server negotiates HTTP/2 over TLS (ALPN)"
stop

echo "end-to-end test passed"
