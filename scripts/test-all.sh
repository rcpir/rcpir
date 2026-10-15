#!/usr/bin/env bash
# Runs every test: vectors, Python (common + encoder), client, server, then the end-to-end test.
#   scripts/test-all.sh
# On the first run it creates what is missing: the Python env in .env/ (conda, from environment.yml)
# and client/node_modules (npm install). Set PY=/path/to/python to use another interpreter
# (it needs numpy, cryptography and pytest).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PY=${PY:-$ROOT/.env/bin/python}
cd "$ROOT"

fail() { echo "error: $*" >&2; exit 1; }

# --- prerequisites -----------------------------------------------------------------------------
for tool in cargo node npm curl openssl; do
  command -v "$tool" >/dev/null || fail "'$tool' is not on PATH"
done
if [[ ! -x $PY ]]; then
  [[ $PY == "$ROOT/.env/bin/python" ]] || fail "PY=$PY does not exist"
  CONDA=$(command -v conda || command -v mamba || ls "$HOME"/miniforge3/bin/conda 2>/dev/null || true)
  [[ -n $CONDA ]] || fail "no Python env in .env/ and no conda found; create one from environment.yml or set PY"
  echo "== setup: creating the Python env in .env/ (conda env create -p .env -f environment.yml)"
  "$CONDA" env create -q -p "$ROOT/.env" -f environment.yml
fi
if [[ ! -d client/node_modules ]]; then
  echo "== setup: npm install (client dev dependencies)"
  (cd client && npm install --silent)
fi

# --- tests -------------------------------------------------------------------------------------
echo "== test vectors";  "$PY" testvectors/gen.py --check; echo "vectors up to date"
echo "== common";        (cd common && "$PY" -m pytest -q)
echo "== encoder";       (cd encoder && "$PY" -m pytest -q)
echo "== client";        (cd client && npm test --silent 2>&1 | grep -E "^ℹ (tests|pass|fail)")
echo "== server";        (cd server && cargo test -q 2>&1 | grep -E "^test result" && cargo clippy -q --all-targets -- -D warnings)
echo "== end to end";    PY="$PY" e2e/run.sh
echo "all tests passed"
