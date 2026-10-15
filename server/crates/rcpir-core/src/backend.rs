//! Answer computation `X q` over `F_2` (`docs/compute_server.md` §1).
//!
//! `X` is column-major (exactly `X.bin`), so `X q` is the XOR of the columns `j` with `q_j = 1`
//! (bit `j` of `q`, MSB-first).

use std::sync::atomic::{AtomicUsize, Ordering};

use anyhow::{Result, ensure};

/// One pass over `X` answering a batch of queries.
///
/// Implementations keep no state between calls that a panic could leave inconsistent: the server
/// catches a panic in `answer_batch`, logs it and keeps using the backend.
pub trait Backend: Send + Sync {
    /// One pass over X answering all queries; `queries[i]` is `ceil(t/8)` bytes, `out[i]` is `L`
    /// bytes and is overwritten.
    fn answer_batch(&self, queries: &[&[u8]], out: &mut [&mut [u8]]);
}

/// Accumulator bytes per worker (`k` queries x strip width): small enough to stay in L2.
const ACC_BUDGET: usize = 256 << 10;
/// Target bytes of `X` (per strip) in one scheduling block.
const BLOCK_BYTES: usize = 1 << 20;
/// Minimum number of scheduling blocks per worker (load balance between P- and E-cores).
const BLOCKS_PER_WORKER: usize = 8;
/// Software prefetch runs this many bytes ahead of the strip being XORed.
const PREFETCH_AHEAD: usize = 4096;
/// The prefetched strip is at most this many entries ahead in the list of selected columns. Binds
/// only for strips narrower than `PREFETCH_AHEAD / MAX_PREFETCH_COLS` = 256 bytes.
const MAX_PREFETCH_COLS: usize = 16;

/// Query bits are processed as `u64` words: one word covers this many consecutive columns.
const WORD_BITS: usize = u64::BITS as usize;
/// Bytes of the packed query in one word.
const WORD_BYTES: usize = WORD_BITS / 8;
/// Most significant bit of a word. Words are big-endian (MSB-first, like the packed query), so
/// column `WORD_BITS * w + r` is the bit `TOP_BIT >> r` of word `w`.
const TOP_BIT: u64 = 1 << (WORD_BITS - 1);
/// Cache-line size in bytes (x86-64). Strips are whole cache lines, and the kernels prefetch one
/// cache line per `CACHE_LINE` bytes XORed.
const CACHE_LINE: usize = 64;
/// Bytes in one AVX2 register (`__m256i`).
const AVX2_BYTES: usize = 32;
/// Bytes XORed per step of the kernels: 4 AVX2 registers = 2 cache lines.
const XOR_STEP: usize = 4 * AVX2_BYTES;
const _: () = assert!(XOR_STEP == 2 * CACHE_LINE); // the kernels prefetch two lines per step

/// CPU backend.
///
/// - **Strips:** columns are processed in strips (byte ranges) of width `W = min(L, ACC_BUDGET / k)`:
///   whole columns unless a large batch needs narrower strips to keep its accumulators in L2. Each
///   strip is one column-split pass, so `X` is still read once. (Cutting long columns into fixed
///   4-8 KiB strips measured 13-33% slower: long contiguous runs matter.)
/// - **Column split:** the columns are cut into blocks; each worker claims blocks dynamically and
///   XORs the selected columns' strips into its own accumulators, which are XOR-reduced at the end.
/// - **Index lists:** per block, the selected columns (OR over the batch) are listed first, so
///   unselected columns cost no branch misprediction, and the strip `PREFETCH_AHEAD` bytes ahead
///   is prefetched.
/// - **Batches:** each selected strip is loaded once and XORed into every query that selects it.
/// - **AVX2** (runtime-detected) for the XOR, with a portable fallback.
pub struct CpuBackend {
    x: Vec<u8>,
    t: usize,
    l: usize,
    pool: rayon::ThreadPool,
    avx2: bool,
}

impl CpuBackend {
    /// `x` is the column-major database (`t` columns of `l` bytes). With `pin_cores`, worker `i`
    /// is pinned to core `pin_cores[i]`.
    pub fn new(x: Vec<u8>, t: usize, l: usize, threads: usize, pin_cores: Option<Vec<usize>>) -> Result<Self> {
        ensure!(x.len() == t * l, "X has {} bytes, expected t * L = {}", x.len(), t * l);
        ensure!(threads >= 1, "need at least one thread");
        let mut pool = rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .thread_name(|i| format!("rcpir-worker-{i}"));
        if let Some(cores) = pin_cores {
            ensure!(
                cores.len() >= threads,
                "--pin-cores lists {} cores for {threads} threads",
                cores.len()
            );
            pool = pool.start_handler(move |i| {
                if !core_affinity::set_for_current(core_affinity::CoreId { id: cores[i] }) {
                    eprintln!("warning: could not pin worker {i} to core {}", cores[i]);
                }
            });
        }
        Ok(CpuBackend {
            x,
            t,
            l,
            pool: pool.build()?,
            avx2: avx2_available(),
        })
    }

    pub fn threads(&self) -> usize {
        self.pool.current_num_threads()
    }

    /// One worker: claims blocks of `cols` columns from `next` and XORs bytes
    /// `[start, start + width)` of every selected column into `acc` (`k` strips of `width`).
    /// Returns `None` if it claimed no block.
    fn worker(
        &self,
        queries: &[&[u8]],
        start: usize,
        width: usize,
        cols: usize,
        next: &AtomicUsize,
    ) -> Option<Vec<u8>> {
        let k = queries.len();
        let words = cols / WORD_BITS; // cols is a multiple of WORD_BITS
        let mut acc: Option<Vec<u8>> = None;
        let mut qwords = vec![0u64; k * words]; // qwords[i * words + w]
        let mut selected: Vec<usize> = Vec::with_capacity(cols);
        let mut targets: Vec<*mut u8> = Vec::with_capacity(k);
        let dist = PREFETCH_AHEAD.div_ceil(width).clamp(1, MAX_PREFETCH_COLS);
        loop {
            let j0 = next.fetch_add(1, Ordering::Relaxed) * cols;
            if j0 >= self.t {
                return acc;
            }
            let acc = acc.get_or_insert_with(|| vec![0u8; k * width]);
            let j1 = (j0 + cols).min(self.t);
            let used_words = (j1 - j0).div_ceil(WORD_BITS);
            for (i, q) in queries.iter().enumerate() {
                for w in 0..used_words {
                    qwords[i * words + w] = query_word(q, j0 / WORD_BITS + w, self.t);
                }
            }
            selected.clear();
            for w in 0..used_words {
                let mut any = (0..k).fold(0, |a, i| a | qwords[i * words + w]);
                while any != 0 {
                    // Highest set bit = lowest selected column of the word.
                    let r = any.leading_zeros() as usize;
                    selected.push(j0 + WORD_BITS * w + r);
                    any &= !(TOP_BIT >> r);
                }
            }
            let x = self.x.as_ptr();
            for (a, &j) in selected.iter().enumerate() {
                // SAFETY: j < t and start + width <= l, so the strip lies inside X (t * l bytes).
                let src = unsafe { x.add(j * self.l + start) };
                // Strip to prefetch while XORing this one (null: none).
                let ahead = match selected.get(a + dist) {
                    Some(&jn) => unsafe { x.add(jn * self.l + start) },
                    None => std::ptr::null(),
                };
                targets.clear();
                let (w, r) = ((j - j0) / WORD_BITS, (j - j0) % WORD_BITS);
                for i in 0..k {
                    if qwords[i * words + w] & (TOP_BIT >> r) != 0 {
                        // SAFETY: strip i of acc, inside the k * width buffer.
                        targets.push(unsafe { acc.as_mut_ptr().add(i * width) });
                    }
                }
                // SAFETY: src is valid for width bytes; targets are disjoint strips of acc.
                unsafe { xor_into(&targets, src, ahead, width, self.avx2) };
            }
        }
    }
}

impl Backend for CpuBackend {
    fn answer_batch(&self, queries: &[&[u8]], out: &mut [&mut [u8]]) {
        assert_eq!(queries.len(), out.len(), "one output per query");
        assert!(
            queries.iter().all(|q| q.len() == self.t.div_ceil(8)),
            "query must be ceil(t/8) bytes"
        );
        assert!(out.iter().all(|o| o.len() == self.l), "output must be L bytes");
        let k = queries.len();
        if k == 0 {
            return;
        }
        // Strip width: whole columns unless the batch's accumulators exceed the budget (then
        // whole cache lines, at least one).
        let strip = self.l.min((ACC_BUDGET / k / CACHE_LINE * CACHE_LINE).max(CACHE_LINE));
        for start in (0..self.l).step_by(strip) {
            let width = strip.min(self.l - start);
            // Columns per scheduling block: a multiple of WORD_BITS (whole query words), about
            // BLOCK_BYTES of X, and at least BLOCKS_PER_WORKER blocks per worker.
            let by_bytes = BLOCK_BYTES / width;
            let by_balance = self.t / (BLOCKS_PER_WORKER * self.threads());
            let cols = (by_bytes.min(by_balance) / WORD_BITS * WORD_BITS).max(WORD_BITS);
            let next = AtomicUsize::new(0);
            let partials: Vec<Vec<u8>> = self
                .pool
                .broadcast(|_| self.worker(queries, start, width, cols, &next))
                .into_iter()
                .flatten()
                .collect();
            // XOR-reduce the workers' accumulators into the outputs.
            for (i, o) in out.iter_mut().enumerate() {
                let o = &mut o[start..start + width];
                o.fill(0);
                for p in &partials {
                    for (a, b) in o.iter_mut().zip(&p[i * width..(i + 1) * width]) {
                        *a ^= b;
                    }
                }
            }
        }
    }
}

/// Query bits of columns `WORD_BITS * w ..` (`WORD_BITS` of them) as a big-endian word: the
/// column `WORD_BITS * w + r` is the bit `TOP_BIT >> r`. Bits of columns `>= t` are cleared.
#[inline]
fn query_word(q: &[u8], w: usize, t: usize) -> u64 {
    let mut b = [0u8; WORD_BYTES];
    let lo = (WORD_BYTES * w).min(q.len());
    let hi = (WORD_BYTES * (w + 1)).min(q.len());
    b[..hi - lo].copy_from_slice(&q[lo..hi]);
    let word = u64::from_be_bytes(b);
    let valid = t.saturating_sub(WORD_BITS * w).min(WORD_BITS); // columns of this word below t
    if valid == WORD_BITS {
        word
    } else {
        word & !(u64::MAX >> valid)
    }
}

fn avx2_available() -> bool {
    #[cfg(target_arch = "x86_64")]
    {
        std::arch::is_x86_feature_detected!("avx2")
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        false
    }
}

/// `*dst ^= src` (`width` bytes) for every `dst` in `targets`; `src` is read once per chunk.
/// If `ahead` is not null, the same `width` bytes at `ahead` are prefetched, one cache line per
/// `CACHE_LINE` bytes XORed (spreading the prefetches keeps the line-fill buffers from saturating).
///
/// # Safety
/// `src` and every target are valid for `width` bytes; targets do not overlap `src` or each other.
#[inline]
unsafe fn xor_into(targets: &[*mut u8], src: *const u8, ahead: *const u8, width: usize, avx2: bool) {
    #[cfg(target_arch = "x86_64")]
    if avx2 {
        return unsafe { xor_into_avx2(targets, src, ahead, width) };
    }
    let _ = avx2;
    unsafe { xor_into_portable(targets, src, ahead, width, 0) }
}

/// Portable version from byte `from` on, in chunks of `XOR_STEP` bytes (plain slice loops, which
/// the compiler vectorizes for the baseline target, e.g. SSE2), with the same interleaved prefetch.
#[inline]
unsafe fn xor_into_portable(targets: &[*mut u8], src: *const u8, ahead: *const u8, width: usize, from: usize) {
    let mut c = from;
    while c < width {
        let e = (c + XOR_STEP).min(width);
        if !ahead.is_null() {
            // The chunk spans up to two cache lines (XOR_STEP = 2 * CACHE_LINE).
            prefetch(ahead.wrapping_add(c));
            if c + CACHE_LINE < e {
                prefetch(ahead.wrapping_add(c + CACHE_LINE));
            }
        }
        // SAFETY: the caller guarantees src and targets are valid for width bytes, disjoint.
        let s = unsafe { std::slice::from_raw_parts(src.add(c), e - c) };
        for &d in targets {
            let d = unsafe { std::slice::from_raw_parts_mut(d.add(c), e - c) };
            for (a, b) in d.iter_mut().zip(s) {
                *a ^= *b;
            }
        }
        c = e;
    }
}

#[inline]
fn prefetch(p: *const u8) {
    #[cfg(target_arch = "x86_64")]
    // SAFETY: prefetch never faults.
    unsafe {
        std::arch::x86_64::_mm_prefetch::<{ std::arch::x86_64::_MM_HINT_T0 }>(p.cast())
    };
    #[cfg(not(target_arch = "x86_64"))]
    let _ = p;
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2")]
unsafe fn xor_into_avx2(targets: &[*mut u8], src: *const u8, ahead: *const u8, width: usize) {
    use std::arch::x86_64::*;
    unsafe {
        let mut i = 0;
        // XOR_STEP bytes (two cache lines) per step: 4 register loads of src, then 4
        // read-modify-writes per target.
        while i + XOR_STEP <= width {
            if !ahead.is_null() {
                _mm_prefetch::<_MM_HINT_T0>(ahead.wrapping_add(i).cast());
                _mm_prefetch::<_MM_HINT_T0>(ahead.wrapping_add(i + CACHE_LINE).cast());
            }
            let s0 = _mm256_loadu_si256(src.add(i) as *const __m256i);
            let s1 = _mm256_loadu_si256(src.add(i + AVX2_BYTES) as *const __m256i);
            let s2 = _mm256_loadu_si256(src.add(i + 2 * AVX2_BYTES) as *const __m256i);
            let s3 = _mm256_loadu_si256(src.add(i + 3 * AVX2_BYTES) as *const __m256i);
            for &d in targets {
                // d.add(n) below advances by n registers (n * AVX2_BYTES bytes).
                let d = d.add(i) as *mut __m256i;
                _mm256_storeu_si256(d, _mm256_xor_si256(_mm256_loadu_si256(d), s0));
                _mm256_storeu_si256(d.add(1), _mm256_xor_si256(_mm256_loadu_si256(d.add(1)), s1));
                _mm256_storeu_si256(d.add(2), _mm256_xor_si256(_mm256_loadu_si256(d.add(2)), s2));
                _mm256_storeu_si256(d.add(3), _mm256_xor_si256(_mm256_loadu_si256(d.add(3)), s3));
            }
            i += XOR_STEP;
        }
        let prefetched = i; // ahead[..prefetched] was prefetched by the loop above
        // Tail: one register at a time, then (fewer than AVX2_BYTES bytes) the portable loop.
        while i + AVX2_BYTES <= width {
            let s = _mm256_loadu_si256(src.add(i) as *const __m256i);
            for &d in targets {
                let d = d.add(i) as *mut __m256i;
                _mm256_storeu_si256(d, _mm256_xor_si256(_mm256_loadu_si256(d), s));
            }
            i += AVX2_BYTES;
        }
        if !ahead.is_null() {
            let mut p = prefetched;
            while p < width {
                _mm_prefetch::<_MM_HINT_T0>(ahead.wrapping_add(p).cast());
                p += CACHE_LINE;
            }
        }
        xor_into_portable(targets, src, std::ptr::null(), width, i);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fixture::{naive_answer, random_query, random_x, unit_query};
    use rand::SeedableRng;
    use rand::rngs::StdRng;

    fn backend(x: &[u8], t: usize, l: usize, threads: usize) -> CpuBackend {
        CpuBackend::new(x.to_vec(), t, l, threads, None).unwrap()
    }

    fn answer(b: &CpuBackend, queries: &[Vec<u8>], l: usize) -> Vec<Vec<u8>> {
        let qrefs: Vec<&[u8]> = queries.iter().map(Vec::as_slice).collect();
        let mut outs = vec![vec![0xAB; l]; queries.len()]; // garbage: must be overwritten
        let mut orefs: Vec<&mut [u8]> = outs.iter_mut().map(Vec::as_mut_slice).collect();
        b.answer_batch(&qrefs, &mut orefs);
        outs
    }

    /// Backend vs the bit-level reference: shapes incl. t mod 8 != 0, t not a multiple of 64,
    /// L not a multiple of 32, several thread counts, batch sizes 1..=5, unit and zero queries,
    /// AVX2 and portable kernels.
    #[test]
    fn matches_naive_reference() {
        let mut rng = StdRng::seed_from_u64(42);
        for (t, l) in [(1, 8), (7, 8), (9, 72), (13, 200), (100, 136), (257, 64), (1000, 40)] {
            let x = random_x(t, l, &mut rng);
            for threads in [1, 2, 3, 5] {
                for portable in [false, true] {
                    let mut b = backend(&x, t, l, threads);
                    if portable {
                        b.avx2 = false;
                    }
                    for k in 1..=5 {
                        let queries: Vec<Vec<u8>> = (0..k).map(|_| random_query(t, &mut rng)).collect();
                        for (q, o) in queries.iter().zip(answer(&b, &queries, l)) {
                            assert_eq!(o, naive_answer(&x, t, l, q), "t={t} l={l} threads={threads} k={k}");
                        }
                    }
                    let outs = answer(&b, &[unit_query(t, t - 1), vec![0; t.div_ceil(8)]], l);
                    assert_eq!(outs[0], &x[(t - 1) * l..]);
                    assert_eq!(outs[1], vec![0; l]);
                }
            }
        }
    }

    /// A long column as one strip, and `[0, L)` cut into strips by ACC_BUDGET for large batches
    /// (incl. a partial last strip).
    #[test]
    fn strips_match_reference() {
        let mut rng = StdRng::seed_from_u64(5);
        for (t, l, k) in [(70, 16456, 1), (70, 16456, 20), (300, 1096, 2 * ACC_BUDGET / 1096)] {
            let x = random_x(t, l, &mut rng);
            let b = backend(&x, t, l, 3);
            let queries: Vec<Vec<u8>> = (0..k).map(|_| random_query(t, &mut rng)).collect();
            let outs = answer(&b, &queries, l);
            for i in [0, k / 2, k - 1] {
                assert_eq!(
                    outs[i],
                    naive_answer(&x, t, l, &queries[i]),
                    "t={t} l={l} query {i} of {k}"
                );
            }
        }
    }

    #[test]
    fn query_word_masks_beyond_t() {
        let q = [0xFF; 9]; // t = 70 bits would need 9 bytes; trailing bits set on purpose
        assert_eq!(query_word(&q, 0, 70), u64::MAX);
        assert_eq!(query_word(&q, 1, 70), 0xFC00_0000_0000_0000); // 6 valid bits
        assert_eq!(query_word(&q, 2, 70), 0);
    }

    #[test]
    fn pinned_workers() {
        let (t, l) = (20, 128);
        let mut rng = StdRng::seed_from_u64(9);
        let x = random_x(t, l, &mut rng);
        let b = CpuBackend::new(x.clone(), t, l, 2, Some(vec![0, 1])).unwrap();
        let q = random_query(t, &mut rng);
        assert_eq!(answer(&b, std::slice::from_ref(&q), l)[0], naive_answer(&x, t, l, &q));
    }

    #[test]
    fn config_errors() {
        assert!(CpuBackend::new(vec![0; 24], 4, 8, 1, None).is_err()); // wrong size
        assert!(CpuBackend::new(vec![0; 24], 3, 8, 0, None).is_err()); // no threads
        assert!(CpuBackend::new(vec![0; 24], 3, 8, 2, Some(vec![0])).is_err()); // too few cores
    }
}
