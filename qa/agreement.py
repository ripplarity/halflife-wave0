"""HALF-LIFE A8/A10 rebuild-agreement check on the frozen 100-row sample (qa/REBUILD_SAMPLE.jsonl).

For each sample row (commit + snapshot) the original CORE receipt and its rebuild receipt are compared:
  agree        = same success (exit_code == 0) or same failure
  agree_class  = same success, or both failed with the same failure_class
A10 rule, fixed before any rebuild: PASS when agree >= 95 of 100, else REBUILD-ALL (all 1,338 rev-2e Go
receipts are rebuilt under rev 2g or later and the rebuilds become the rows of record).

Usage: python -B qa/agreement.py ORIG_DIR REBUILD_DIR [--sample qa/REBUILD_SAMPLE.jsonl] [--out F.json]
Prints "agree=N of=M agree_class=K" and then PASS or REBUILD-ALL. --out writes the JSON read by
publish/fill.py --rebuild-agreement. Exit 0 PASS, 10 REBUILD-ALL, 2 bad input (missing receipt, sample not 100).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
THRESHOLD, N = 95, 100


def index(d: Path):
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


def ok(r):
    return type(r.get("exit_code")) is int and r["exit_code"] == 0


def compare(sample_rows, orig, reb):
    agree = agree_class = 0
    for row in sample_rows:
        k = (row["commit"], row["snapshot"])
        for name, idx in (("original", orig), ("rebuild", reb)):
            if k not in idx:
                raise SystemExit(f"{k}: no {name} receipt")
        a, b = orig[k], reb[k]
        same = ok(a) == ok(b)
        agree += same
        agree_class += same and (
            ok(a) or a.get("failure_class") == b.get("failure_class")
        )
    return agree, agree_class


def verdict(agree, of):
    return "PASS" if of == N and agree >= THRESHOLD else "REBUILD-ALL"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("orig_dir")
    ap.add_argument("rebuild_dir")
    ap.add_argument("--sample", default=str(STUDY / "qa" / "REBUILD_SAMPLE.jsonl"))
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        rows = [
            json.loads(x)
            for x in Path(a.sample).read_text(encoding="utf-8").splitlines()
            if x.strip()
        ]
        if len(rows) != N:
            raise SystemExit(f"sample has {len(rows)} rows, want {N}")
        ag, agc = compare(rows, index(Path(a.orig_dir)), index(Path(a.rebuild_dir)))
    except SystemExit as e:
        print(f"ERROR: {e.code}", file=sys.stderr)
        return 2
    v = verdict(ag, len(rows))
    if a.out:
        Path(a.out).write_text(
            json.dumps({"agree": ag, "of": len(rows), "agree_class": agc, "verdict": v})
            + "\n",
            encoding="utf-8",
        )
    print(f"agree={ag} of={len(rows)} agree_class={agc}")
    print(v)
    return 0 if v == "PASS" else 10


if __name__ == "__main__":
    sys.exit(main())
