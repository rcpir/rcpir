"""Reference values of docs/lpn_parameters.md §8 and params_format.md §3."""

import pytest

from rcpir_encoder import lpn

T = ELL = 2**14     # n = 2^28 bits, lambda' = 174


def kib(bits):
    return round(bits / 8 / 1024, 1)


@pytest.mark.parametrize("c,s,binding,comm_kib", [
    (2, 174, "prange", 352.3),
    (4, 87, "prange", 178.2),
    (16, 44, "prange", 92.1),
    (256, 22, "prange", 48.1),
    (4096, 16, "mitm", 36.1),
])
def test_mode_a_reference_table(c, s, binding, comm_kib):
    sel = lpn.mode_a(128, T, ELL, c)
    assert sel.s == s
    assert sel.m == c * T
    assert sel.attacks.binding == binding
    assert sel.storage_bits == c * sel.n
    assert kib(sel.comm.total) == comm_kib
    assert lpn.secure(sel.s, sel.m, T, 174)
    assert not lpn.secure(sel.s - 1, sel.m, T, 174)
    assert bool(sel.warnings) == (binding == "mitm")


@pytest.mark.parametrize("k,s,c_eff,gib,comm_kib", [
    (20, 17, 1507.6, 47.11, 38.1),
    (32, 29, 64.0, 2.00, 62.1),
    (48, 45, 14.6, 0.46, 94.1),
    (64, 61, 7.2, 0.23, 126.1),
    (100, 97, 3.5, 0.11, 198.2),
    (184, 181, 1.9, 0.06, 366.3),
])
def test_mode_b_reference_table(k, s, c_eff, gib, comm_kib):
    target = k * 2**14            # k * sqrt(n)
    sel = lpn.mode_b(128, T, ELL, target)
    assert sel.s == s
    assert round(sel.c_eff, 1) == c_eff
    assert round(sel.storage_bits / 8 / 2**30, 2) == gib
    assert kib(sel.comm.total) == comm_kib
    assert sel.comm.total <= target
    assert lpn.secure(sel.s, sel.m, T, 174)
    assert not lpn.secure(sel.s, sel.m - 1, T, 174)     # m is minimal for s


def test_params_example_security_object():
    sel = lpn.mode_a(128, 2**17, 2**15, 16)
    assert sel.s == 45 and sel.m == 2**21
    assert sel.security_object() == {
        "lambda": 128, "log2_Q": 32, "lambda_eff": 177, "c_eff": 16.0,
        "attack_bits": {"prange": 180.0, "mitm": 348.9, "brute_force": 697.9},
        "binding_attack": "prange", "mode": "A", "c": 16,
    }


def test_mode_a_small_t_infeasible_terminates():
    with pytest.raises(lpn.Infeasible, match="infeasible"):
        lpn.mode_a(128, 3, 64, 16)
    with pytest.raises(lpn.Infeasible):
        lpn.mode_a(128, 10, 64, 16)
    assert lpn.mode_a(128, 1000, 64, 16).s == 43     # feasible already for t = 1000


def test_mode_a_rejects_c_le_1_and_huge_m():
    with pytest.raises(lpn.Infeasible):
        lpn.mode_a(128, 100, 64, 1)
    with pytest.raises(lpn.Infeasible):
        lpn.mode_a(128, 2**31, 64, 4)


def test_mode_b_infeasible_reports_min_comm():
    with pytest.raises(lpn.Infeasible) as ei:
        lpn.mode_b(128, T, ELL, 3 * 2**14)          # leaves room for s = 0
    assert f"{lpn.mode_a(128, T, ELL, lpn.C_MAX).comm.total} bits" in str(ei.value)
    with pytest.raises(lpn.Infeasible):
        lpn.mode_b(128, T, ELL, 16 * 2**14)         # s = 13 needs c > 2^16


def test_insecure_override():
    sel = lpn.insecure_override(128, 3, 128, 40, 5)
    obj = sel.security_object()
    assert obj["mode"] == "insecure-override" and obj["insecure"] is True
    assert set(obj["attack_bits"]) == {"prange", "mitm", "brute_force"}
    assert "INSECURE" in lpn.report(sel)
    with pytest.raises(ValueError):
        lpn.insecure_override(128, 3, 128, 4, 5)
