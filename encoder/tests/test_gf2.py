import numpy as np
import pytest
from rcpir_common import hprg

from conftest import SEED
from rcpir_encoder import gf2
from rcpir_encoder.gf2 import matmul_cpu


def bit_matrix_reference(X, H, t):
    """R = X H with unpacked 0/1 integer matrices (third independent formulation)."""
    L = X.shape[1]
    Xb = np.unpackbits(X, axis=1, bitorder="big").astype(np.int64)            # (t, ell): X^T
    Hb = np.unpackbits(H, axis=1, count=t, bitorder="big").astype(np.int64)   # (mp, t):  H^T
    Rt = (Hb @ Xb) % 2                                                       # (mp, ell): R^T
    return np.packbits(Rt.astype(np.uint8), axis=1, bitorder="big")[:, :L]


@pytest.mark.parametrize("t,L,mp", [(1, 8, 3), (3, 16, 40), (13, 8, 17), (64, 24, 64), (257, 40, 33)])
def test_matmul_cpu(rng, t, L, mp):
    X = rng.integers(0, 256, size=(t, L), dtype=np.uint8)
    H = hprg.h_panel(SEED, t, 5, mp)
    assert np.array_equal(matmul_cpu(X, H, t), bit_matrix_reference(X, H, t))


def test_matmul_cpu_tiling(rng, monkeypatch):
    t, L, mp = 203, 48, 29
    X = rng.integers(0, 256, size=(t, L), dtype=np.uint8)
    H = hprg.h_panel(SEED, t, 0, mp)
    monkeypatch.setattr(gf2, "TEMP_MEMORY_BUDGET_BYTES", 1 << 15)       # tiles of a few bytes per column
    assert gf2.tile_bytes(t, mp) < L
    assert np.array_equal(matmul_cpu(X, H, t), bit_matrix_reference(X, H, t))


@pytest.mark.parametrize("t,L,mp", [(1, 8, 3), (257, 40, 33), (4097, 129, 300), (70000, 70, 513)])
def test_matmul_cuda(rng, t, L, mp):
    """Bit-identical to the CPU backend; shapes not multiples of the kernel tiles (rows, columns, t)."""
    pytest.importorskip("cupy")
    from rcpir_encoder.gf2_cuda import matmul_cuda
    X = rng.integers(0, 256, size=(t, L), dtype=np.uint8)
    H = hprg.h_panel(SEED, t, 3, mp)
    assert np.array_equal(matmul_cuda(X, H, t), matmul_cpu(X, H, t))
