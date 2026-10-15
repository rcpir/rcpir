"""Block <-> column encoding (docs/db_format.md §3).

    column_j = u32_be(len(payload)) | payload | zero padding     (exactly L bytes)
    L = roundup_8(4 + max_j len(payload_j))
"""

from __future__ import annotations

HEADER_BYTES = 4
MAX_PAYLOAD = 2**32 - 1


def column_bytes(max_payload: int) -> int:
    """L for a database whose largest payload has `max_payload` bytes."""
    return (HEADER_BYTES + max_payload + 7) // 8 * 8


def encode_column(payload: bytes, L: int) -> bytes:
    return len(payload).to_bytes(HEADER_BYTES, "big") + payload.ljust(L - HEADER_BYTES, b"\0")


def decode_column(col: bytes) -> bytes:
    """Recover the payload from a column; rejects a header with len > L-4. Padding is not checked."""
    n = int.from_bytes(col[:HEADER_BYTES], "big")
    if n > len(col) - HEADER_BYTES:
        raise ValueError(f"invalid block header: length {n} > L-4 = {len(col) - HEADER_BYTES}")
    return bytes(col[HEADER_BYTES:HEADER_BYTES + n])
