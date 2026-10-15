"""B1: communication and storage of the RC-PIR for a 1 GiB database (analytic, from the encoder's
LPN parameter selection, Mode A, lambda = 128).

For each storage factor c, picks the shape t x ell (t * ell = n, both powers of two) with the
smallest total communication. Ignores the 4-byte block header of db_format.md.
Usage: python3 benchmarks/comm.py > benchmarks/results/comm.md
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "encoder/src"), str(ROOT / "common/src")]
from rcpir_encoder import lpn  # noqa: E402

LOG_N = 33          # 1 GiB
CS = (2, 4, 8, 16, 256)


def kib(bits):
    return f"{bits / 8 / 1024:.1f}"


rows = []
for c in CS:
    shapes = [lpn.mode_a(128, 2**k, 2 ** (LOG_N - k), c) for k in range(12, 25)]
    rows.append(min(shapes, key=lambda sel: sel.comm.total))

print(f"n = 2^{LOG_N} bits (1 GiB), lambda = 128, Q = 2^{lpn.LOG2_Q}. Sizes in KiB.\n")
print("| c | t | ell | s | retrieval storage | compute up | compute down | retrieval up | retrieval down | total |")
print("|---|---|---|---|---|---|---|---|---|---|")
for sel in rows:
    cm = sel.comm
    print(f"| {sel.mode_input['c']} | 2^{sel.t.bit_length() - 1} | 2^{sel.ell.bit_length() - 1} | {sel.s} "
          f"| {sel.storage_bits / 8 / 2**30:.0f} GiB | {kib(cm.compute_up)} | {kib(cm.compute_down)} "
          f"| {kib(cm.retrieval_up)} | {kib(cm.retrieval_down)} | {kib(cm.total)} |")
