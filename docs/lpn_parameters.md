# LPN Parameter Selection for the √n RC-PIR

Status: agreed spec (to be implemented). Agreed defaults: $\lambda=128$, $c=16$, $c_{\max}=2^{16}$, $Q=2^{32}$. The scheme is the RC-PIR construction
"Optimized Toy Example". Field: $\mathbb{F}_2$.

## 1. Scheme recap and notation

| Symbol | Meaning |
|---|---|
| $n$ | database size in bits |
| $t,\ \ell$ | database shape: $X\in\mathbb{F}_2^{\ell\times t}$, $n=t\ell$. Taken from the input DB: $t$ = number of blocks, $\ell$ = max encoded block size (see `docs/db_format.md`) |
| $m$ | number of columns of the public matrix $H\in\mathbb{F}_2^{t\times m}$ |
| $c=m/t$ | storage expansion factor (need not be an integer; only $m$ is stored) |
| $s$ | noise weight (sparsity) of $e\in\mathbb{F}_2^m$ |
| $\lambda$ | target security level in bits (input) |
| $Q=2^{32}$ | lifetime number of queries per $H$ (fixed constant) |

- Encoding: $R = XH\in\mathbb{F}_2^{\ell\times m}$; block $j$ = column $R_{*,j}$ ($\ell$ bits).
- Query for column $i\in[t]$: sample $e$ with uniformly random support $S\subseteq[m]$, $|S|=s$.
  Retrieval query $S$; compute query $q_c=He+e_i$.
- Decode: $Xq_c-\sum_{j\in S}R_{*,j}=Xe_i$.

Privacy against the compute server rests on $(t,m,s)$-dLPN over $\mathbb{F}_2$:
$(H,He)\approx_c(H,U_t)$, with $H$ uniform and $e$ of fixed weight $s$.

## 2. Threat model

- Classical adversary only (quantum attacks are out of scope for now).
- $H$ is uniformly random (no quasi-cyclic or sparse structure).
- Noise has fixed weight $s$ with a uniformly random support (not regular noise).
- No extra margin for advanced ISD variants (Stern, MMT, BJMM, …). For sub-linear
  weight these share Prange's exponent $2^{s\log_2 c\,(1+o(1))}$ (Canto Torres–Sendrier);
  the user absorbs lower-order gains into the choice of $\lambda$.

### Effective security target

$$\lambda' = \lambda + \log_2 Q + \lceil\log_2 t\rceil = \lambda + 32 + \lceil\log_2 t\rceil .$$

- $\log_2 Q$ covers the hybrid loss over $Q$ queries and multi-target ("decoding one out of
  many") speedups from reusing $H$.
- $\log_2 t$ covers the attacker trying all shifts $q_c+e_j$, $j\in[t]$, for the unknown index.
  (An earlier draft used $\log_2\ell$; identical for square shapes such as §8.)

## 3. Security conditions

All three are *lower bounds* on attack cost, in bits. They use $(m/s)^s\le\binom{m}{s}$,
which errs on the safe side. Do not use $m^s$: it overestimates the attack cost.

| Attack | Condition |
|---|---|
| Prange ISD | $\ s\log_2 c \ \ge\ \lambda'$ |
| Meet in the middle | $\ \tfrac{s}{2}\log_2\tfrac{m}{s} \ \ge\ \lambda'$ |
| Brute force | $\ s\log_2\tfrac{m}{s} \ \ge\ \lambda'$ (implied by MITM; checked for completeness) |

Define `secure(s, m, t, λ')` as the conjunction of the three conditions.

Equivalent closed form for the smallest $m$ that is secure for a given $s$:

$$m_{\min}(s) = \Big\lceil \max\big(t\cdot 2^{\lambda'/s},\ \ s\cdot 2^{2\lambda'/s}\big)\Big\rceil .$$

The first term comes from Prange and the second from MITM.

## 4. Cost accounting (bits)

| Item | Cost |
|---|---|
| Retrieval upload | $s\lceil\log_2 m\rceil$ |
| Retrieval download | $s\ell$ |
| Compute upload | $t$ |
| Compute download | $\ell$ |
| **Total communication** $\mathrm{Comm}(s,m)$ | $t+\ell+s\ell+s\lceil\log_2 m\rceil$ |
| Retrieval storage | $\ell m = c\cdot t\ell \approx c\,n$ |
| Number of retrieval fetches | $s$ |

$H$ ($t\cdot m$ bits) is a public parameter and is not counted (how it is distributed or
derived is a stack decision).

## 5. Mode A: forward (storage factor → communication)

Input: $\lambda$, $t$, $\ell$ (from the DB), $c$ (default $c=16$).

1. $\lambda'=\lambda+32+\lceil\log_2 t\rceil$, $m=\lceil ct\rceil$, $c_{\rm eff}=m/t$.
   Infeasible unless $c>1$ and $m\le 2^{32}$.
2. $s_0=\lceil\lambda'/\log_2 c_{\rm eff}\rceil$ (Prange); $s=s_0$.
3. While not `secure(s, m, t, λ')`: $s\gets s+1$; if $s>m/e$: **infeasible**.
   (MITM cost is increasing in $s$ only for $s<m/e$; beyond that it decreases, so no larger $s$ helps.
   This happens for small $t$, e.g. $t=3$, $c=16$.)
4. Output the report (§7). If $s>s_0$, **warn: MITM is binding**. In that case a larger $c$
   barely helps, and a smaller $c$ may give the same $s$.

## 6. Mode B: inverse (target communication → storage, for approval)

Input: $\lambda$, $t$, $\ell$ (from the DB), target communication $C$ (bits), optional cap $c_{\max}$ (default $2^{16}$).

1. $\lambda'$ as above, $m\gets 2t$.
2. Repeat until $m$ is stable. $s$ is non-increasing across iterations, so this terminates:
   - $s=\big\lfloor (C-t-\ell)/(\ell+\lceil\log_2 m\rceil)\big\rfloor$;
     if $s<1$: **infeasible** (see below);
   - $m\gets m_{\min}(s)$.
3. If $m/t>c_{\max}$ or $m>2^{32}$: **infeasible**.
4. Assert `secure(s, m, t, λ')` and $\mathrm{Comm}(s,m)\le C$.
5. Print the report (§7) and **ask the user to approve** before encoding.

On infeasibility, report the minimum achievable communication: run Mode A with $c=c_{\max}$
and print its $\mathrm{Comm}$.

## 7. Report (both modes)

Print: $\lambda,\ \lambda',\ n,\ t,\ \ell,\ m,\ c_{\rm eff},\ s$; each attack cost in bits and which
one is binding; storage (bits and GiB, and as a multiple of $n$); per-server upload and download;
total communication; number of retrieval fetches.

Optional `--table` flag: print Mode A for $c\in\{2,4,16,256,4096\}$ so that the user can see
the trade-off.

## 8. Reference values (for tests)

$\lambda=128$, $Q=2^{32}$, $n=2^{28}$ bits (32 MiB), $t=\ell=2^{14}$, $\lambda'=174$.
(Recomputed after changing $Q$ from $2^{40}$ to $2^{32}$; with $Q=2^{40}$ the same script reproduces
the previous tables.)

Mode A:

| $c$ | $s$ | Binding | Storage | Total comm. |
|---|---|---|---|---|
| 2 | 174 | Prange | $2n$ = 64 MiB | 352.3 KiB |
| 4 | 87 | Prange | $4n$ = 128 MiB | 178.2 KiB |
| 16 | 44 | Prange | $16n$ = 512 MiB | 92.1 KiB |
| 256 | 22 | Prange | $256n$ = 8 GiB | 48.1 KiB |
| 4096 | 16 | **MITM** (Prange alone gives 15) | $4096n$ = 128 GiB | 36.1 KiB |

Mode B:

| Target $C$ | $s$ | $c_{\rm eff}$ | Storage | Actual comm. |
|---|---|---|---|---|
| $20\sqrt n$ | 17 | 1507.6 (MITM) | 47.11 GiB | 38.1 KiB |
| $32\sqrt n$ | 29 | 64.0 | 2.00 GiB | 62.1 KiB |
| $48\sqrt n$ | 45 | 14.6 | 0.46 GiB | 94.1 KiB |
| $64\sqrt n$ | 61 | 7.2 | 0.23 GiB | 126.1 KiB |
| $100\sqrt n$ | 97 | 3.5 | 0.11 GiB | 198.2 KiB |
| $184\sqrt n$ | 181 | 1.9 | 0.06 GiB | 366.3 KiB |

Rule of thumb: $s\approx\lambda'/\log_2 c$, so halving communication squares $c$.

## 9. Out of scope / revisit later

- Quantum attackers (Grover + Prange would double $s$).
- Structured $H$ (quasi-cyclic or sparse) or regular noise. These need extra attacks:
  linear tests, algebraic attacks (Briaud–Øygarden 2023), and a quasi-cyclic DOOM factor.
- Automatic reshaping. The shape now comes from the user's block list; the tool only warns
  when it is unbalanced (optimum near $t\approx(s+1)\ell$, communication about $2\sqrt{(s+1)n}$).
- Calibration against an estimator (CryptographicEstimators SD estimator; Liu–Wang–Yang–Yu
  LPN estimator).

## References

- Canto Torres, Sendrier. *Analysis of Information Set Decoding for a Sub-linear Error Weight*, PQCrypto 2016. https://hal.archives-ouvertes.fr/hal-01244886
- Sendrier. *Decoding One Out of Many*, PQCrypto 2011 (surveyed in https://arxiv.org/pdf/2209.06656).
- Esser, Bellini. *Syndrome Decoding Estimator*, PKC 2022. https://eprint.iacr.org/2021/1243
- Liu, Wang, Yang, Yu. *The Hardness of LPN over Any Integer Ring and Field for PCG Applications*, EUROCRYPT 2024. https://eprint.iacr.org/2022/712
