"""LPN parameter selection (docs/lpn_parameters.md).

Notation: X in F_2^{ell x t}, H in F_2^{t x m}, noise weight s, c = m / t.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from rcpir_common.params import INSECURE_MODE, M_LIMIT

LOG2_Q = 32                 # lifetime query budget per H
DEFAULT_LAMBDA = 128
DEFAULT_C = 16
C_MAX = 2**16               # Mode B cap on c
TABLE_CS = (2, 4, 16, 256, 4096)


class Infeasible(Exception):
    pass


def ceil_log2(x: int) -> int:
    """Exact ceil(log2 x) for an integer x >= 1."""
    return (x - 1).bit_length()


def lambda_eff(lam: int, t: int) -> int:
    """lambda' = lambda + log2 Q + ceil(log2 t)  (§2)."""
    return lam + LOG2_Q + ceil_log2(t)


@dataclass(frozen=True)
class Attacks:
    """Lower bounds on attack cost in bits (§3), using (m/s)^s <= C(m, s)."""
    prange: float
    mitm: float
    brute_force: float

    @property
    def binding(self) -> str:
        return "prange" if self.prange <= self.mitm else "mitm"


def attack_bits(s: int, m: int, t: int) -> Attacks:
    return Attacks(prange=s * math.log2(m / t), mitm=s / 2 * math.log2(m / s), brute_force=s * math.log2(m / s))


def secure(s: int, m: int, t: int, lam_eff: int) -> bool:
    if not 1 <= s <= m:
        return False
    a = attack_bits(s, m, t)
    return min(a.prange, a.mitm, a.brute_force) >= lam_eff


def m_min(s: int, t: int, lam_eff: int) -> int:
    """Smallest secure m for s: the closed form of §3."""
    m = math.ceil(max(t * 2 ** (lam_eff / s), s * 2 ** (2 * lam_eff / s)))
    while not secure(s, m, t, lam_eff):     # floating-point rounding at the boundary
        m += 1
    return m


@dataclass(frozen=True)
class Comm:
    """Communication in bits (§4)."""
    retrieval_up: int
    retrieval_down: int
    compute_up: int
    compute_down: int

    @property
    def total(self) -> int:
        return self.retrieval_up + self.retrieval_down + self.compute_up + self.compute_down


@dataclass
class Selection:
    lam: int
    t: int
    ell: int
    m: int
    s: int
    mode: str                       # "A", "B" or INSECURE_MODE ("insecure-override")
    mode_input: dict                # {"c": C} / {"target_comm_bits": C} / {}
    warnings: list[str] = field(default_factory=list)

    @property
    def lam_eff(self) -> int:
        return lambda_eff(self.lam, self.t)

    @property
    def c_eff(self) -> float:
        return self.m / self.t

    @property
    def n(self) -> int:
        return self.t * self.ell

    @property
    def storage_bits(self) -> int:
        return self.ell * self.m

    @property
    def attacks(self) -> Attacks:
        return attack_bits(self.s, self.m, self.t)

    @property
    def comm(self) -> Comm:
        return Comm(self.s * ceil_log2(self.m), self.s * self.ell, self.t, self.ell)

    def security_object(self) -> dict:
        """The `security` object of params.json (params_format.md §2)."""
        a = self.attacks
        obj = {
            "lambda": self.lam,
            "log2_Q": LOG2_Q,
            "lambda_eff": self.lam_eff,
            "c_eff": round(self.c_eff, 4),
            "attack_bits": {"prange": round(a.prange, 1), "mitm": round(a.mitm, 1),
                            "brute_force": round(a.brute_force, 1)},
            "binding_attack": a.binding,
            "mode": self.mode,
            **self.mode_input,
        }
        if self.mode == INSECURE_MODE:
            obj["insecure"] = True
        return obj


def mode_a(lam: int, t: int, ell: int, c: float = DEFAULT_C) -> Selection:
    """Mode A: storage factor c -> smallest secure s (§5)."""
    lam_e = lambda_eff(lam, t)
    m = math.ceil(c * t)
    if not t < m <= M_LIMIT:
        raise Infeasible(f"Mode A infeasible: need 1 < c and m = ceil(c t) <= 2^32 (got m = {m})")
    s0 = s = math.ceil(lam_e / math.log2(m / t))
    while not secure(s, m, t, lam_e):
        # For s > m/e the MITM and brute-force costs only decrease, so no larger s can work.
        if s > m / math.e:
            raise Infeasible(f"Mode A infeasible: no secure s for t = {t}, m = {m}, lambda' = {lam_e} "
                             f"(t too small for c = {c}; use a larger c or --insecure-m/--insecure-s for tests)")
        s += 1
    sel = Selection(lam, t, ell, m, s, "A", {"c": c})
    if s > s0:
        sel.warnings.append(f"MITM is binding (Prange alone gives s = {s0}): a larger c barely helps; "
                            f"a smaller c may give the same s")
    return sel


def mode_b(lam: int, t: int, ell: int, target_comm: int) -> Selection:
    """Mode B: target communication (bits) -> smallest secure m (§6)."""
    lam_e = lambda_eff(lam, t)
    m = 2 * t
    while True:                     # s never increases, so this terminates
        s = (target_comm - t - ell) // (ell + ceil_log2(m))
        if s < 1:
            raise Infeasible(_mode_b_failure(lam, t, ell, f"target {target_comm} bits leaves no room for s >= 1"))
        m_new = m_min(s, t, lam_e)
        if m_new == m:
            break
        m = m_new
    if m / t > C_MAX or m > M_LIMIT:
        raise Infeasible(_mode_b_failure(lam, t, ell, f"s = {s} needs c = {m / t:.1f} > c_max = {C_MAX}"))
    sel = Selection(lam, t, ell, m, s, "B", {"target_comm_bits": target_comm})
    assert secure(s, m, t, lam_e) and sel.comm.total <= target_comm
    if sel.attacks.binding == "mitm":
        sel.warnings.append("MITM is binding")
    return sel


def _mode_b_failure(lam: int, t: int, ell: int, reason: str) -> str:
    try:
        best = f"{mode_a(lam, t, ell, C_MAX).comm.total} bits (Mode A with c = c_max = {C_MAX})"
    except Infeasible:
        best = "unknown (Mode A with c_max is infeasible too)"
    return f"Mode B infeasible: {reason}. Minimum achievable communication: {best}"


def insecure_override(lam: int, t: int, ell: int, m: int, s: int) -> Selection:
    """Test only: use (m, s) as given, without any security check."""
    if not 1 <= s <= m <= M_LIMIT:
        raise ValueError(f"insecure override needs 1 <= s <= m <= 2^32 (got m = {m}, s = {s})")
    return Selection(lam, t, ell, m, s, INSECURE_MODE, {},
                     ["INSECURE parameters (--insecure-m/--insecure-s): for testing only"])


# ----------------------------------------------------------------------------------------------
# Reports (§7)

def _size(bits: float) -> str:
    b = bits / 8
    for unit in ("B", "KiB", "MiB", "GiB"):
        if b < 1024 or unit == "GiB":
            return f"{b:.1f} {unit}"
        b /= 1024


def report(sel: Selection) -> str:
    a, c = sel.attacks, sel.comm
    mode = {"A": f"Mode A, c = {sel.mode_input.get('c')}",
            "B": f"Mode B, target communication = {sel.mode_input.get('target_comm_bits')} bits",
            INSECURE_MODE: "insecure override"}[sel.mode]
    lines = []
    if sel.mode == INSECURE_MODE:
        lines += ["!" * 80,
                  "!!  INSECURE PARAMETER OVERRIDE: m and s were NOT checked against LPN attacks.",
                  "!!  For testing only. params.json records security.insecure = true.",
                  "!" * 80]
    lines += [
        f"LPN parameters: {mode}",
        f"  lambda = {sel.lam}, lambda' = {sel.lam_eff}  (lambda + log2 Q [{LOG2_Q}] + ceil(log2 t))",
        f"  n = {sel.n} bits ({_size(sel.n)}), t = {sel.t}, ell = {sel.ell}",
        f"  m = {sel.m}, c_eff = m/t = {sel.c_eff:.4g}, s = {sel.s}",
        f"  attack costs (bits): prange {a.prange:.1f}, mitm {a.mitm:.1f}, brute force {a.brute_force:.1f}"
        f"  -> binding: {a.binding}",
        f"  retrieval storage: {_size(sel.storage_bits)} = {sel.c_eff:.4g} n",
        f"  retrieval server: upload {c.retrieval_up} bits, download {c.retrieval_down} bits ({sel.s} fetches)",
        f"  compute server:   upload {c.compute_up} bits, download {c.compute_down} bits",
        f"  total communication: {c.total} bits ({_size(c.total)})",
    ]
    lines += [f"  WARNING: {w}" for w in sel.warnings]
    return "\n".join(lines)


def table(lam: int, t: int, ell: int) -> str:
    """Mode A for several c (--table)."""
    rows = [f"Mode A trade-off (lambda' = {lambda_eff(lam, t)})",
            f"  {'c':>6} {'s':>5} {'binding':>8} {'storage':>12} {'total comm':>12}"]
    for c in TABLE_CS:
        try:
            sel = mode_a(lam, t, ell, c)
            rows.append(f"  {c:>6} {sel.s:>5} {sel.attacks.binding:>8} {_size(sel.storage_bits):>12}"
                        f" {_size(sel.comm.total):>12}")
        except Infeasible:
            rows.append(f"  {c:>6}  infeasible")
    return "\n".join(rows)
