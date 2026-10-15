"""rcpir_common against the cross-language vectors (testvectors/vectors/)."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from rcpir_common import bits, blocks, hprg, params, protocol

VEC = Path(__file__).resolve().parents[2] / "testvectors" / "vectors"


def load(name: str) -> dict:
    return json.loads((VEC / name).read_text())


# ---------------------------------------------------------------------------------------------
# h_prg

def test_h_column_vectors():
    for c in load("h_prg.json")["cases"]:
        col = hprg.h_column(bytes.fromhex(c["h_seed"]), c["t"], c["j"])
        assert len(col) == c["nbytes"]
        if "col_hex" in c:
            assert col.hex() == c["col_hex"], c
        else:
            assert hashlib.sha256(col).hexdigest() == c["col_sha256"], c


def test_h_panel_vectors():
    cases = [c for c in load("h_prg.json")["cases"] if "col_hex" in c]
    for c in cases:
        panel = hprg.h_panel(bytes.fromhex(c["h_seed"]), c["t"], c["j"], 1)
        assert panel[0].tobytes().hex() == c["col_hex"], c


# ---------------------------------------------------------------------------------------------
# bit packing and q_c

def test_bitpack_vectors():
    v = load("bitpack.json")
    for c in v["valid"]:
        packed = bits.pack_bits([int(b) for b in c["bits"]])
        assert packed.hex() == c["packed_hex"], c["name"]
        assert bits.is_well_formed(packed, c["t"])
        assert np.packbits(np.array([int(b) for b in c["bits"]], np.uint8)).tobytes() == packed  # numpy agrees
    for c in v["invalid"]:
        assert not bits.is_well_formed(bytes.fromhex(c["packed_hex"]), c["t"]), c["name"]


def test_qc_vectors():
    for c in load("qc.json")["cases"]:
        seed, t = bytes.fromhex(c["h_seed"]), c["t"]
        q = bytearray((t + 7) // 8)
        for j in c["S"]:
            q = bytearray(a ^ b for a, b in zip(q, hprg.h_column(seed, t, j)))
        bits.flip_bit(q, c["i"])
        assert q.hex() == c["qc_hex"], c["name"]


# ---------------------------------------------------------------------------------------------
# paths, blocks, params

def test_column_location_vectors():
    for c in load("column_location.json")["cases"]:
        assert protocol.column_location(c["j"], c["columns_per_shard"], c["L"]) == (c["path"], c["offset"])


def test_db_format_packing_vectors():
    for c in load("db_format.json")["valid"]:
        payloads = [bytes.fromhex(h) for h in c["payloads_hex"]]
        L = blocks.column_bytes(max(map(len, payloads)))
        assert L == c["L"], c["name"]
        x = b"".join(blocks.encode_column(p, L) for p in payloads)
        assert x.hex() == c["x_bin_hex"], c["name"]
        assert protocol.sha256_tag(x) == c["db_digest"]


def test_db_format_decode_vectors():
    for c in load("db_format.json")["decode"]:
        col = bytes.fromhex(c["column_hex"])
        if "payload_hex" in c:
            assert blocks.decode_column(col).hex() == c["payload_hex"], c["name"]
        elif c["error"] == "length_too_large":
            with pytest.raises(ValueError):
                blocks.decode_column(col)
        else:   # wrong_column_length: the caller checks len(col) == L before decoding
            assert len(col) != c["L"]


def test_params_vectors():
    v = load("params.json")
    for c in v["valid"]:
        params.validate(c["params"])
        assert params.is_insecure(c["params"]) == c["insecure_override"], c["name"]
    for c in v["invalid"]:
        with pytest.raises(params.ParamsError):
            params.validate(c["params"])
            pytest.fail(c["name"])


def test_params_rejects_bool_and_float():
    p = load("params.json")["valid"][0]["params"]
    for bad in (True, 3.0):
        with pytest.raises(params.ParamsError):
            params.validate({**p, "s": bad})
