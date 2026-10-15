"""`aes128-ctr-col-v1`: expansion of `h_seed` into H in F_2^{t x m} (docs/h_prg.md).

Column j, packed MSB-first in ceil(t/8) bytes, is the AES-128-CTR keystream with initial counter
block BE64(j) || BE64(0), with the unused trailing bits of the last byte cleared.
"""

import numpy as np
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .bits import tail_mask

H_PRG = "aes128-ctr-col-v1"


def h_column(seed: bytes, t: int, j: int) -> bytes:
    """One packed column H[*, j] (the snippet of h_prg.md §2)."""
    enc = Cipher(algorithms.AES(seed), modes.CTR(j.to_bytes(8, "big") + bytes(8))).encryptor()
    col = bytearray(enc.update(bytes((t + 7) // 8)))
    col[-1] &= tail_mask(t)
    return bytes(col)


def h_panel(seed: bytes, t: int, j0: int, count: int) -> np.ndarray:
    """Columns j0 .. j0+count-1 as a (count, ceil(t/8)) uint8 array, one packed column per row.

    Same output as `h_column`. One CTR encryptor per column: ~5 GB/s for large t, against ~0.7 GB/s
    for a single ECB call over explicit counter blocks (building the counters dominated).
    """
    B = (t + 7) // 8
    aes, zeros = algorithms.AES(seed), bytes(B)
    panel = np.empty((count, B), dtype=np.uint8)
    for k in range(count):
        ctr = Cipher(aes, modes.CTR((j0 + k).to_bytes(8, "big") + bytes(8))).encryptor()
        panel[k] = np.frombuffer(ctr.update(zeros), dtype=np.uint8)
    panel[:, -1] &= tail_mask(t)
    return panel
