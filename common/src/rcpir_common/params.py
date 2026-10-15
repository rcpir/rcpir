"""params.json constants and validation (docs/params_format.md §1, §4).

The same rules are implemented by the client (client/src/params.ts) and the compute server
(server/crates/rcpir-core/src/params.rs); all three are checked against testvectors/vectors/params.json.
"""

from __future__ import annotations

import re

from .hprg import H_PRG

FORMAT_VERSION = 1
NOISE = "fixed-weight"
M_LIMIT = 2**32
INSECURE_MODE = "insecure-override"

INTEGER_FIELDS = ("format_version", "t", "ell", "L", "m", "s", "columns_per_shard")
STRING_FIELDS = ("h_prg", "h_seed", "noise", "db_digest", "r_digest")

_SEED = re.compile(r"[0-9a-f]{32}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class ParamsError(ValueError):
    pass


def validate(p: dict) -> None:
    """Raise ParamsError unless `p` (parsed params.json) satisfies §4.

    The 12 protocol fields are required; metadata (`security`, `created`, `encoder_version`) is
    optional and unknown fields are ignored.
    """
    if not isinstance(p, dict):
        raise ParamsError("params.json is not a JSON object")
    for k in INTEGER_FIELDS:
        if type(p.get(k)) is not int:          # excludes bool, float and missing
            raise ParamsError(f'"{k}" must be an integer')
    for k in STRING_FIELDS:
        if not isinstance(p.get(k), str):
            raise ParamsError(f'"{k}" must be a string')
    checks = [
        (p["format_version"] == FORMAT_VERSION, f"format_version must be {FORMAT_VERSION}"),
        (p["h_prg"] == H_PRG, f"unknown h_prg {p['h_prg']!r}"),
        (p["noise"] == NOISE, f"unknown noise {p['noise']!r}"),
        (p["t"] >= 1, "t must be >= 1"),
        (1 <= p["s"] <= p["m"] <= M_LIMIT, "need 1 <= s <= m <= 2^32"),
        (p["L"] >= 8 and p["L"] % 8 == 0, "L must be >= 8 and a multiple of 8"),
        (p["ell"] == 8 * p["L"], "ell must equal 8 * L"),
        (1 <= p["columns_per_shard"] <= p["m"], "need 1 <= columns_per_shard <= m"),
        (_SEED.fullmatch(p["h_seed"]) is not None, "h_seed must be 32 lowercase hex characters"),
        (_DIGEST.fullmatch(p["db_digest"]) is not None, "db_digest must be sha256:<64 lowercase hex>"),
        (_DIGEST.fullmatch(p["r_digest"]) is not None, "r_digest must be sha256:<64 lowercase hex>"),
    ]
    for ok, msg in checks:
        if not ok:
            raise ParamsError(msg)


def is_insecure(p: dict) -> bool:
    """True if `security` marks the test-only insecure override (encoder --insecure-m/--insecure-s)."""
    sec = p.get("security")
    return isinstance(sec, dict) and (sec.get("insecure") is True or sec.get("mode") == INSECURE_MODE)
