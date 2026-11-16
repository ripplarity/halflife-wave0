"""EXPLORATORY, post-hoc (after the fit): H3 rows (NOW, cohorts 2023-2024, marker key present, NO-MANIFEST
excluded as in fit.py) by ecosystem and by pnpm-defect row. Defect row = a FARM-STEP line runs pnpm, and the log
has "pnpm: not found", "yarn: not found", "cannot find binary path" or a corepack error (EXPLORATORY_age_patterns.md).
Usage: python -B publish/exploratory/h3_composition.py > publish/exploratory/h3_composition.txt"""

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REC = ROOT / "OUT" / "core_record"
DEFECT = re.compile(
    r"pnpm: not found|yarn: not found|cannot find binary path|corepack[^\n]*(error|Error)"
)
year = {
    r["html_url"]: int(r["year"])
    for r in map(json.loads, open(ROOT / "FROZEN_LIST.jsonl", encoding="utf-8"))
}
mk = {
    (m["repo"], m["now_sha"]): m["ai_marker"]
    for m in map(
        json.loads, open(ROOT / "markers" / "ai_marker.jsonl", encoding="utf-8")
    )
    if m.get("ai_marker") in (True, False)
}


def pm_defect(log):
    if not log.exists():
        return False, False
    t = log.read_text(encoding="utf-8", errors="replace")
    pnpm = any("pnpm" in ln for ln in t.splitlines() if ln.startswith("FARM-STEP:"))
    return pnpm, pnpm and bool(DEFECT.search(t))


tab = defaultdict(lambda: [0, 0])
check = defaultdict(int)
for p in sorted(REC.glob("*.json")):
    r = json.loads(p.read_text(encoding="utf-8"))
    pnpm, dfc = pm_defect(p.with_suffix(".log"))
    if dfc:
        check[r["snapshot"]] += 1
    if (
        r["snapshot"] != "NOW"
        or r.get("failure_class") == "NO-MANIFEST"
        or year.get(r["repo"]) not in (2023, 2024)
    ):
        continue
    m = mk.get((r["repo"], r["commit"]))
    if m is None:
        continue
    g = "marker" if m else "other"
    ok = int(r["exit_code"]) == 0
    for key in (
        ("all", g),
        ("eco=" + r["ecosystem"], g),
        ("pnpm_defect=" + ("yes" if dfc else "no"), g),
        ("node_pnpm=" + ("yes" if pnpm and r["ecosystem"] == "node" else "no"), g),
    ):
        tab[key][0] += ok
        tab[key][1] += 1

print(
    "# EXPLORATORY post-hoc; H3 rows (NOW, cohorts 2023-2024, marker key present); built/attempted"
)
print(
    f"# check: pnpm-defect rows in all receipts ERA {check['ERA']} NOW {check['NOW']}"
)
for k in sorted({k for k, _ in tab}):
    cells = "  ".join(
        f"{g} {tab[(k, g)][0]}/{tab[(k, g)][1]}" for g in ("marker", "other")
    )
    print(f"{k:18s} {cells}")
