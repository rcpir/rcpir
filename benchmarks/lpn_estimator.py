"""LPN parameter selection with the LPN estimator instead of the spec's lower bound.

The spec (docs/lpn_parameters.md §3) requires s * log2(c) >= lambda' (Prange iterations, no cost per
iteration). Here s is the smallest weight for which the LPN estimator of Yu, Yang, Wang et al.
(https://lpnestimator.com, code: github.com/1234wangtr/Code_estimators; we use the float version of
github.com/shachy12/Code_estimators, commit 82a6b00) gives at least the target, for dual exact LPN
(H in F_2^{t x m}, fixed-weight noise of weight s): the minimum over its attacks Pooled Gauss, SD,
SD 2.0, SD-ISD and BJMM-ISD, as its analysisfordual2(n = t, N = m, t = s). The spec's MITM and
brute-force conditions must also hold (the estimator does not cover them).

Targets: "lambda_eff" = lambda + log2 Q + ceil(log2 t) (the spec's margins kept), or an integer
number of bits (a single LPN instance, without those margins).
Set LPN_ESTIMATOR to the estimator's directory (default ~/projects/Code_estimators).
"""

import functools
import math
import os
import sys
from pathlib import Path

from rcpir_common.params import M_LIMIT
from rcpir_encoder import lpn

ESTIMATOR_DIR = Path(os.environ.get("LPN_ESTIMATOR", Path.home() / "projects/Code_estimators"))


@functools.cache
def _estimator():
    sys.dont_write_bytecode = True          # no __pycache__ in the estimator's directory
    sys.path.insert(0, str(ESTIMATOR_DIR))
    from lwyy import hardness_of_lpn
    return hardness_of_lpn


@functools.lru_cache(maxsize=None)
def estimated_bits(t, m, s):
    """Bit security of dual exact LPN with H in F_2^{t x m} and noise weight s, per the estimator."""
    h = _estimator()
    N, k = m, m - t
    return float(min(h.Gauss(N, k, s), h.SDfor2(N, k, s), h.SD2for2(N, k, s), h.SD_ISD(N, k, s), h.BJMM_ISD(N, k, s)))


def target_bits(lam, t, target):
    return lpn.lambda_eff(lam, t) if target == "lambda_eff" else int(target)


def _secure(t, m, s, bits):
    a = lpn.attack_bits(s, m, t)
    return min(a.mitm, a.brute_force) >= bits and estimated_bits(t, m, s) >= bits


@functools.lru_cache(maxsize=None)
def _min_s(t, m, bits):
    """Smallest s with _secure(t, m, s, bits); both conditions grow with s while s < m / e.
    The estimator's formulas need s < t (its SD attack divides by t - s), which only excludes tiny t."""
    hi = 1
    while not _secure(t, m, hi, bits):
        hi *= 2
        if hi > m / math.e or hi >= t:
            raise lpn.Infeasible(f"no secure s < t for t = {t}, m = {m}, target {bits} bits")
    lo = hi // 2 + 1 if hi > 1 else 1
    while lo < hi:
        mid = (lo + hi) // 2
        if _secure(t, m, mid, bits):
            hi = mid
        else:
            lo = mid + 1
    return lo


def mode_estimator(lam, t, ell, c, target="lambda_eff"):
    """Like lpn.mode_a (storage factor c -> s), with s chosen by the estimator for the target."""
    m = math.ceil(c * t)
    if not t < m <= M_LIMIT:
        raise lpn.Infeasible(f"need 1 < c and m = ceil(c t) <= 2^32 (got m = {m})")
    bits = target_bits(lam, t, target)
    return lpn.Selection(lam, t, ell, m, _min_s(t, m, bits), "estimator", {"c": c, "target_bits": bits})
