#!/usr/bin/env python3
"""Generator for the RC-PIR cross-language test vectors.

Uses the shared spec primitives of `common/` (rcpir_common: h_prg, bit packing, column
encoding, paths, digests) but not the encoder; the client (TypeScript) and the server (Rust)
check the vectors independently. It writes the JSON files in `vectors/`:

    h_prg.json         docs/h_prg.md         columns of H from h_seed (aes128-ctr-col-v1)
    bitpack.json       docs/db_format.md §3  MSB-first packing of F_2 vectors (e.g. q_c)
    qc.json            docs/protocol.md §4   q_c = XOR of h_prg columns in S, bit i flipped
    column_location.json  docs/protocol.md §2  shard path and byte offset of column j of R
    db_format.json     docs/db_format.md     JSONL -> X.bin, column decoding, invalid inputs
    params.json        docs/params_format.md §4  params.json validation fixtures

Usage:
    python gen.py            # (re)write vectors/*.json
    python gen.py --check    # exit 1 if vectors/*.json differ from what would be generated

All output is deterministic (no clock, no OS randomness).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common" / "src"))

from rcpir_common.bits import pack_bits  # noqa: E402
from rcpir_common.blocks import column_bytes, encode_column  # noqa: E402
from rcpir_common.hprg import h_column  # noqa: E402
from rcpir_common.protocol import column_location, sha256_tag  # noqa: E402

OUT_DIR = HERE / "vectors"
FORMAT = "rc-pir-testvectors"
VERSION = 1

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------


def det_bytes(label: str, n: int) -> bytes:
    """Deterministic pseudo-random bytes (SHA-256 in counter mode); only used to make test data."""
    out = bytearray()
    ctr = 0
    while len(out) < n:
        out += hashlib.sha256(f"{label}/{ctr}".encode()).digest()
        ctr += 1
    return bytes(out[:n])


# ---------------------------------------------------------------------------
# 1. h_prg
# ---------------------------------------------------------------------------

H_SEEDS = [
    "00000000000000000000000000000000",
    "000102030405060708090a0b0c0d0e0f",
    "3f9c0a1b2c3d4e5f60718293a4b5c6e1",  # the example seed of docs/params_format.md §3
]
H_TS = [1, 7, 8, 9, 127, 128, 129, 1000, 131072]
H_JS = [0, 1, 255, 256, 2**31, 2**32 - 1]
H_FULL_HEX_MAX_T = 1000  # larger columns are given as sha256 + prefix/suffix


def gen_h_prg() -> dict:
    cases = []
    for seed_hex in H_SEEDS:
        seed = bytes.fromhex(seed_hex)
        for t in H_TS:
            for j in H_JS:
                col = h_column(seed, t, j)
                case = {"h_seed": seed_hex, "t": t, "j": j, "nbytes": len(col)}
                if t <= H_FULL_HEX_MAX_T:
                    case["col_hex"] = col.hex()
                else:
                    case["col_sha256"] = hashlib.sha256(col).hexdigest()
                    case["col_prefix_hex"] = col[:32].hex()
                    case["col_suffix_hex"] = col[-32:].hex()
                cases.append(case)
    return {
        "format": FORMAT,
        "version": VERSION,
        "file": "h_prg",
        "spec": "docs/h_prg.md",
        "h_prg": "aes128-ctr-col-v1",
        "description": (
            "Packed column H[*,j] (ceil(t/8) bytes, MSB-first, unused trailing bits zero) expanded from "
            "h_seed. For t > %d only sha256(col) and the first/last 32 bytes are given." % H_FULL_HEX_MAX_T
        ),
        "cases": cases,
    }


# ---------------------------------------------------------------------------
# 2. bit packing
# ---------------------------------------------------------------------------


def bit_patterns(t: int) -> list[tuple[str, list[int]]]:
    pats = [
        ("zeros", [0] * t),
        ("ones", [1] * t),
        ("alternating_10", [1 - (r % 2) for r in range(t)]),
        ("first", [1 if r == 0 else 0 for r in range(t)]),
        ("last", [1 if r == t - 1 else 0 for r in range(t)]),
    ]
    if t > 8:
        pats.append(("bit7_bit8", [1 if r in (7, 8) else 0 for r in range(t)]))
    if t > 16:
        rnd = det_bytes(f"bitpack/{t}", t)
        pats.append(("pseudorandom", [b & 1 for b in rnd]))
    return pats


def gen_bitpack() -> dict:
    valid = []
    for t in [1, 7, 8, 9, 15, 16, 17, 64, 100]:
        for name, bits in bit_patterns(t):
            valid.append(
                {
                    "name": f"t{t}_{name}",
                    "t": t,
                    "bits": "".join(map(str, bits)),
                    "packed_hex": pack_bits(bits).hex(),
                }
            )
    invalid = [
        {"name": "t1_trailing_bit_set", "t": 1, "packed_hex": "c0", "reason": "trailing_bits_nonzero"},
        {"name": "t1_lowest_bit_set", "t": 1, "packed_hex": "01", "reason": "trailing_bits_nonzero"},
        {"name": "t7_last_bit_set", "t": 7, "packed_hex": "01", "reason": "trailing_bits_nonzero"},
        {"name": "t9_trailing_bit_set", "t": 9, "packed_hex": "ff40", "reason": "trailing_bits_nonzero"},
        {"name": "t100_trailing_bit_set", "t": 100, "packed_hex": "00" * 12 + "01", "reason": "trailing_bits_nonzero"},
        {"name": "t9_too_short", "t": 9, "packed_hex": "ff", "reason": "wrong_length"},
        {"name": "t8_too_long", "t": 8, "packed_hex": "ff00", "reason": "wrong_length"},
        {"name": "t16_empty", "t": 16, "packed_hex": "", "reason": "wrong_length"},
    ]
    return {
        "format": FORMAT,
        "version": VERSION,
        "file": "bitpack",
        "spec": "docs/db_format.md §3, docs/protocol.md §3",
        "description": (
            "MSB-first packing of a vector in F_2^t into ceil(t/8) bytes: element 8b+k is bit 7-k of byte b, "
            "unused trailing bits are zero. 'bits' lists elements 0..t-1 in order. 'invalid' are byte strings "
            "a receiver of a t-bit vector (e.g. the compute server parsing q_c) must reject."
        ),
        "valid": valid,
        "invalid": invalid,
    }


# ---------------------------------------------------------------------------
# 3. q_c construction
# ---------------------------------------------------------------------------

QC_CASES = [
    ("small", "000102030405060708090a0b0c0d0e0f", 9, 64, [0, 5, 63], 8),
    ("t1", "000102030405060708090a0b0c0d0e0f", 1, 4, [3], 0),
    ("i_zero", "3f9c0a1b2c3d4e5f60718293a4b5c6e1", 1000, 16000, [17, 2048, 9999, 15999], 0),
    ("i_last", "3f9c0a1b2c3d4e5f60718293a4b5c6e1", 1000, 16000, [1, 2, 3], 999),
    ("j_large", "00000000000000000000000000000000", 129, 2**32, [2**31, 2**32 - 1, 0], 128),
    ("unsorted_S", "3f9c0a1b2c3d4e5f60718293a4b5c6e1", 127, 1000, [999, 3, 500, 42, 7], 64),
]


def gen_qc() -> dict:
    cases = []
    for name, seed_hex, t, m, S, i in QC_CASES:
        seed = bytes.fromhex(seed_hex)
        acc = bytearray((t + 7) // 8)
        for j in S:
            for k, b in enumerate(h_column(seed, t, j)):
                acc[k] ^= b
        acc[i >> 3] ^= 0x80 >> (i & 7)
        cases.append(
            {"name": name, "h_seed": seed_hex, "t": t, "m": m, "S": S, "i": i, "qc_hex": bytes(acc).hex()}
        )
    return {
        "format": FORMAT,
        "version": VERSION,
        "file": "qc",
        "spec": "docs/protocol.md §4 step 3, docs/h_prg.md",
        "description": (
            "Compute-server query q_c = XOR_{j in S} H[*,j] + e_i, packed MSB-first (ceil(t/8) bytes). "
            "S is given as a list (order irrelevant, elements distinct, each < m); i is the block index (< t)."
        ),
        "cases": cases,
    }


# ---------------------------------------------------------------------------
# 4. column locations (shards)
# ---------------------------------------------------------------------------


def gen_column_location() -> dict:
    # (j, columns_per_shard, L): one column per shard, first/last column of a shard, and the shape of a
    # 64 MiB bound with L = 424 (columns_per_shard = floor(2^26 / 424) = 158275).
    cases = [(0, 1, 8), (5, 1, 8), (2**32 - 1, 1, 8),
             (0, 16384, 4096), (16383, 16384, 4096), (16384, 16384, 4096), (2**32 - 1, 16384, 4096),
             (158274, 158275, 424), (158275, 158275, 424), (2532399, 158275, 424)]
    out = []
    for j, cps, L in cases:
        path, offset = column_location(j, cps, L)
        out.append({"j": j, "columns_per_shard": cps, "L": L, "path": path, "offset": offset})
    return {
        "format": FORMAT,
        "version": VERSION,
        "file": "column_location",
        "spec": "docs/protocol.md §2",
        "description": ("Column j of R is the L bytes at 'offset' in the shard at 'path' "
                        "(shard j // columns_per_shard, 8 lowercase hex digits; offset (j % columns_per_shard) * L)."),
        "cases": out,
    }


# ---------------------------------------------------------------------------
# 5. db_format
# ---------------------------------------------------------------------------


def jsonl_line(payload: bytes, **extra) -> str:
    obj = {"data": base64.b64encode(payload).decode()}
    obj.update(extra)
    return json.dumps(obj, separators=(", ", ": "))


def pack_db(payloads: list[bytes]) -> tuple[int, bytes]:
    L = column_bytes(max(len(p) for p in payloads))
    return L, b"".join(encode_column(p, L) for p in payloads)


def text_case(name: str, note: str, text: str, payloads: list[bytes]) -> dict:
    raw = text.encode("utf-8")
    L, x = pack_db(payloads)
    return {
        "name": name,
        "note": note,
        "jsonl": text,
        "jsonl_hex": raw.hex(),
        "t": len(payloads),
        "max_payload": max(len(p) for p in payloads),
        "sum_payload": sum(len(p) for p in payloads),
        "L": L,
        "ell": 8 * L,
        "payloads_hex": [p.hex() for p in payloads],
        "x_bin_hex": x.hex(),
        "db_digest": sha256_tag(x),
    }


def gen_db_valid() -> list[dict]:
    cases = []

    # Spec example (docs/db_format.md §2).
    text = '{"data": "SGVsbG8gd29ybGQ="}\n{"data": "", "key": "empty-block"}\n{"data": "AAECAwQ="}\n'
    cases.append(
        text_case("spec_example", "Example of docs/db_format.md §2.", text, [b"Hello world", b"", bytes(range(5))])
    )

    # Single empty block: smallest possible DB, L = 8.
    cases.append(text_case("single_empty", "t=1, empty payload, L=8.", '{"data": ""}\n', [b""]))

    # max payload 4 -> 4+4 = 8 exactly, L = 8.
    p = [b"abcd", b"x"]
    cases.append(
        text_case("fill_L8", "Largest payload is 4 bytes, so 4+4 = L = 8 (payload fills L-4 exactly).",
                  "".join(jsonl_line(q) + "\n" for q in p), p)
    )

    # max payload 5 -> L = 16.
    p = [b"abcde"]
    cases.append(text_case("just_over_L8", "Payload of 5 bytes forces L = 16.", jsonl_line(p[0]) + "\n", p))

    # t = 9 (not a multiple of 8); lengths 0..7 and 12 (12 fills L-4 = 12 exactly).
    p = [det_bytes(f"t9/{k}", n) for k, n in enumerate([0, 1, 2, 3, 4, 5, 6, 7, 12])]
    cases.append(
        text_case("t9_mixed_exact_fill",
                  "t=9 (not a multiple of 8); block 8 has 12 bytes and fills L-4 exactly (L=16).",
                  "".join(jsonl_line(q) + "\n" for q in p), p)
    )

    # No trailing newline; extra fields of various types, unicode, field order, whitespace.
    text = (
        '{"key": "first", "data": "AQID"}\n'
        '{"data":"/w==","n":1,"nested":{"a":[1,2,3]},"flag":true,"nothing":null}\n'
        '  {  "k\\u00e9y" : "été ☃" , "data" : "+/+/"  }  \n'
        '{"data": "AAAAAAAAAAAAAAAAAAAAAA=="}'
    )
    p = [bytes([1, 2, 3]), bytes([0xFF]), bytes([0xFB, 0xFF, 0xBF]), bytes(16)]
    cases.append(
        text_case("extra_fields_no_trailing_newline",
                  "Other fields are ignored (any type, any order, non-ASCII, surrounding JSON whitespace). "
                  "The last line has no trailing newline. Base64 uses '+' and '/'. Block 3 is all zeros.",
                  text, p)
    )

    # Medium: t = 17, pseudorandom lengths up to 100.
    lens = [b % 101 for b in det_bytes("t17/lens", 17)]
    lens[5] = 100
    p = [det_bytes(f"t17/{k}", n) for k, n in enumerate(lens)]
    cases.append(
        text_case("t17_pseudorandom", "t=17, pseudorandom payloads, max 100 bytes (L=104).",
                  "".join(jsonl_line(q) + "\n" for q in p), p)
    )
    return cases


def gen_db_invalid() -> list[dict]:
    ok = '{"data": "AA=="}'

    def case(name: str, raw: bytes, line, reason: str, note: str) -> dict:
        c = {"name": name, "note": note, "jsonl_hex": raw.hex()}
        try:
            c["jsonl"] = raw.decode("utf-8")
        except UnicodeDecodeError:
            pass
        c["error_line"] = line
        c["reason"] = reason
        return c

    def lines(*ls: str, trailing: bool = True) -> bytes:
        return ("\n".join(ls) + ("\n" if trailing else "")).encode("utf-8")

    return [
        case("empty_file", b"", None, "empty_file", "Zero bytes."),
        case("only_newline", b"\n", 1, "blank_line", "A single blank line."),
        case("blank_line_middle", lines(ok, "", ok), 2, "blank_line", "Blank line between two valid lines."),
        case("blank_line_end", lines(ok, ok, ""), 3,
             "blank_line", "Two newlines at the end, i.e. a blank last line (one trailing newline is allowed)."),
        case("whitespace_only_line", lines(ok, "   "), 2, "blank_line",
             "Line with only spaces. Treated as blank (it is not a JSON value either)."),
        case("invalid_json_trailing_comma", lines(ok, '{"data": "AA==",}'), 2, "invalid_json", "Trailing comma."),
        case("invalid_json_truncated", lines(ok, ok, '{"data": "AA=='), 3, "invalid_json", "Unterminated string."),
        case("two_objects_one_line", lines('{"data": "AA=="} {"data": "AA=="}'), 1, "invalid_json",
             "Two JSON values on one line."),
        case("not_an_object_array", lines(ok, '["AA=="]'), 2, "not_an_object", "Top-level JSON array."),
        case("not_an_object_string", lines('"AA=="'), 1, "not_an_object", "Top-level JSON string."),
        case("missing_data", lines(ok, '{"key": "x"}'), 2, "missing_data", "No \"data\" field."),
        case("data_wrong_case", lines('{"Data": "AA=="}'), 1, "missing_data", "Field names are case-sensitive."),
        case("data_number", lines(ok, ok, '{"data": 5}'), 3, "data_not_string", "\"data\" is a number."),
        case("data_null", lines('{"data": null}'), 1, "data_not_string", "\"data\" is null."),
        case("data_array", lines('{"data": [0, 1]}'), 1, "data_not_string", "\"data\" is an array."),
        case("base64_bad_char", lines(ok, '{"data": "SGVsbG8*"}'), 2, "invalid_base64", "'*' is not in the alphabet."),
        case("base64_urlsafe", lines('{"data": "-_8="}'), 1, "invalid_base64",
             "URL-safe alphabet ('-', '_') is not standard base64."),
        case("base64_missing_padding", lines('{"data": "SGVsbG8"}'), 1, "invalid_base64",
             "Padding '=' is required (length not a multiple of 4)."),
        case("base64_extra_padding", lines('{"data": "AA==="}'), 1, "invalid_base64", "Too much padding."),
        case("base64_inner_space", lines('{"data": "SGVs bG8="}'), 1, "invalid_base64", "Space inside the string."),
        case("base64_escaped_newline", lines('{"data": "SGVs\\nbG8="}'), 1, "invalid_base64",
             "JSON-escaped newline inside the base64 string (MIME-style line breaks are not allowed)."),
        case("base64_padding_in_middle", lines('{"data": "AA==AA=="}'), 1, "invalid_base64",
             "Padding in the middle."),
        case("invalid_utf8", ok.encode() + b"\n" + b'{"data": "AA==", "key": "\xff"}\n', 2, "invalid_utf8",
             "Byte 0xff is not valid UTF-8 (in an ignored field, still an error: the file must be UTF-8)."),
    ]


def gen_db_decode() -> list[dict]:
    def col(L: int, length_field: int, body: bytes) -> bytes:
        c = length_field.to_bytes(4, "big") + body
        return c + bytes(L - len(c))

    cases = []

    def ok(name: str, L: int, payload: bytes, note: str, padding: bytes | None = None) -> None:
        c = col(L, len(payload), payload)
        if padding is not None:
            c = c[: 4 + len(payload)] + padding
            assert len(c) == L
        cases.append({"name": name, "note": note, "L": L, "column_hex": c.hex(), "payload_hex": payload.hex()})

    def bad(name: str, L: int, column: bytes, reason: str, note: str) -> None:
        cases.append({"name": name, "note": note, "L": L, "column_hex": column.hex(), "error": reason})

    ok("empty_L8", 8, b"", "len = 0.")
    ok("fill_L8", 8, b"abcd", "len = L-4 (largest allowed).")
    ok("fill_L16", 16, det_bytes("dec/16", 12), "len = L-4 with L = 16.")
    ok("short_L32", 32, b"\x00\x01\x02", "Payload of 3 bytes followed by zero padding.")
    ok("payload_with_zeros", 16, bytes(7), "Payload consisting of zero bytes (length comes from the header).")
    ok("nonzero_padding_ignored", 16, b"hi", "Padding bytes after the payload are not checked by the decoder.",
       padding=bytes([0xAA] * 10))
    bad("len_L_minus_3", 8, col(8, 5, b"abcd"), "length_too_large", "len = L-3 > L-4.")
    bad("len_L", 16, col(16, 16, det_bytes("dec/bad16", 12)), "length_too_large", "len = L.")
    bad("len_max_u32", 8, bytes.fromhex("ffffffff") + bytes(4), "length_too_large", "len = 2^32-1.")
    bad("len_high_byte", 64, bytes.fromhex("01000000") + bytes(60), "length_too_large",
        "len = 2^24: catches little-endian reading of the header.")
    bad("column_too_short", 16, col(16, 2, b"hi")[:15], "wrong_column_length", "Column has L-1 bytes.")
    bad("column_too_long", 8, col(8, 2, b"hi") + b"\x00", "wrong_column_length", "Column has L+1 bytes.")
    return cases


def gen_db_format() -> dict:
    return {
        "format": FORMAT,
        "version": VERSION,
        "file": "db_format",
        "spec": "docs/db_format.md",
        "description": (
            "valid: JSONL input (exact bytes in jsonl_hex; 'jsonl' is the same text) -> t, L, ell, the packed "
            "X.bin (column-major, t columns of L bytes, x_bin_hex) and db_digest = sha256(X.bin). "
            "invalid: inputs that must be rejected; error_line is 1-based (null for the empty file), 'reason' "
            "is informative. decode: column bytes (L given) -> payload, or rejection."
        ),
        "valid": gen_db_valid(),
        "invalid": gen_db_invalid(),
        "decode": gen_db_decode(),
    }


# ---------------------------------------------------------------------------
# 6. params.json validation
# ---------------------------------------------------------------------------


def base_params() -> dict:
    """The example of docs/params_format.md §3 with concrete digests."""
    return {
        "format_version": 1,
        "t": 131072,
        "ell": 32768,
        "L": 4096,
        "m": 2097152,
        "s": 45,
        "h_prg": "aes128-ctr-col-v1",
        "h_seed": "3f9c0a1b2c3d4e5f60718293a4b5c6e1",
        "noise": "fixed-weight",
        "db_digest": sha256_tag(b"rc-pir test vector: db"),
        "r_digest": sha256_tag(b"rc-pir test vector: r"),
        "columns_per_shard": 16384,
        "security": {
            "lambda": 128, "log2_Q": 32, "lambda_eff": 177, "c_eff": 16.0,
            "attack_bits": {"prange": 180.0, "mitm": 348.9, "brute_force": 697.9},
            "binding_attack": "prange",
            "mode": "A", "c": 16,
        },
        "created": "2026-10-09T12:00:00Z",
        "encoder_version": "0.1.0",
    }


def insecure_params() -> dict:
    """A tiny test DB encoded with the insecure override (--insecure-m 48 --insecure-s 4)."""
    p = base_params()
    p.update({"t": 3, "ell": 128, "L": 16, "m": 48, "s": 4, "columns_per_shard": 48})
    # As written by the encoder (lpn.Selection.security_object) for this override.
    p["security"] = {
        "lambda": 128, "log2_Q": 32, "lambda_eff": 162, "c_eff": 16.0,
        "attack_bits": {"prange": 16.0, "mitm": 7.2, "brute_force": 14.3},
        "binding_attack": "mitm", "mode": "insecure-override", "insecure": True,
    }
    return p


def gen_params() -> dict:
    valid = []
    invalid = []

    def v(name: str, note: str, p: dict, insecure: bool = False) -> None:
        valid.append({"name": name, "note": note, "verdict": "valid", "insecure_override": insecure, "params": p})

    def bad(name: str, rule: str, mutate) -> None:
        p = base_params()
        mutate(p)
        invalid.append({"name": name, "verdict": "invalid", "violated_rule": rule, "params": p})

    def setf(field, value):
        def f(p):
            p[field] = value
        return f

    def delf(field):
        def f(p):
            del p[field]
        return f

    v("spec_example", "docs/params_format.md §3 with concrete digests.", base_params())
    p = base_params()
    p.update({"t": 1, "ell": 64, "L": 8, "m": 1, "s": 1, "columns_per_shard": 1})
    v("minimal", "t = 1, s = m = columns_per_shard = 1, L = 8: every lower bound attained.", p)
    p = base_params()
    p.update({"m": 2**32, "s": 2**32})
    v("max_m", "m = s = 2^32: upper bound attained.", p)
    v("insecure_override", "Test-only insecure override recorded in `security`: valid, but clients should warn.",
      insecure_params(), insecure=True)
    p = base_params()
    for k in ("security", "created", "encoder_version"):
        del p[k]
    v("no_metadata", "security, created and encoder_version are optional (params_format.md §4).", p)
    p = base_params()
    p["future_field"] = {"x": [1, 2]}
    v("unknown_field", "Unknown fields are ignored (forward compatibility).", p)

    rules = [
        ("format_version_2", "format_version == 1", setf("format_version", 2)),
        ("format_version_string", "format_version == 1", setf("format_version", "1")),
        ("h_prg_unknown", "h_prg is a known value", setf("h_prg", "aes128-ctr-col-v2")),
        ("noise_unknown", "noise is a known value", setf("noise", "bernoulli")),
        ("t_zero", "t >= 1", setf("t", 0)),
        ("t_negative", "t >= 1", setf("t", -5)),
        ("t_string", "t >= 1 (integer)", setf("t", "131072")),
        ("s_zero", "1 <= s", setf("s", 0)),
        ("s_greater_than_m", "s <= m", setf("s", 2097153)),
        ("m_too_large", "m <= 2^32", lambda p: p.update({"m": 2**32 + 1})),
        ("L_zero", "L >= 8", lambda p: p.update({"L": 0, "ell": 0})),
        ("L_4", "L >= 8", lambda p: p.update({"L": 4, "ell": 32})),
        ("L_not_multiple_of_8", "L % 8 == 0", lambda p: p.update({"L": 12, "ell": 96})),
        ("ell_mismatch", "ell == 8 * L", setf("ell", 32769)),
        ("ell_equals_L", "ell == 8 * L", setf("ell", 4096)),
        ("columns_per_shard_zero", "1 <= columns_per_shard", setf("columns_per_shard", 0)),
        ("columns_per_shard_greater_than_m", "columns_per_shard <= m", setf("columns_per_shard", 2097153)),
        ("columns_per_shard_string", "columns_per_shard (integer)", setf("columns_per_shard", "16384")),
        ("h_seed_uppercase", "h_seed is 32 lowercase hex chars", setf("h_seed", "3F9C0A1B2C3D4E5F60718293A4B5C6E1")),
        ("h_seed_short", "h_seed is 32 lowercase hex chars", setf("h_seed", "3f9c0a1b2c3d4e5f60718293a4b5c6")),
        ("h_seed_long", "h_seed is 32 lowercase hex chars", setf("h_seed", "3f9c0a1b2c3d4e5f60718293a4b5c6e100")),
        ("h_seed_non_hex", "h_seed is 32 lowercase hex chars", setf("h_seed", "3f9c0a1b2c3d4e5f60718293a4b5c6eg")),
        ("h_seed_0x_prefix", "h_seed is 32 lowercase hex chars", setf("h_seed", "0x3f9c0a1b2c3d4e5f60718293a4b5c6")),
        ("db_digest_uppercase", "digest = sha256: + 64 lowercase hex", setf("db_digest", "sha256:" + "AB" * 32)),
        ("db_digest_no_prefix", "digest = sha256: + 64 lowercase hex", setf("db_digest", "ab" * 32)),
        ("db_digest_sha512", "digest = sha256: + 64 lowercase hex", setf("db_digest", "sha512:" + "ab" * 32)),
        ("db_digest_63_hex", "digest = sha256: + 64 lowercase hex", setf("db_digest", "sha256:" + "a" * 63)),
        ("r_digest_65_hex", "digest = sha256: + 64 lowercase hex", setf("r_digest", "sha256:" + "a" * 65)),
        ("r_digest_uppercase_prefix", "digest = sha256: + 64 lowercase hex",
         setf("r_digest", "SHA256:" + "ab" * 32)),
    ]
    for name, rule, mut in rules:
        bad(name, rule, mut)
    for field in ["format_version", "t", "ell", "L", "m", "s", "h_prg", "h_seed", "noise", "db_digest", "r_digest",
                  "columns_per_shard"]:
        bad(f"missing_{field}", "protocol field present", delf(field))

    return {
        "format": FORMAT,
        "version": VERSION,
        "file": "params",
        "spec": "docs/params_format.md §1, §4",
        "description": (
            "params.json validation fixtures. Each invalid fixture is the spec example with exactly one rule "
            "violated. 'params' is the parsed object; serialize it with any JSON encoder if a file is needed. "
            "insecure_override marks fixtures whose security.mode is 'insecure-override' (valid, but clients "
            "should surface a warning). Contents of 'security' are not validated otherwise."
        ),
        "valid": valid,
        "invalid": invalid,
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

GENERATORS = {
    "h_prg.json": gen_h_prg,
    "bitpack.json": gen_bitpack,
    "qc.json": gen_qc,
    "column_location.json": gen_column_location,
    "db_format.json": gen_db_format,
    "params.json": gen_params,
}


def render(obj: dict) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=True) + "\n"


def generate_all() -> dict[str, str]:
    return {name: render(fn()) for name, fn in GENERATORS.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="verify vectors/ is up to date instead of writing")
    args = ap.parse_args(argv)
    files = generate_all()
    if args.check:
        stale = [n for n, txt in files.items() if not (OUT_DIR / n).exists() or (OUT_DIR / n).read_text() != txt]
        for n in stale:
            print(f"stale: vectors/{n}", file=sys.stderr)
        return 1 if stale else 0
    OUT_DIR.mkdir(exist_ok=True)
    for n, txt in files.items():
        (OUT_DIR / n).write_text(txt)
        print(f"wrote vectors/{n} ({len(txt.encode())} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
