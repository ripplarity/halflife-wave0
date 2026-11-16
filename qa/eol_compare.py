"""A22 + A23 comparison: wave-0 build success against the declared runtime floor's end-of-life status.

READS OUTCOMES (exit_code, failure_class). It refuses to run unless --after-fit is given AND the fit output exists
(exit 3), like qa/a13_secondary.py.

Usage:
  python -B qa/eol_compare.py qa/EOL_EXPOSURE.jsonl OUT/core_record --after-fit --fit publish/_core/fit.json --out qa/A22_EOL.json
Exit 0 written; 2 bad input (an exposure row without a receipt, or a receipt without an exposure row); 3 refused.

Fixed by A22/A23 (NOTARY blocks 18 and 20):
- Groups: NOT-EXPOSED (group 1) vs EXPOSED (group 0); outcome success = exit_code == 0.
- Excluded from every comparison: failure_class TOOLCHAIN-EOL (counted, split by exposure status).
- Verdict statistic, NOW rows (A23), per ecosystem python/node/go: Mantel-Haenszel risk difference
  (success share NOT-EXPOSED minus EXPOSED) stratified by cohort year (the year in `cell`), Sato 95% interval.
  Strata with an empty arm drop out and are counted. Powered = >= 20 in each arm over the contributing strata.
- Verdict: TRACKS if >= 2 powered ecosystems have RD >= 0.10 with lower bound > 0; DOES NOT TRACK if >= 2 are
  powered and every powered one has upper bound < 0.10; fewer than 2 powered = UNDERPOWERED; else INCONCLUSIVE.
- Descriptive, for ERA and NOW separately: the same statistic (ERA labelled per its power flag), unstratified RD with
  a Newcombe hybrid-score interval, the success share of EXPOSED rows (Clopper-Pearson), and the sensitivity and
  specificity of "EXPOSED predicts failure" among compared rows (Clopper-Pearson). Also the share of failures that
  are EXPOSED, over all failures of the snapshot in python/node/go (excluding TOOLCHAIN-EOL), Clopper-Pearson.
Wording: "builds whose declared runtime floor was past end-of-life", never "failed because of end-of-life".
"""

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

from scipy.stats import beta

STUDY = Path(__file__).resolve().parent.parent
Z = 1.959963984540054
ECOS = ("python", "node", "go")
EXCLUDED_CLASS = "TOOLCHAIN-EOL"
MIN_ARM = 20
THRESH = 0.10


def key_of(r):
    return (r["repo"].rstrip("/").removesuffix(".git"), r["commit"], r["snapshot"])


def success(rec):
    return type(rec.get("exit_code")) is int and rec["exit_code"] == 0


def year_of(cell):
    m = re.search(r"(\d{4})", cell or "")
    return int(m.group(1)) if m else None


# ---------- statistics ----------
def clopper_pearson(k, n):
    if n == 0:
        return None
    lo = 0.0 if k == 0 else float(beta.ppf(0.025, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(0.975, k + 1, n - k))
    return {"k": k, "n": n, "p": k / n, "lo": lo, "hi": hi}


def wilson(k, n):
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return c - h, c + h


def newcombe(a, n1, c, n0):
    """Difference p1 - p0 with Newcombe's hybrid score interval (method 10)."""
    if n1 == 0 or n0 == 0:
        return None
    p1, p0 = a / n1, c / n0
    l1, u1 = wilson(a, n1)
    l0, u0 = wilson(c, n0)
    d = p1 - p0
    lo = d - math.sqrt((p1 - l1) ** 2 + (u0 - p0) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p0 - l0) ** 2)
    return {"rd": d, "lo": lo, "hi": hi}


def mh_sato(strata):
    """strata: list of (a, n1, c, n0): successes/size in group 1 (NOT-EXPOSED) and group 0 (EXPOSED).
    Returns MH risk difference with the Sato (1989) variance, or None if no stratum has both arms."""
    use = [s for s in strata if s[1] > 0 and s[3] > 0]
    if not use:
        return None
    W = num = P = Q = 0.0
    for a, n1, c, n0 in use:
        N = n1 + n0
        W += n1 * n0 / N
        num += (a * n0 - c * n1) / N
        P += (n1 * n1 * c - n0 * n0 * a + n1 * n0 * (n0 - n1) / 2) / (N * N)
        Q += (a * (n0 - c) + c * (n1 - a)) / (2 * N)
    rd = num / W
    var = (rd * P + Q) / (W * W)
    se = math.sqrt(max(var, 0.0))
    return {"rd": rd, "se": se, "lo": rd - Z * se, "hi": rd + Z * se}


# ---------- assembly ----------
def index_receipts(d):
    out = {}
    for e in os.scandir(d):
        if e.name.endswith(".json"):
            r = json.load(open(e.path, encoding="utf-8"))
            if isinstance(r, dict) and "commit" in r:
                out[key_of(r)] = r
    return out


def analyse_snapshot(rows):
    """rows: list of dicts with ecosystem, status, year, ok, cls (one snapshot)."""
    res = {"ecosystems": {}}
    fail_all = fail_exp = 0
    for eco in ECOS:
        er = [r for r in rows if r["ecosystem"] == eco]
        excl = {"EXPOSED": 0, "NOT-EXPOSED": 0, "other": 0}
        comp = []
        for r in er:
            if r["cls"] == EXCLUDED_CLASS:
                excl[
                    r["status"]
                    if r["status"] in ("EXPOSED", "NOT-EXPOSED")
                    else "other"
                ] += 1
                continue
            if not r["ok"]:
                fail_all += 1
                fail_exp += r["status"] == "EXPOSED"
            if r["status"] in ("EXPOSED", "NOT-EXPOSED"):
                comp.append(r)
        years = sorted({r["year"] for r in comp})
        strata, dropped = [], []
        for y in years:
            g1 = [r for r in comp if r["year"] == y and r["status"] == "NOT-EXPOSED"]
            g0 = [r for r in comp if r["year"] == y and r["status"] == "EXPOSED"]
            if g1 and g0:
                strata.append(
                    (
                        sum(r["ok"] for r in g1),
                        len(g1),
                        sum(r["ok"] for r in g0),
                        len(g0),
                    )
                )
            else:
                dropped.append(y)
        n1 = sum(s[1] for s in strata)
        n0 = sum(s[3] for s in strata)
        g1 = [r for r in comp if r["status"] == "NOT-EXPOSED"]
        g0 = [r for r in comp if r["status"] == "EXPOSED"]
        fails = [r for r in comp if not r["ok"]]
        succ = [r for r in comp if r["ok"]]
        res["ecosystems"][eco] = {
            "status_counts": {
                s: sum(r["status"] == s for r in er)
                for s in sorted({r["status"] for r in er})
            },
            "excluded_toolchain_eol": excl,
            "mh": mh_sato(strata),
            "strata_used": len(strata),
            "strata_dropped": dropped,
            "arm_n_contributing": {"not_exposed": n1, "exposed": n0},
            "powered": n1 >= MIN_ARM and n0 >= MIN_ARM,
            "unstratified_newcombe": newcombe(
                sum(r["ok"] for r in g1), len(g1), sum(r["ok"] for r in g0), len(g0)
            ),
            "success_share_exposed": clopper_pearson(sum(r["ok"] for r in g0), len(g0)),
            "sensitivity": clopper_pearson(
                sum(r["status"] == "EXPOSED" for r in fails), len(fails)
            ),
            "specificity": clopper_pearson(
                sum(r["status"] == "NOT-EXPOSED" for r in succ), len(succ)
            ),
        }
    res["share_of_failures_exposed"] = clopper_pearson(fail_exp, fail_all)
    return res


def verdict(snap):
    pw = [e for e in snap["ecosystems"].values() if e["powered"] and e["mh"]]
    if len(pw) < 2:
        return "UNDERPOWERED"
    if sum(e["mh"]["rd"] >= THRESH and e["mh"]["lo"] > 0 for e in pw) >= 2:
        return "TRACKS"
    if all(e["mh"]["hi"] < THRESH for e in pw):
        return "DOES NOT TRACK"
    return "INCONCLUSIVE"


def compare(exposure_rows, receipts):
    exp_keys = {key_of(r): r for r in exposure_rows}
    missing = [k for k in exp_keys if k not in receipts]
    extra = [k for k in receipts if k not in exp_keys]
    if missing or extra:
        raise SystemExit(
            f"join mismatch: {len(missing)} exposure rows without receipt, {len(extra)} receipts without exposure row"
        )
    by_snap = {"ERA": [], "NOW": []}
    for k, e in exp_keys.items():
        rec = receipts[k]
        if e["ecosystem"] not in ECOS:
            continue
        by_snap.setdefault(e["snapshot"], []).append(
            {
                "ecosystem": e["ecosystem"],
                "status": e["status"],
                "year": year_of(e.get("cell")),
                "ok": success(rec),
                "cls": rec.get("failure_class"),
            }
        )
    out = {s: analyse_snapshot(v) for s, v in by_snap.items()}
    out["verdict_NOW_rows"] = verdict(out["NOW"])
    out["A22_ERA_rule"] = verdict(out["ERA"])
    out["wording"] = "builds whose declared runtime floor was past end-of-life"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("exposure")
    ap.add_argument("receipts_dir")
    ap.add_argument("--after-fit", action="store_true")
    ap.add_argument("--fit", default=str(STUDY / "publish" / "_core" / "fit.json"))
    ap.add_argument("--out", default=str(STUDY / "qa" / "A22_EOL.json"))
    a = ap.parse_args(argv)
    if not a.after_fit or not Path(a.fit).is_file():
        print(
            "refused: A22 comparison reads outcomes; it runs only after the single fit (--after-fit and an existing fit output)",
            file=sys.stderr,
        )
        return 3
    rows = [
        json.loads(x)
        for x in Path(a.exposure).read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    try:
        res = compare(rows, index_receipts(a.receipts_dir))
    except SystemExit as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    Path(a.out).write_text(
        json.dumps(res, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )
    print(
        f"verdict_NOW_rows={res['verdict_NOW_rows']} A22_ERA_rule={res['A22_ERA_rule']} out={a.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
