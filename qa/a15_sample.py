"""HALF-LIFE A15 check 1: draw the per-revision rebuild-agreement sample, build nothing.

A15 wording: for each of the recipe ids v2g, v2i and v2j, the valid receipts are sorted by
sha256("A15|" + receipt file name) ascending and the first 60 are taken (all, if fewer than 60).

Reads ONLY each receipt's file name and its recipe_id (no outcome field). "Valid" here means: the file
parses as a JSON object with a string recipe_id, and its name is not on any --void list (TSV/text, first
column = receipt file name). NO-MANIFEST filtering is left to the rebuild step (it needs failure_class).

Refuses (exit 3) while a CORE/FULL job is live, unless --dry (which prints and writes nothing).
Usage: python -B qa/a15_sample.py [--receipts OUT/core] [--void F ...] [--out qa/A15_SAMPLE.jsonl] [--dry]
Exit 0 ok, 3 core job live.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
REVISIONS = ("v2g", "v2i", "v2j")
N = 60


def key(name: str) -> str:
    return hashlib.sha256(("A15|" + name).encode("utf-8")).hexdigest()


def revision_of(recipe_id: str):
    for r in REVISIONS:
        if recipe_id == r or recipe_id.endswith("-" + r):
            return r
    return None


def read_void(paths):
    out = set()
    for p in paths or []:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            c = line.split("\t")[0].strip()
            if c and not c.startswith("#"):
                out.add(Path(c).name)
    return out


def recipe_id(p: Path):
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(r, dict):
        return None
    v = r.get("recipe_id")
    return v if isinstance(v, str) else None


def draw(rdir: Path, void=frozenset(), n=N):
    by = {r: [] for r in REVISIONS}
    for p in rdir.glob("*.json"):
        if p.name in void:
            continue
        rid = recipe_id(p)
        rev = revision_of(rid) if rid else None
        if rev:
            by[rev].append(p.name)
    return {r: sorted(names, key=key)[:n] for r, names in by.items()}


def core_live():
    sys.path.insert(0, str(STUDY / "qa"))
    from standby_audit import live_jobs

    return live_jobs()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipts", default=str(STUDY / "OUT" / "core"))
    ap.add_argument("--void", action="append", default=[])
    ap.add_argument("--out", default=str(STUDY / "qa" / "A15_SAMPLE.jsonl"))
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    if not a.dry:
        live = core_live()
        if live:
            print(
                "refused: live job(s) " + ", ".join(live) + " (use --dry)",
                file=sys.stderr,
            )
            return 3
    s = draw(Path(a.receipts), read_void(a.void))
    rows = [
        {"revision": r, "rank": i, "receipt": nm}
        for r in REVISIONS
        for i, nm in enumerate(s[r])
    ]
    for r in REVISIONS:
        print(f"{r}: {len(s[r])}")
    if not a.dry:
        Path(a.out).write_text(
            "".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
