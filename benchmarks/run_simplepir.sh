#!/usr/bin/env bash
# SimplePIR / DoublePIR on a 1 GiB database (2^33 x 1-bit entries), single thread, using the
# authors' own benchmarks (github.com/ahenzinger/simplepir, pinned commit). Needs Go >= 1.18.
# Pass "recover" to also measure their decode time, or "batch" for their batch benchmarks (Fig. 9, ~1.5 compute-hours).
set -euo pipefail
cd "$(dirname "$0")"
COMMIT=e9020b03bf2872c75b8954e749e32408b5db87ed
[ -d simplepir ] || git clone -q https://github.com/ahenzinger/simplepir simplepir
git -C simplepir checkout -q "$COMMIT"
mkdir -p results
cd simplepir/pir
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
