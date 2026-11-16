"""HALF-LIFE rebuild reasons per cell (A12/A16/A17 farm figure): why each receipt of the rebuild list was selected.

Uses the same tests as the pinned selector qa/timeout_rebuild.py is_selected (A12 TIMEOUT; A16 NETWORK or the A16
log pattern; A17 the literal "Proxy CONNECT aborted", case-insensitive), applied in that order: a receipt selected
for more than one reason counts once, under the first. Cell = the frozen CORE_LIST row's "cell".
Reads from receipts ONLY failure_class (TIMEOUT/NETWORK test, as the selector does) and the log text; prints only the
output path and sha256. Run after step 4 (the rebuild list exists); its numbers are a farm figure, not an outcome.

Usage: python -B qa/rebuild_reasons.py [--receipts OUT/core] [--core-list core/CORE_LIST.jsonl] [--out qa/REBUILD_REASONS.json]
Writes {"cells": {cell: {"timeout": a, "network_429": b, "proxy_msg": c}}}, the input of publish/fill.py --rebuild-reasons.
Exit 0 written; 2 a selected receipt has no CORE_LIST row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import timeout_rebuild as tr

STUDY = Path(__file__).resolve().parents[1]


def reason(r: dict, log: Path):
    if not tr.is_selected(r, log):
        return None
    if r.get("failure_class") == "TIMEOUT":
        return "timeout"
    try:
        txt = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        txt = ""
    if r.get("failure_class") == "NETWORK" or tr.A16_RE.search(txt):
        return "network_429"
    return "proxy_msg"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipts", default=str(STUDY / "OUT" / "core"))
    ap.add_argument("--core-list", default=str(STUDY / "core" / "CORE_LIST.jsonl"))
    ap.add_argument("--out", default=str(STUDY / "qa" / "REBUILD_REASONS.json"))
    a = ap.parse_args(argv)
    cell_of = {}
    for line in Path(a.core_list).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            cell_of[(row["commit"], row["snapshot"])] = row.get("cell")
    cells = {
        c: {"timeout": 0, "network_429": 0, "proxy_msg": 0}
        for c in sorted(set(cell_of.values()) - {None})
    }
    for p in sorted(Path(a.receipts).glob("*.json"), key=lambda x: x.name):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(r, dict):
            continue
        why = reason(r, p.with_suffix(".log"))
        if why is None:
            continue
        c = cell_of.get((r.get("commit"), r.get("snapshot")))
        if c is None:
            print(f"error: no CORE_LIST row for {p.name}", file=sys.stderr)
            return 2
        cells[c][why] += 1
    data = (json.dumps({"cells": cells}, sort_keys=True) + "\n").encode("utf-8")
    Path(a.out).write_bytes(data)
    print(f"out={a.out} sha256={hashlib.sha256(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
