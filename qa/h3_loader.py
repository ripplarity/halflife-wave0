"""HALF-LIFE H3 pre-step (markers/JOIN_NOTES.md "Smallest loader change"); fit.py is not edited.

Writes an enriched JSONL that analysis/fit.py reads unchanged:
  - year: from FROZEN_LIST.jsonl by html_url == receipt.repo (every row; H1/H2 need it too).
  - ai_marker: from markers/ai_marker.jsonl keyed on (repo, now_sha) == (receipt.repo, receipt.commit),
    attached only to NOW receipts and only when ai_marker is true/false. Null or sha mismatch = key absent.
Prints counts of the join only (rows, rows without year, 2023-2024 NOW rows with/without a marker key).
Never prints or tabulates outcomes.

Usage: python qa/h3_loader.py RECEIPTS_DIR_OR_JSONL OUT.jsonl [--frozen FROZEN_LIST.jsonl]
       [--markers markers/ai_marker.jsonl]
Then:  python analysis/fit.py OUT.jsonl --asof 2026
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(ln) for ln in fh if ln.strip()]


def load_receipts(src: Path):
    if src.is_dir():
        out = []
        for p in sorted(src.glob("*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict) and "repo" in d and "snapshot" in d:
                out.append(d)
        return out
    return jsonl(src)


def enrich(receipts, frozen, markers):
    year = {r["html_url"]: int(r["year"]) for r in frozen}
    mk = {(m["repo"], m["now_sha"]): m["ai_marker"] for m in markers}
    stats = {
        "rows": 0,
        "no_year": 0,
        "h3_now_rows": 0,
        "h3_with_marker": 0,
        "h3_dropped_null_or_missing": 0,
    }
    out = []
    for r in receipts:
        r = dict(r)
        r.pop("ai_marker", None)  # only the join may set it
        stats["rows"] += 1
        y = year.get(r["repo"])
        if y is None:
            stats["no_year"] += 1
            continue  # fit.py would crash on int(None); such a row is not in the frozen study
        r["year"] = y
        if r.get("snapshot") == "NOW":
            v = mk.get((r["repo"], r.get("commit")))
            if y in (2023, 2024):
                stats["h3_now_rows"] += 1
                if isinstance(v, bool):
                    stats["h3_with_marker"] += 1
                else:
                    stats["h3_dropped_null_or_missing"] += 1
            if isinstance(v, bool):
                r["ai_marker"] = v
        out.append(r)
    return out, stats


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("receipts")
    ap.add_argument("out")
    ap.add_argument("--frozen", default=str(ROOT / "FROZEN_LIST.jsonl"))
    ap.add_argument("--markers", default=str(ROOT / "markers" / "ai_marker.jsonl"))
    a = ap.parse_args(argv)
    rows, st = enrich(
        load_receipts(Path(a.receipts)), jsonl(a.frozen), jsonl(a.markers)
    )
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    print(" ".join(f"{k}={v}" for k, v in st.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
