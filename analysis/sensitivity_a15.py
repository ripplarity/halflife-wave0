"""HALF-LIFE A15 check 2: the two secondary sensitivity fits. Never replaces the headline.

(a) pre-registered model with recipe id as a fixed effect. fit.py's model has no regression intercept,
    so the fixed effect is realised as stratification by recipe id: H1 = stratified Cochran-Armitage
    (per-stratum scores and variances summed, z = sum U / sqrt(sum V)). H2 (exponential MLE) and H3
    (Fisher) have no intercept to absorb a fixed effect; they are recomputed by fit.analyse unchanged.
(b) fit.analyse on v2j receipts only, if every ERA cell (ecosystem x year) has >= 30 of them; else skipped.
Imports analysis/fit.py's functions; never runs fit.py's main.
Usage: python -B analysis/sensitivity_a15.py ROWS.jsonl --asof 2026   (merged rows, same input as fit.py)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit

MIN_CELL = 30


def rev(row):
    rid = str(row.get("recipe_id", ""))
    return rid.rsplit("-", 1)[-1] if rid else ""


def stratified_ca(strata):
    """strata: list of group lists [(score, succ, total)]. Returns (z, p_one_sided) for a falling trend."""
    U = V = 0.0
    for groups in strata:
        N = sum(t for _, _, t in groups)
        if N == 0:
            continue
        pbar = sum(s for _, s, _ in groups) / N
        xbar = sum(x * t for x, _, t in groups) / N
        U += sum((x - xbar) * s for x, s, _ in groups)
        V += pbar * (1 - pbar) * sum(t * (x - xbar) ** 2 for x, _, t in groups)
    if V <= 0:
        return (None, None)
    z = U / math.sqrt(V)
    return (z, fit._norm_sf(-z))


def fixed_effect(rows, asof, seed=20261109):
    base = fit.analyse(rows, asof, seed)
    kept, _ = fit.valid(rows)
    for eco in fit.ECOSYSTEMS:
        by = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        for r in kept:
            if r["snapshot"] == "ERA" and r["ecosystem"] == eco:
                c = by[rev(r)][fit.age_of(r, asof)]
                c[1] += 1
                c[0] += int(fit.success(r))
        strata = [sorted((a, s, t) for a, (s, t) in g.items()) for g in by.values()]
        z, p = stratified_ca(strata)
        e = base["ecosystems"][eco]
        e["h1_trend_z"], e["h1_p_one_sided"] = z, p
        e["h1_verdict"] = p is not None and p < 0.0125
        e["recipe_strata"] = sorted(by)
    base["sensitivity"] = "a_recipe_fixed_effect"
    return base


def cell_counts(rows):
    n = defaultdict(int)
    for r in fit.valid(rows)[0]:
        if r["snapshot"] == "ERA":
            n[(r["ecosystem"], int(r["year"]))] += 1
    return n


def v2j_only(rows, asof, seed=20261109, years=range(2013, 2025)):
    sub = [r for r in rows if rev(r) == "v2j"]
    n = cell_counts(sub)
    short = [
        f"{e}/{y}" for e in fit.ECOSYSTEMS for y in years if n.get((e, y), 0) < MIN_CELL
    ]
    if short:
        return {"sensitivity": "b_v2j_only", "skipped": True, "short_cells": short}
    out = fit.analyse(sub, asof, seed)
    out["sensitivity"], out["skipped"] = "b_v2j_only", False
    return out


def verdict_changes(head, alt):
    if alt.get("skipped"):
        return []
    ch = []
    for e in fit.ECOSYSTEMS:
        if head["ecosystems"][e]["h1_verdict"] != alt["ecosystems"][e]["h1_verdict"]:
            ch.append("H1/" + e)
    if head.get("h2_verdict") != alt.get("h2_verdict"):
        ch.append("H2")
    if head["h3"]["verdict"] != alt["h3"]["verdict"]:
        ch.append("H3")
    return ch


def summarise(head, fa, fb):
    """Shape read by publish/fill.py a15_sensitivity_values (plus the full fits under "detail")."""
    ca, cb = verdict_changes(head, fa), verdict_changes(head, fb)
    a = {
        "verdict_changed": bool(ca),
        "summary": "recipe id as a fixed effect: "
        + ("verdict changed for " + ", ".join(ca) if ca else "no verdict changed"),
    }
    if fb.get("skipped"):
        b = {
            "ran": False,
            "verdict_changed": None,
            "summary": "v2j-only fit not run: %d cells hold fewer than %d v2j receipts"
            % (len(fb["short_cells"]), MIN_CELL),
        }
    else:
        b = {
            "ran": True,
            "verdict_changed": bool(cb),
            "summary": "v2j receipts only: "
            + ("verdict changed for " + ", ".join(cb) if cb else "no verdict changed"),
        }
    return {"a": a, "b": b, "detail": {"a": fa, "b": fb}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("--asof", type=int, required=True)
    ap.add_argument("--seed", type=int, default=20261109)
    a = ap.parse_args(argv)
    rows = fit.load(a.rows)
    head = fit.analyse(rows, a.asof, a.seed)
    res = summarise(
        head, fixed_effect(rows, a.asof, a.seed), v2j_only(rows, a.asof, a.seed)
    )
    json.dump(
        res, sys.stdout, indent=2, default=lambda o: "inf" if o == math.inf else str(o)
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
