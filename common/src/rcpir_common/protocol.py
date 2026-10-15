"""Names fixed by the wire protocol (docs/protocol.md) and digest strings (docs/params_format.md)."""

from __future__ import annotations

import hashlib

WELL_KNOWN_PATH = "/.well-known/rc-pir.json"
QUERY_PATH = "/rc-pir/query"
DIGEST_HEADER = "RC-PIR-DB-Digest"


def shard_path(k: int) -> str:
    """URL path of shard k of R: /rc-pir/r/<k as 8 lowercase hex digits> (§2)."""
    return f"/rc-pir/r/{k:08x}"


def column_location(j: int, columns_per_shard: int, L: int) -> tuple[str, int]:
    """(shard path, byte offset) of column j of R; the column is the L bytes from the offset (§2)."""
    return shard_path(j // columns_per_shard), (j % columns_per_shard) * L


def digest_tag(hexdigest: str) -> str:
    """'sha256:<hex>' as used by db_digest, r_digest and the RC-PIR-DB-Digest header."""
    return f"sha256:{hexdigest}"


def sha256_tag(data: bytes) -> str:
    return digest_tag(hashlib.sha256(data).hexdigest())
