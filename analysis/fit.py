"""HALF-LIFE pre-registered analysis (frozen before any build result exists).

Input: a JSONL of build receipts, one per (repo, snapshot). Fields used: ecosystem, year, snapshot
("ERA" or "NOW"), exit_code (int), failure_class (str), ai_marker (bool, optional, NOW rows only).
Rows with failure_class == "NO-MANIFEST" are excluded from every denominator and counted separately.

Confirmatory tests (PREREG_DRAFT.md):
  H1  per ecosystem, ERA success decreases with age: Cochran-Armitage trend test, one-sided,
      alpha 0.0125 (Bonferroni over 4 ecosystems).
  H2  per ecosystem, half-life T from S(age) = exp(-ln2 * age / T) by maximum likelihood on ERA rows;
      bootstrap 95% CI, 1,000 resamples by repo. Supported if the CIs of the best and worst
      ecosystem do not overlap.
  H3  2023-2024 cohorts, NOW rows: AI-marker repos vs others, two-sided Fisher exact, alpha 0.05.
Everything else is descriptive.

Usage: python fit.py receipts.jsonl --asof 2026 [--seed 20261109] > RESULT.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict

ECOSYSTEMS = ("python", "node", "go", "rust")
LN2 = math.log(2.0)


def load(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def age_of(row, asof):
    return asof - int(row["year"])


def success(row):
    return int(row["exit_code"]) == 0


def valid(rows):
    """Drop NO-MANIFEST rows from denominators; return (kept, dropped_count)."""
    kept = [r for r in rows if r.get("failure_class") != "NO-MANIFEST"]
    return kept, len(rows) - len(kept)


# ---------- H2: exponential survival, MLE for T ----------


def mle_halflife(ages, outcomes):
    """Maximise sum_i [y_i log S(a_i) + (1-y_i) log(1-S(a_i))], S(a)=exp(-ln2 a/T).
    Golden-section search on T in (0.1, 1000] years; returns T (float) or None if no data."""
    if not ages:
        return None
    if all(outcomes):
        return (
            math.inf
        )  # nothing has decayed: half-life not identifiable, reported as inf
    if not any(outcomes):
        return 0.0

    def nll(T):
        s = 0.0
        for a, y in zip(ages, outcomes):
            S = math.exp(-LN2 * a / T)
            S = min(max(S, 1e-12), 1 - 1e-12)
            s -= math.log(S) if y else math.log(1 - S)
        return s

    lo, hi = 0.1, 1000.0
    gr = (math.sqrt(5) - 1) / 2
    c = hi - gr * (hi - lo)
    d = lo + gr * (hi - lo)
    for _ in range(200):
        if nll(c) < nll(d):
            hi = d
        else:
            lo = c
        c = hi - gr * (hi - lo)
        d = lo + gr * (hi - lo)
    return (lo + hi) / 2


def bootstrap_ci(ages, outcomes, n=1000, seed=0):
    rng = random.Random(seed)
    m = len(ages)
    ests = []
    for _ in range(n):
        idx = [rng.randrange(m) for _ in range(m)]
        ests.append(mle_halflife([ages[i] for i in idx], [outcomes[i] for i in idx]))
    finite = sorted(e for e in ests if e is not None)
    if not finite:
        return (None, None)
    lo = finite[int(0.025 * (len(finite) - 1))]
    hi = finite[int(0.975 * (len(finite) - 1))]
    return (lo, hi)


# ---------- H1: Cochran-Armitage trend test ----------


def _norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def cochran_armitage(groups):
    """groups: list of (score, successes, total) ordered by score (age). One-sided test that
    success decreases with age (negative trend). Returns (z, p_one_sided)."""
    N = sum(t for _, _, t in groups)
    if N == 0:
        return (None, None)
    R = sum(s for _, s, _ in groups)
    pbar = R / N
    xbar = sum(x * t for x, _, t in groups) / N
    num = sum((x - xbar) * s for x, s, _ in groups)
    var = pbar * (1 - pbar) * sum(t * (x - xbar) ** 2 for x, _, t in groups)
    if var <= 0:
        return (None, None)
    z = num / math.sqrt(var)
    # negative z means success falls with age; one-sided p for that direction
    return (z, _norm_sf(-z))


# ---------- H3: Fisher exact (two-sided) ----------


def fisher_two_sided(a, b, c, d):
    """2x2 table [[a, b], [c, d]]: rows = marker yes/no, cols = success/fail."""
    n = a + b + c + d
    if n == 0:
        return None

    def logc(n_, k_):
        return math.lgamma(n_ + 1) - math.lgamma(k_ + 1) - math.lgamma(n_ - k_ + 1)

    r1, r2, c1 = a + b, c + d, a + c

    def p_of(x):
        return math.exp(logc(r1, x) + logc(r2, c1 - x) - logc(n, c1))

    lo, hi = max(0, c1 - r2), min(r1, c1)
    p_obs = p_of(a)
    total = 0.0
    for x in range(lo, hi + 1):
        px = p_of(x)
        if px <= p_obs * (1 + 1e-9):
            total += px
    return min(1.0, total)


# ---------- driver ----------


def analyse(rows, asof, seed=20261109):
    kept, dropped = valid(rows)
    out = {
        "asof": asof,
        "rows": len(rows),
        "no_manifest_excluded": dropped,
        "ecosystems": {},
    }
    era = [r for r in kept if r["snapshot"] == "ERA"]
    for eco in ECOSYSTEMS:
        sub = [r for r in era if r["ecosystem"] == eco]
        ages = [age_of(r, asof) for r in sub]
        outs = [success(r) for r in sub]
        by_age = defaultdict(lambda: [0, 0])
        for a, y in zip(ages, outs):
            by_age[a][1] += 1
            by_age[a][0] += int(y)
        groups = sorted((a, s, t) for a, (s, t) in by_age.items())
        z, p = cochran_armitage(groups)
        T = mle_halflife(ages, outs)
        ci = bootstrap_ci(ages, outs, seed=seed) if sub else (None, None)
        out["ecosystems"][eco] = {
            "n_era": len(sub),
            "success_by_age": {str(a): {"ok": s, "n": t} for a, s, t in groups},
            "h1_trend_z": z,
            "h1_p_one_sided": p,
            "h1_verdict": (p is not None and p < 0.0125),
            "h2_halflife_years": T,
            "h2_ci95": list(ci),
        }
    finite = {
        e: v
        for e, v in out["ecosystems"].items()
        if v["h2_ci95"][0] is not None
        and v["h2_halflife_years"] not in (None, math.inf)
    }
    if len(finite) >= 2:
        best = max(finite, key=lambda e: finite[e]["h2_halflife_years"])
        worst = min(finite, key=lambda e: finite[e]["h2_halflife_years"])
        out["h2_best"], out["h2_worst"] = best, worst
        out["h2_verdict"] = finite[worst]["h2_ci95"][1] < finite[best]["h2_ci95"][0]
    else:
        out["h2_verdict"] = None
    now = [
        r
        for r in kept
        if r["snapshot"] == "NOW"
        and int(r["year"]) in (2023, 2024)
        and "ai_marker" in r
    ]
    a = sum(1 for r in now if r["ai_marker"] and success(r))
    b = sum(1 for r in now if r["ai_marker"] and not success(r))
    c = sum(1 for r in now if not r["ai_marker"] and success(r))
    d = sum(1 for r in now if not r["ai_marker"] and not success(r))
    out["h3"] = {
        "table": {"marker_ok": a, "marker_fail": b, "other_ok": c, "other_fail": d},
        "p_two_sided": fisher_two_sided(a, b, c, d) if now else None,
        "verdict": (
            fisher_two_sided(a, b, c, d) < 0.05
            and (a / (a + b) if a + b else 0) < (c / (c + d) if c + d else 0)
        )
        if now and (a + b) and (c + d)
        else None,
    }
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("receipts")
    ap.add_argument("--asof", type=int, required=True, help="analysis year, e.g. 2026")
    ap.add_argument("--seed", type=int, default=20261109)
    args = ap.parse_args(argv)
    res = analyse(load(args.receipts), args.asof, args.seed)
    json.dump(
        res, sys.stdout, indent=2, default=lambda o: "inf" if o == math.inf else str(o)
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
