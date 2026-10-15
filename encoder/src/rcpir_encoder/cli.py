"""`rcpir-encode` command line (docs/encoder.md §1)."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__, lpn
from .pipeline import EncodeError, EncodeOptions, encode, log


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rcpir-encode",
        description="Encode a JSONL database for the sqrt(n) RC-PIR (X.bin, shards of R = XH, params.json).")
    p.add_argument("db", type=Path, help='input database: JSONL, one block per line in a base64 "data" field')
    p.add_argument("--out", type=Path, required=True, help="output directory (must be empty unless --resume)")
    p.add_argument("--lambda", dest="lam", type=int, default=lpn.DEFAULT_LAMBDA,
                   help="target security level in bits (default 128)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--c", type=float, default=lpn.DEFAULT_C,
                      help="Mode A: storage expansion factor c = m/t (default 16)")
    mode.add_argument("--target-comm", type=int, metavar="BITS",
                      help="Mode B: target total communication in bits (asks for confirmation)")
    mode.add_argument("--insecure-m", type=int, metavar="M",
                      help="TEST ONLY: use m = M without any security check (needs --insecure-s)")
    p.add_argument("--insecure-s", type=int, metavar="S", help="TEST ONLY: use s = S (needs --insecure-m)")
    p.add_argument("--table", action="store_true", help="also print Mode A for c in {2, 4, 16, 256, 4096}")
    p.add_argument("--dry-run", action="store_true", help="print the report and exit without writing anything")
    p.add_argument("--yes", action="store_true", help="skip the Mode B confirmation prompt")
    p.add_argument("--seed", type=bytes.fromhex, metavar="HEX", help="fixed h_seed (32 hex characters)")
    p.add_argument("--device", choices=("cpu", "cuda"), default="cpu",
                   help="matmul backend (default cpu; cuda needs CuPy and an NVIDIA GPU, sm_80 or newer)")
    p.add_argument("--shard-mib", type=int, default=64, metavar="MIB",
                   help="upper bound on the size of a shard of R in MiB (default 64); shards hold whole columns")
    p.add_argument("--no-verify", action="store_true", help="skip the verification step")
    p.add_argument("--resume", action="store_true", help="continue an interrupted run in --out")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (args.insecure_m is None) != (args.insecure_s is None):
        parser.error("--insecure-m and --insecure-s must be given together")
    if args.shard_mib < 1:
        parser.error("--shard-mib must be >= 1")
    if args.seed is not None and len(args.seed) != 16:
        parser.error("--seed must be 32 hex characters (16 bytes)")
    opts = EncodeOptions(
        db=args.db, out=args.out, lambda_value=args.lam, c=args.c, target_comm=args.target_comm,
        insecure_m=args.insecure_m, insecure_s=args.insecure_s, table=args.table, dry_run=args.dry_run,
        yes=args.yes, seed=args.seed, device=args.device, verify=not args.no_verify, resume=args.resume,
        shard_bytes=args.shard_mib << 20)
    try:
        encode(opts)
    except (EncodeError, lpn.Infeasible, ValueError, OSError) as e:   # DBFormatError, VerificationError are ValueErrors
        log(f"error: {e}")
        return 1
    return 0
