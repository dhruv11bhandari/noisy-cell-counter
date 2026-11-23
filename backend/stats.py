import numpy as np
from scipy import stats as st

PRIORS = {"jeffreys": (0.5, 0.001), "project": (1.0, 1.0)}  # Gamma(alpha, beta), rate form


def tiles(pts, h, w, k):
    ix = np.minimum((pts[:, 0] / w * k).astype(int), k - 1)
    iy = np.minimum((pts[:, 1] / h * k).astype(int), k - 1)
    return np.bincount(iy * k + ix, minlength=k * k)


def model(x, pr, level=0.9, B=4000):
    n, S = len(x), int(x.sum())
    q = (1 - level) / 2
    out = dict(tiles=x.tolist(), tilemean=S / n)
    if S == 0:
        return out
    m = S / n
    D = float(x.var(ddof=1) / m)  # index of dispersion: 1 for pure Poisson
    sim = np.random.default_rng(0).poisson(m, (B, n))  # p-value: how often pure Poisson is this spread out
    sm = np.maximum(sim.mean(1), 1e-9)
    p = float((1 + (sim.var(1, ddof=1) / sm >= D - 1e-12).sum()) / (B + 1))
    a, b = pr[0] + S, pr[1] + n  # conjugate update: Gamma(alpha + sum x, beta + n)
    lo, hi = st.gamma.ppf([q, 1 - q], a, scale=1 / b)
    mu, f = a / b, max(1.0, D ** 0.5)  # overdispersed -> widen by sqrt(D) (quasi-Poisson)
    cs, ns = np.cumsum(x), np.arange(1, n + 1)  # sequential updating, one tile at a time
    seq = st.gamma.ppf([[q], [1 - q]], pr[0] + cs, scale=1 / (pr[1] + ns))
    cov = {}  # leave-one-tile-out coverage of the negative-binomial predictive interval
    for L in (0.5, 0.8, 0.9):
        ql, hit = (1 - L) / 2, 0
        for i in range(n):
            a2, b2 = pr[0] + S - x[i], pr[1] + n - 1
            l2, h2 = st.nbinom.ppf([ql, 1 - ql], a2, b2 / (b2 + 1))
            hit += int(l2 <= x[i] <= h2)
        cov[L] = hit / n
    gap = float(np.mean([abs(L - c) for L, c in cov.items()]))  # the course's "average gap"
    sg = np.mean([c - L for L, c in cov.items()])
    label = "calibrated" if gap < 0.05 else "overconfident" if sg < 0 else "underconfident"
    out.update(D=D, p=p, lo=lo * n, hi=hi * n, alo=max(0.0, mu - (mu - lo) * f) * n,
               ahi=(mu + (hi - mu) * f) * n, f=f, seq=seq.tolist(), gap=gap, label=label)
    return out
