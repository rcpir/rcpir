"""MSB-first packing of F_2 vectors (docs/db_format.md §3).

Element 8b+k of a packed vector is bit 7-k of byte b; unused trailing bits of the last byte are zero.
The same rule packs columns of X, H and R and the compute query q_c.
"""

from __future__ import annotations


def tail_mask(t: int) -> int:
    """Mask of the last byte of a packed t-bit vector that keeps rows < t and clears the rest."""
    return (0xFF << (-t % 8)) & 0xFF


def pack_bits(bits) -> bytes:
    """Pack a sequence of 0/1 values (element 0 first)."""
    out = bytearray((len(bits) + 7) // 8)
    for r, v in enumerate(bits):
        if v:
            out[r >> 3] |= 0x80 >> (r & 7)
    return bytes(out)


def flip_bit(buf, i: int) -> None:
    """Flip element i of a packed vector in place (bytearray or uint8 array)."""
    buf[i >> 3] ^= 0x80 >> (i & 7)


def is_well_formed(packed: bytes, t: int) -> bool:
    """Exactly ceil(t/8) bytes and the unused trailing bits are zero (what the compute server checks)."""
    return len(packed) == (t + 7) // 8 and (t % 8 == 0 or packed[-1] & ~tail_mask(t) & 0xFF == 0)
