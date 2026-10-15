"""CUDA backend of `gf2_matmul` (docs/encoder.md §3): 1-bit tensor cores (mma b1 AND.POPC) via CuPy.

Same signature and layouts as `gf2.matmul_cpu`. Tiled 1-bit kernel (128x256 block tiles, double-buffered
cp.async) with an MSB-first epilogue that writes the column bytes as stored.

X is transposed once into GPU memory (rows packed along t, the layout of H) and kept there, so the
whole of X must fit in VRAM. Each call uploads one panel of H, runs the kernel, downloads the panel of R.
"""

import cupy as cp
import numpy as np

KERNEL = r"""
// R = X^T-row-packed (Xt) times H panel over F_2.
// Xt : uint32 [rows, KW]  row b = row b of X (bits over t), packed like H (MSB-first bytes)
// Ht : uint32 [cols, KW]  row c = column c of the H panel
// R16: uint16 [cols, rows/16]  column-major R panel, MSB-first bytes (= the stored column bytes)
// 8 warps (2 x 4), block tile 128 x 256, warp tile 64 x 64, K stage 512 bits, double-buffered cp.async.
#define BM 128
#define BN 256
#define SW 16
__device__ __forceinline__ int swz(int r, int w) { return r * SW + ((((w >> 2) ^ ((r >> 1) & 3))) << 2) + (w & 3); }
__device__ __forceinline__ void cp16(void *dst, const void *src) {
  unsigned d = (unsigned)__cvta_generic_to_shared(dst);
  asm volatile("cp.async.cg.shared.global [%0], [%1], 16;\n" ::"r"(d), "l"(src));
}
extern "C" __global__ void __launch_bounds__(256) gemm_b1(const unsigned *__restrict__ Xt, const unsigned *__restrict__ Ht,
                                                          unsigned short *__restrict__ R16, int KW, int rows) {
  __shared__ __align__(16) unsigned sA[2][BM * SW];
  __shared__ __align__(16) unsigned sB[2][BN * SW];
  int tid = threadIdx.x, warp = tid >> 5, lane = tid & 31, g = lane >> 2, t = lane & 3;
  int wm = warp >> 2, wn = warp & 3, row0 = blockIdx.y * BM, col0 = blockIdx.x * BN;
  auto load = [&](int buf, int kw) {
    for (int idx = tid; idx < BM * 4; idx += 256) {
      int r = idx >> 2, c = idx & 3;
      cp16(&sA[buf][swz(r, c * 4)], Xt + (size_t)(row0 + r) * KW + kw + c * 4);
    }
    for (int idx = tid; idx < BN * 4; idx += 256) {
      int r = idx >> 2, c = idx & 3;
      cp16(&sB[buf][swz(r, c * 4)], Ht + (size_t)(col0 + r) * KW + kw + c * 4);
    }
    asm volatile("cp.async.commit_group;\n");
  };
  int acc[4][8][4];
#pragma unroll
  for (int i = 0; i < 4; i++)
#pragma unroll
    for (int j = 0; j < 8; j++) acc[i][j][0] = acc[i][j][1] = acc[i][j][2] = acc[i][j][3] = 0;
  const int stages = KW / SW;
  load(0, 0);
  for (int s = 0; s < stages; s++) {
    int buf = s & 1;
    if (s + 1 < stages) { load(buf ^ 1, (s + 1) * SW); asm volatile("cp.async.wait_group 1;\n"); }
    else asm volatile("cp.async.wait_group 0;\n");
    __syncthreads();
    const unsigned *A = sA[buf], *B = sB[buf];
#pragma unroll
    for (int ks = 0; ks < SW; ks += 8) {
      unsigned a[4][4], b[8][2];
#pragma unroll
      for (int i = 0; i < 4; i++) {
        int r = wm * 64 + i * 16 + g;
        a[i][0] = A[swz(r, ks + t)];     a[i][1] = A[swz(r + 8, ks + t)];
        a[i][2] = A[swz(r, ks + 4 + t)]; a[i][3] = A[swz(r + 8, ks + 4 + t)];
      }
#pragma unroll
      for (int j = 0; j < 8; j++) {
        int c = wn * 64 + j * 8 + g;
        b[j][0] = B[swz(c, ks + t)]; b[j][1] = B[swz(c, ks + 4 + t)];
      }
#pragma unroll
      for (int i = 0; i < 4; i++)
#pragma unroll
        for (int j = 0; j < 8; j++)
          asm volatile("mma.sync.aligned.m16n8k256.row.col.s32.b1.b1.s32.and.popc "
                       "{%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3};\n"
                       : "+r"(acc[i][j][0]), "+r"(acc[i][j][1]), "+r"(acc[i][j][2]), "+r"(acc[i][j][3])
                       : "r"(a[i][0]), "r"(a[i][1]), "r"(a[i][2]), "r"(a[i][3]), "r"(b[j][0]), "r"(b[j][1]));
    }
    __syncthreads();
  }
  // Epilogue: parity, then 16 rows of one column into a uint16 whose two bytes are MSB-first.
  // C fragment: c0:(g, 2t) c1:(g, 2t+1) c2:(g+8, 2t) c3:(g+8, 2t+1); ballot bit = 4g + t.
#pragma unroll
  for (int i = 0; i < 4; i++)
#pragma unroll
    for (int j = 0; j < 8; j++) {
      unsigned bl[4];
#pragma unroll
      for (int v = 0; v < 4; v++) bl[v] = __ballot_sync(0xffffffffu, acc[i][j][v] & 1);
      if (lane < 8) {
        int tt = lane >> 1, e = lane & 1;
        unsigned lo = bl[e], hi = bl[2 + e], word = 0;
#pragma unroll
        for (int gg = 0; gg < 8; gg++) {
          word |= ((lo >> (4 * gg + tt)) & 1u) << (7 - gg);
          word |= ((hi >> (4 * gg + tt)) & 1u) << (15 - gg);
        }
        int col = col0 + wn * 64 + j * 8 + 2 * tt + e, row = row0 + wm * 64 + i * 16;
        R16[(size_t)col * (rows >> 4) + (row >> 4)] = (unsigned short)word;
      }
    }
}
"""

BM, BN, BK = 128, 256, 512                 # kernel tile: rows of R, columns of R, bits of t per stage
_kernel = None
_x_cache: tuple = (None, None)             # (X host array, Xt on the GPU)


def _ceil(a: int, b: int) -> int:
    return -(-a // b) * b


def panel_cols(t: int, L: int) -> int:
    """Panel width: H panel and R panel about 512 MiB each on the GPU, a multiple of the tile width."""
    budget = 1 << 29
    return max(BN, min(budget // (_ceil(t, BK) // 8), budget // (_ceil(8 * L, BM) // 8)) // BN * BN)


def _transpose_x(X: np.ndarray, t: int) -> cp.ndarray:
    """(t, L) packed columns of X -> (rows, tp/8) packed rows of X, zero-padded, on the GPU."""
    ell = 8 * X.shape[1]
    need = _ceil(ell, BM) * _ceil(t, BK) // 8
    if need > cp.cuda.runtime.memGetInfo()[0] // 2:
        raise MemoryError(f"X ({need / 2**30:.1f} GiB) does not fit in GPU memory")
    Xt = cp.zeros((_ceil(ell, BM), _ceil(t, BK) // 8), dtype=cp.uint8)
    step = max(8, (1 << 28) // ell // 8 * 8)            # rows of X.bin per chunk (~256 MiB unpacked)
    for r0 in range(0, t, step):
        rows = min(step, t - r0)
        bits = cp.zeros((_ceil(rows, 8), ell), dtype=cp.uint8)            # CuPy's (un)packbits have no axis
        bits[:rows] = cp.unpackbits(cp.asarray(X[r0:r0 + rows]).ravel()).reshape(rows, ell)
        packed = cp.packbits(cp.ascontiguousarray(bits.T).ravel()).reshape(ell, -1)
        Xt[:ell, r0 // 8:r0 // 8 + packed.shape[1]] = packed
    return Xt


def matmul_cuda(X: np.ndarray, H: np.ndarray, t: int) -> np.ndarray:
    global _kernel, _x_cache
    if _kernel is None:
        _kernel = cp.RawKernel(KERNEL, "gemm_b1", options=("-std=c++17",))
    if _x_cache[0] is not X:
        _x_cache = (None, None)                         # free the previous Xt first
        _x_cache = (X, _transpose_x(X, t))
    Xt = _x_cache[1]
    rows, tp8 = Xt.shape
    mp, L = H.shape[0], X.shape[1]
    Hd = cp.zeros((_ceil(mp, BN), tp8), dtype=cp.uint8)
    Hd[:mp, :H.shape[1]] = cp.asarray(H)
    R16 = cp.empty((Hd.shape[0], rows // 16), dtype=cp.uint16)
    _kernel((Hd.shape[0] // BN, rows // BM), (256,),
            (Xt.view(cp.uint32), Hd.view(cp.uint32), R16, np.int32(tp8 // 4), np.int32(rows)))
    return cp.asnumpy(R16.view(cp.uint8)[:mp, :L])
