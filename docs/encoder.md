# Encoder Pipeline

Status: agreed design. Stack: Python, CuPy 1-bit tensor-core kernel on GPU (`docs/stack.md`).
Inputs/outputs: `docs/db_format.md`, `docs/params_format.md`, `docs/h_prg.md`, `docs/protocol.md`.

## 1. CLI

```
rcpir-encode DB.jsonl --out DIR [--lambda 128] (--c C | --target-comm BITS | --insecure-m M --insecure-s S)
             [--table] [--dry-run] [--yes] [--seed HEX] [--device cpu|cuda] [--shard-mib 64] [--no-verify] [--resume]
```

| Flag | Meaning |
|---|---|
| `--lambda` | Target security level $\lambda$ (default 128). |
| `--c` / `--target-comm` | Mode A (storage factor; default `--c 16`) or Mode B (target communication in bits), `docs/lpn_parameters.md` §5–6. |
| `--insecure-m M --insecure-s S` | **Tests only.** Use $(m,s)$ without any security check; recorded in `params.json` (`params_format.md` §2). Needed for tiny DBs, where Mode A is infeasible. |
| `--table` | Also print Mode A for $c\in\{2,4,16,256,4096\}$ (`lpn_parameters.md` §7). |
| `--dry-run` | Print the report and the time estimate, write nothing. |
| `--yes` | Skip the confirmation prompt (Mode B always asks otherwise; no answer counts as no). |
| `--seed HEX` | Fixed `h_seed` (32 hex chars) for reproducible tests. Default: OS CSPRNG. |
| `--device` | `cpu` (default for now) or `cuda` (not implemented until branch 2B; then the default if available). |
| `--shard-mib` | Upper bound $B$ on the size of a shard of $R$ in MiB (default 64, under GitHub's 100 MiB file limit). Shards hold whole columns: `columns_per_shard` $=\min(\lfloor B/L\rfloor, m)$, so each is at most $B$. Error if $B<L$. |
| `--no-verify` | Skip step 6. |
| `--resume` | Continue an interrupted run in `DIR` (§4). Without it, a non-empty `DIR` is an error. |

Exit codes: `0` success, `1` input/parameter/verification error, `2` usage error.

## 2. Steps

1. **Scan** `DB.jsonl` (`db_format.md` §4): validate, compute $t$, $L$, $\ell$, padding overhead.
2. **Select parameters** (Mode A or B): $m$, $s$, attack costs. Print the report (`lpn_parameters.md` §7,
   `db_format.md` §5) and an **estimated preprocessing time**, measured by timing the selected backend on a
   small random problem at start-up (rough; about 2× pessimistic on the CPU backend).
   Mode B waits for confirmation unless `--yes`.
3. **Seed:** 16 bytes from the OS CSPRNG (or `--seed`).
4. **Pack** `X.bin` (column-major, $t$ columns of $L$ bytes, MSB-first) and compute `db_digest` (SHA-256).
5. **Compute $R=XH$** (tiled, §3), writing each column at its offset in its shard (`protocol.md` §2), then
   computing `r_digest` over the shards in order.
6. **Verify** (default on): spot check of $k=1000$ distinct random columns of $R$ (all if $m\le k$): each is
   recomputed on the CPU (`h_column`, float32 BLAS) and compared with its file. Catches systematic errors
   (kernel, layout, padding, writes, resume): if a fraction $f$ of the columns is wrong, it passes with
   probability $\le(1-f)^k$. Rare isolated errors (e.g. a bit flip on a non-ECC GPU) are not caught.
   Cost: $k\,t\ell$ bit operations, ~2 s for 64 MiB and ~20 s for 1 GiB (measured rate of `matmul_cpu`). It does not check `X.bin` against the input (covered by the `db_format` vectors and by
   `e2e/retrieve_all.mjs`, which can also be run against a deployment).
7. **Write** `params.json` last (its presence marks a complete run), after validating it with
   `rcpir_common.params.validate` (the rules the client and server apply).

## 3. GPU computation of $R=XH$ (`--device cuda`, `gf2_cuda.py`)

- **Kernel:** `mma.sync m16n8k256 b1 AND.POPC` (sm_80+), block tile
  128 rows × 256 columns of $R$, 512 bits of $t$ per stage, double-buffered `cp.async`. The parity of the
  popcount sum is the $\mathbb{F}_2$ result; the epilogue writes MSB-first column bytes (the file format).
- **$X$:** transposed once on the GPU into rows packed along $t$ (the layout of the columns of $H$) and kept
  in VRAM for the whole run, so all of $X$ (≈ $n/8$ bytes) must fit in GPU memory.
- **Panels:** the pipeline loop of §2 step 5 is unchanged. Per panel: `h_panel` on the CPU (per-column
  AES-CTR, ~5 GB/s for large $t$), upload, kernel, download of the $m_p$ columns, file writes. Panel width:
  $H$ and $R$ panels about 512 MiB each on the GPU, a multiple of 256.
- **Padding:** rows to a multiple of 128, columns to 256, $t$ to 512 bits (zeros, cut from the output).
- **Not done:** overlapping the PRG, the GPU and the file writes; streaming $X$ when it exceeds VRAM.

## 4. Resume

Column panels are written in index order. With `--resume`, the encoder re-reads the parameters and seed
from the progress file `DIR/.rcpir-progress.json` (command-line mode flags and `--seed` are ignored),
checks that the input file is unchanged (SHA-256), repacks `X.bin`, and continues with the first
incomplete panel. Columns are always written at their final offsets, so a partly written panel is simply
overwritten. `r_digest` is computed at the end by reading the shards in order.
`params.json` is written only at the very end; resuming a complete run is a no-op.

## 5. Output

```
DIR/
  params.json                     # also copied to site/.well-known/rc-pir.json
  X.bin                           # for the compute server
  site/                           # upload as-is to the retrieval host
    .well-known/rc-pir.json
    rc-pir/r/xxxxxxxx             # shards of R: columns_per_shard columns of L bytes each
```

Note: `X.bin` and the shards are large; on WSL2 put `DIR` on the Linux filesystem, not `/mnt/c` (NTFS).
