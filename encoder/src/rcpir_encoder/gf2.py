"""R = X H over F_2 for one column panel of H (`gf2_matmul`, docs/encoder.md §3).

All arrays use the packed on-disk layouts (MSB-first, one column per row):

    X       (t, L) uint8            X[r] = column r of X (may be an np.memmap of X.bin)
    H       (mp, ceil(t/8)) uint8   H[k] = column k of the panel, as returned by hprg.h_panel
    result  (mp, L) uint8           row k = column k of the R panel = XOR of the X[r] with H[r, k] = 1
                                    (exactly the bytes of the column in its shard)

The CUDA backend (gf2_cuda.py) provides a function with the same signature (see get_backend).
"""

import numpy as np

TEMP_MEMORY_BUDGET_BYTES = 1 << 30         # rough memory budget for one call


def panel_cols(t: int, L: int) -> int:
    """Panel width: the unpacked H panel (4 bytes per bit) and the output each fit in the budget."""
    return max(1, min(TEMP_MEMORY_BUDGET_BYTES // (8 * t), TEMP_MEMORY_BUDGET_BYTES // (4 * L)))


def tile_bytes(t: int, mp: int) -> int:
    """Bytes of each column per tile of matmul_cpu, so that the tile's temporaries fit in the budget.

    A tile of b bytes holds two float32 arrays, Xf (t x 8b) and the product (mp x 8b), i.e.
    32 b (t + mp) bytes; the factor 2 covers their temporary copies (unpacked uint8, int32 casts).
    """
    return max(1, TEMP_MEMORY_BUDGET_BYTES // (64 * (t + mp)))


def matmul_cpu(X: np.ndarray, H: np.ndarray, t: int) -> np.ndarray:
    """Unpack bits, multiply with float32 BLAS, keep the parity, repack.

    float32 represents the integer sums exactly as long as they are <= 2^24, i.e. t <= 2^24.
    The byte range of the X columns is processed in tiles to bound memory.
    """
    if t > 2**24:
        raise ValueError("the CPU backend supports t <= 2^24")
    mp, L = H.shape[0], X.shape[1]
    Hf = np.unpackbits(H, axis=1, count=t).astype(np.float32)          # (mp, t): panel of H^T
    out = np.empty((mp, L), dtype=np.uint8)
    step = tile_bytes(t, mp)
    for b0 in range(0, L, step):
        Xf = np.unpackbits(X[:, b0:b0 + step], axis=1).astype(np.float32)   # (t, 8*step): tile of X^T
        counts = (Hf @ Xf).astype(np.int32)                             # exact integer sums
        out[:, b0:b0 + step] = np.packbits(counts & 1, axis=1)
    return out


def get_backend(device: str):
    """(matmul, panel_cols) of the device. `cuda` needs CuPy (imported only here)."""
    if device == "cpu":
        return matmul_cpu, panel_cols
    if device == "cuda":
        try:
            from . import gf2_cuda
        except ImportError as e:
            raise ValueError(f"--device cuda needs CuPy ({e})") from e
        return gf2_cuda.matmul_cuda, gf2_cuda.panel_cols
    raise ValueError(f"unknown device {device!r}")
