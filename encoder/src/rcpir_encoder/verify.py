"""Step 6 of the encoder (docs/encoder.md §2): spot check of R = XH on random columns.

Recomputes k random columns of R with the CPU backend (`gf2.matmul_cpu`, independent of the CUDA
kernel) and compares them with the columns in the shards. Catches systematic errors (kernel, layout, padding,
writes, resume): if a fraction f of the columns is wrong, the check passes with probability <= (1-f)^k.
It does not catch rare isolated errors (e.g. a single bit flip). Cost: k t ell bit operations on the CPU.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

import numpy as np
from rcpir_common import hprg, protocol

from . import gf2

SPOT_CHECK_COLUMNS = 1000


class VerificationError(ValueError):
    pass


def read_column(site: Path, j: int, columns_per_shard: int, L: int) -> bytes:
    """Column j of R from its shard in the site directory (protocol.md §2)."""
    path, offset = protocol.column_location(j, columns_per_shard, L)
    with open(site / path.lstrip("/"), "rb") as f:
        f.seek(offset)
        return f.read(L)


def verify(site: Path, params: dict, X: np.ndarray, k: int = SPOT_CHECK_COLUMNS) -> None:
    """Compare min(k, m) distinct random columns of R with X H_{*,j} recomputed on the CPU."""
    t, L, m = params["t"], params["L"], params["m"]
    seed = bytes.fromhex(params["h_seed"])
    cols = np.random.default_rng(secrets.randbits(128)).choice(m, size=min(k, m), replace=False)
    step = gf2.panel_cols(t, L)
    for c0 in range(0, len(cols), step):
        js = cols[c0:c0 + step]
        H = np.frombuffer(b"".join(hprg.h_column(seed, t, int(j)) for j in js), dtype=np.uint8)
        expected = gf2.matmul_cpu(X, H.reshape(len(js), -1), t)
        for j, col in zip(js, expected):
            if read_column(site, int(j), params["columns_per_shard"], L) != col.tobytes():
                raise VerificationError(f"verification failed: column {j} of R != X H_{{*,{j}}}")
    print(f"verify: OK (spot check of {len(cols)} of {m} columns of R)", file=sys.stderr, flush=True)
