"""HALF-LIFE A15 check 1: per-revision rebuild agreement (block 10b). New file; qa/agreement.py (A8/A10) is unchanged.

For each sample row of qa/A15_SAMPLE.jsonl ({"revision","rank","receipt"}), the original receipt (by file name in
ORIG_DIR) and its rebuild (matched by commit + snapshot in REBUILD_DIR) are compared. Agreement = the same value of
(exit_code == 0), exactly as A15 words it; no other field is compared.
Rules (A15): v2g, v2i: agreement below 95 % -> REBUILD-ALL for that revision (every receipt of it is rebuilt under
the final revision and the rebuild is the row of record; the fit still runs once). v2j: reported with an exact
(Clopper-Pearson) 95 % interval; no row is replaced.

Usage: python -B qa/a15_agreement.py ORIG_DIR REBUILD_DIR [--sample qa/A15_SAMPLE.jsonl] [--out qa/A15_AGREEMENT.json]
Prints one line per revision ("v2g agree=a of=m rate=..% STANDS|REBUILD-ALL", "v2j ... ci=..% to ..%").
--out writes {"v2g": {"agree": a, "of": m}, "v2i": {...}, "v2j": {...}}, the input of publish/fill.py --a15-agreement
(fill recomputes the rule and the interval itself).
Exit 0 v2g and v2i stand; 10 v2g or v2i REBUILD-ALL; 2 bad input (missing receipt or rebuild, unknown revision,
more than 60 rows for a revision, empty revision).
"""

from __future__ import annotations

import argparse
import json
import sys
from math import comb
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
REVISIONS = ("v2g", "v2i", "v2j")
RULED = ("v2g", "v2i")
N_MAX = 60


def ok(r):
    return type(r.get("exit_code")) is int and r["exit_code"] == 0


def clopper_pearson(k: int, n: int, alpha: float = 0.05):
    """Exact two-sided interval by bisection on the binomial tail (stdlib only)."""

    def cdf(x, p):
        return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(x + 1))

    def bisect(f):
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid):
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else bisect(lambda p: cdf(k - 1, p) > 1 - alpha / 2)
    upper = 1.0 if k == n else bisect(lambda p: cdf(k, p) > alpha / 2)
    return lower, upper


def rebuild_index(d: Path):
    idx = {}
    for p in sorted(d.glob("*.json"), key=lambda x: x.name):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(r, dict) and "commit" in r and "snapshot" in r:
            k = (r["commit"], r["snapshot"])
            if k in idx:
                raise SystemExit(f"{d}: two receipts for {k}")
            idx[k] = r
    return idx


def compare(sample: Path, orig: Path, reb: Path):
    ridx = rebuild_index(reb)
    res = {r: {"agree": 0, "of": 0} for r in REVISIONS}
    for line in sample.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rev = row.get("revision")
        if rev not in res:
            raise SystemExit(f"unknown revision {rev!r}")
        p = orig / row["receipt"]
        if not p.is_file():
            raise SystemExit(f"original receipt missing: {row['receipt']}")
        a = json.loads(p.read_text(encoding="utf-8"))
        k = (a.get("commit"), a.get("snapshot"))
        if k not in ridx:
            raise SystemExit(f"no rebuild for {row['receipt']} {k}")
        res[rev]["of"] += 1
        res[rev]["agree"] += ok(a) == ok(ridx[k])
    for r, e in res.items():
        if not 0 < e["of"] <= N_MAX:
            raise SystemExit(f"{r}: {e['of']} rows (must be 1 to {N_MAX})")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("orig_dir")
    ap.add_argument("rebuild_dir")
    ap.add_argument("--sample", default=str(STUDY / "qa" / "A15_SAMPLE.jsonl"))
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        res = compare(Path(a.sample), Path(a.orig_dir), Path(a.rebuild_dir))
    except SystemExit as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    rebuild_all = False
    for r in REVISIONS:
        ag, of = res[r]["agree"], res[r]["of"]
        line = f"{r} agree={ag} of={of} rate={100 * ag / of:.1f}%"
        if r in RULED:
            stands = 100 * ag >= 95 * of
            rebuild_all |= not stands
            line += " STANDS" if stands else " REBUILD-ALL"
        else:
            lo, hi = clopper_pearson(ag, of)
            line += f" ci={100 * lo:.1f}% to {100 * hi:.1f}% (report only)"
        print(line)
    if a.out:
        Path(a.out).write_text(json.dumps(res, sort_keys=True) + "\n", encoding="utf-8")
    return 10 if rebuild_all else 0


if __name__ == "__main__":
    sys.exit(main())
