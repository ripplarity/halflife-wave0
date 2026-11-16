"""Fill paper.md placeholders from analysis/fit.py JSON + a receipts dir (+ optional dataset dir).

Usage: python fill.py FIT_JSON RECEIPTS_DIR OUT_MD [--template paper.md] [--dataset DIR] [--allow AUTHOR]
Title and abstract are verdict-conditional: paper.md carries one pre-written block per H1 verdict
(<!-- IF H1 supported|not_supported|inconclusive -->), and h1_overall() picks it from the fit JSON.
Exit 0: every placeholder except the allowed ones ({{AUTHOR}}, {{REPO_URL}}) was filled, every supplied value was used,
        and every leaf of the fit JSON was consumed.
Exit 2: an unfilled placeholder, an unused supplied value, or an unconsumed fit leaf (each listed on stderr).
No result number is typed by hand anywhere in the paper: all come from here.
"""

from __future__ import annotations

import argparse
import base64
import glob
import hashlib
import json
import math
import os
import re
import statistics
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
ECOS = ("python", "node", "go", "rust")
PH = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")
OOM_CAP = 8 * 1024**3
MIB = 1024**2


def flatten(o, prefix=""):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
        return out
    if isinstance(o, list):
        out = {}
        for i, v in enumerate(o):
            out.update(flatten(v, f"{prefix}[{i}]"))
        return out
    return {prefix: o}


class Fit:
    """Wraps the fit JSON; every read marks the leaf consumed."""

    def __init__(self, d):
        self.d = d
        self.leaves = flatten(d)
        self.used = set()

    def get(self, path):
        cur = self.d
        try:
            for part in re.findall(r"[^.\[\]]+", path):
                cur = cur[int(part)] if isinstance(cur, list) else cur[part]
        except (KeyError, IndexError, TypeError, ValueError):
            raise FillError(f"fit JSON has no leaf {path} (renamed or missing)")
        for k in self.leaves:
            if k == path or k.startswith(path + ".") or k.startswith(path + "["):
                self.used.add(k)
        return cur

    def has(self, path):
        try:
            cur = self.d
            for part in re.findall(r"[^.\[\]]+", path):
                cur = cur[int(part)] if isinstance(cur, list) else cur[part]
            return True
        except (KeyError, IndexError, TypeError):
            return False


class FillError(Exception):
    """A value that must not reach the paper (NaN, missing leaf, count that disagrees with the receipts)."""


def _real(v):
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise FillError(f"not a number: {v!r}")
    try:
        f = float(v)
    except ValueError:
        raise FillError(f"not a number: {v!r}")
    if math.isnan(f):
        raise FillError("NaN in fit output")
    return f


def num(v, nd=2):
    if v is None:
        return "not identifiable"
    f = _real(v)
    if f == math.inf:
        return NO_DECAY
    if math.isinf(f):
        raise FillError(f"non-finite value {v!r}")
    return f"{f:.{nd}f}"


NO_DECAY = "no decay detected within the observed range"


def age_range(sba):
    ages = sorted(int(a) for a in sba)
    if not ages:
        return "no ERA rows"
    return f"observed ages {ages[0]} to {ages[-1]} years"


def halflife(T, sba):
    """Point estimate with unit. A non-finite T is never printed as a number of years."""
    if T is None:
        return "not identifiable (no ERA rows)"
    f = _real(T)
    if f == math.inf:
        return f"{NO_DECAY} ({age_range(sba)})"
    if math.isinf(f):
        raise FillError(f"non-finite value {T!r}")
    return f"{f:.2f} years"


def ci_text(lo, hi, sba):
    if lo is None or hi is None:
        return "no bootstrap CI"
    a, b = _real(lo), _real(hi)
    if math.isinf(a) and a > 0:
        return f"every resample: {NO_DECAY} ({age_range(sba)})"
    if math.isinf(b) and b > 0:
        return f"{num(a)} years to no upper bound ({NO_DECAY} in the upper resamples, {age_range(sba)})"
    return f"{num(a)} to {num(b)} years"


H1_VERDICTS = ("supported", "not_supported", "inconclusive")


def h1_overall(fit):
    """PREREG H1: 'ERA build success decreases with age in EVERY ecosystem', alpha 0.0125 each.
    supported = all four tests reject; not_supported = at least one computable test does not reject;
    inconclusive = no computable test fails to reject but at least one test is not computable."""
    states = []
    for e in ECOS:
        p = fit.d["ecosystems"][e].get("h1_p_one_sided")
        if p is None:
            states.append("nc")
        else:
            states.append(
                "rej"
                if verdict(fit.d["ecosystems"][e].get("h1_verdict")) == "SUPPORTED"
                else "no"
            )
    if "no" in states:
        return "not_supported"
    if "nc" in states:
        return "inconclusive"
    return "supported"


BLOCK = re.compile(r"<!-- IF H1 ([a-z_]+) -->\n(.*?)<!-- END IF -->\n", re.DOTALL)


def select_blocks(text, which):
    """Keep the pre-written block for the fit's H1 verdict. Blocks come in adjacent groups of exactly
    three (supported, not_supported, inconclusive); anything else is refused. No block is chosen by hand."""
    if which not in H1_VERDICTS:
        raise FillError(f"H1 verdict {which!r}")
    out, pos, group, gstart = [], 0, [], None
    ms = list(BLOCK.finditer(text))

    def close():
        names = [g.group(1) for g in group]
        if sorted(names) != sorted(H1_VERDICTS):
            raise FillError(
                f"H1 block group {names} is not exactly {list(H1_VERDICTS)}"
            )
        out.append(next(g.group(2) for g in group if g.group(1) == which))

    for m in ms:
        if group and text[group[-1].end() : m.start()].strip() == "":
            group.append(m)
            continue
        if group:
            close()
            pos = group[-1].end()
        out.append(text[pos : m.start()])
        group = [m]
    if group:
        close()
        pos = group[-1].end()
    out.append(text[pos:])
    res = "".join(out)
    if "<!-- IF" in res or "END IF" in res:
        raise FillError("malformed H1 block marker")
    return res


def pval(v):
    if v is None:
        return "not computable"
    v = _real(v)
    if not 0.0 <= v <= 1.0:
        raise FillError(f"p-value {v!r} outside [0, 1]")
    return f"{v:.2e}" if v < 0.001 else f"{v:.3f}"


def verdict(v, yes="SUPPORTED", no="NOT SUPPORTED"):
    if v is None:
        return "NOT COMPUTABLE"
    if v in (True, "True", "true"):
        return yes
    if v in (False, "False", "false"):
        return no
    raise FillError(f"verdict {v!r} is not a boolean")


def count(v):
    if type(v) is not int or v < 0:
        raise FillError(f"count {v!r} is not a non-negative int")
    return v


def pct(a, b):
    a, b = count(a), count(b)
    if a > b:
        raise FillError(f"{a} successes out of {b}")
    return f"{a}/{b} = {100.0 * a / b:.1f}%" if b else f"{a}/0"


def load_receipts(d):
    rows = []
    for p in sorted(glob.glob(os.path.join(d, "*.json"))):
        with open(p, encoding="utf-8") as f:
            rows.append(json.load(f))
        if rows[-1].get("recipe_id") in ("halflife-recipe-v2f", "halflife-recipe-v2h"):
            raise SystemExit(
                f"{os.path.basename(p)}: {rows[-1]['recipe_id']} receipts are all void (A10, A14); not a row of record"
            )
    if not rows:
        raise SystemExit(f"no *.json receipts in {d}")
    return rows


def fit_values(fit):
    v = {}
    v["asof"] = str(fit.get("asof"))
    v["fit_rows"] = str(fit.get("rows"))
    v["fit_no_manifest_excluded"] = str(fit.get("no_manifest_excluded"))
    lines = [
        "| ecosystem | n (ERA) | H1 z | H1 p = P(Z <= z) | H1 verdict (alpha 0.0125) | half-life T | bootstrap 95% CI |",
        "|---|---|---|---|---|---|---|",
    ]
    age_lines = ["| ecosystem | age (years) | built / attempted |", "|---|---|---|"]
    for e in ECOS:
        b = f"ecosystems.{e}"
        n = fit.get(f"{b}.n_era")
        z = fit.get(f"{b}.h1_trend_z")
        p = fit.get(f"{b}.h1_p_one_sided")
        h1 = fit.get(f"{b}.h1_verdict")
        T = fit.get(f"{b}.h2_halflife_years")
        lo, hi = fit.get(f"{b}.h2_ci95")
        sba = fit.get(f"{b}.success_by_age")
        hv1 = verdict(h1)
        if p is None:
            hv1 = "NOT COMPUTABLE"
        v[f"{e}_n_era"] = str(n)
        v[f"{e}_h1_z"] = num(z)
        v[f"{e}_h1_p"] = pval(p)
        v[f"{e}_h1_verdict"] = hv1
        v[f"{e}_T"] = halflife(T, sba)
        v[f"{e}_T_ci"] = ci_text(lo, hi, sba)
        lines.append(
            f"| {e} | {n} | {num(z)} | {pval(p)} | {hv1} | {halflife(T, sba)} | {ci_text(lo, hi, sba)} |"
        )
        for age in sorted(sba, key=int):
            age_lines.append(f"| {e} | {age} | {pct(sba[age]['ok'], sba[age]['n'])} |")
    v["table_h1_h2"] = "\n".join(lines)
    v["table_era_success_by_age"] = "\n".join(age_lines)
    hv = fit.get("h2_verdict")
    v["h2_verdict"] = verdict(hv)
    if fit.has("h2_best"):
        v["h2_best_worst"] = f"best {fit.get('h2_best')}, worst {fit.get('h2_worst')}"
    else:
        v["h2_best_worst"] = (
            "fewer than two ecosystems had a finite half-life with a CI"
        )
    t = fit.get("h3.table")
    if fit.d["h3"].get("p_two_sided") is None and not any(count(x) for x in t.values()):
        # A5 item 4: no marker rows reached the fit -> H3 is "not run", never a null result.
        fit.get("h3.p_two_sided")
        if fit.get("h3.verdict") is not None:
            raise FillError("H3 verdict present without any H3 rows")
        v["h3_table"] = (
            "H3 was not run: no AI-assist marker rows reached the fit (A5 item 4)"
        )
        v["h3_p"] = "not computed"
        v["h3_verdict"] = "NOT RUN (not a null result)"
        return v
    v["h3_table"] = (
        f"AI-marker repos built {pct(t['marker_ok'], t['marker_ok'] + t['marker_fail'])}; "
        f"others built {pct(t['other_ok'], t['other_ok'] + t['other_fail'])}"
    )
    v["h3_p"] = pval(fit.get("h3.p_two_sided"))
    v["h3_verdict"] = verdict(fit.get("h3.verdict"))
    return v


def receipt_values(rows):
    v = {}
    fails = [r for r in rows if int(r["exit_code"]) != 0]
    cls = Counter(r.get("failure_class") or "UNCLASSIFIED" for r in fails)
    nonother = sum(c for k, c in cls.items() if k not in ("OTHER", "UNCLASSIFIED"))
    v["n_builds"] = str(len(rows))
    v["n_repos"] = str(len({r["repo"].rstrip("/").lower() for r in rows}))
    v["n_failures"] = str(len(fails))
    v["kill_rule_share"] = pct(nonother, len(fails))
    v["kill_rule_verdict"] = (
        "PASS"
        if fails and nonother / len(fails) >= 0.80
        else "FAIL"
        if fails
        else "NOT COMPUTABLE (no failures)"
    )
    v["table_failure_classes"] = "\n".join(
        ["| class | failures | share |", "|---|---|---|"]
        + [
            f"| {k} | {c} | {100.0 * c / len(fails):.1f}% |"
            for k, c in sorted(cls.items(), key=lambda x: (-x[1], x[0]))
        ]
    )
    lines = ["| ecosystem | snapshot | built / attempted |", "|---|---|---|"]
    for e in ECOS:
        for s in ("ERA", "NOW"):
            sub = [
                r for r in rows if r.get("ecosystem") == e and r.get("snapshot") == s
            ]
            lines.append(
                f"| {e} | {s} | {pct(sum(1 for r in sub if int(r['exit_code']) == 0), len(sub))} |"
            )
    v["table_success_by_eco_snapshot"] = "\n".join(lines)
    v["n_oom_cap"] = str(
        sum(1 for r in fails if (r.get("mem_peak_bytes") or 0) >= OOM_CAP - MIB)
    )
    v["n_refused_host_builds"] = str(sum(1 for r in rows if r.get("refused_hosts")))
    durs = sorted(float(r.get("duration_s") or 0) for r in rows)
    v["duration_median_s"] = f"{statistics.median(durs):.0f}"
    v["duration_p95_s"] = f"{durs[int(0.95 * (len(durs) - 1))]:.0f}"
    v["duration_total_h"] = f"{sum(durs) / 3600:.1f}"
    v["recipe_ids"] = ", ".join(sorted({str(r.get("recipe_id")) for r in rows}))
    rc = {}
    for r in rows:
        rc[str(r.get("recipe_id"))] = rc.get(str(r.get("recipe_id")), 0) + 1
    v["recipe_id_counts"] = ", ".join(f"{k} {n}" for k, n in sorted(rc.items()))
    v["image_digests"] = ", ".join(sorted({str(r.get("image_digest")) for r in rows}))
    return v


def _sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_consistency(fit, rows):
    """Every count the fit reports must agree with the receipts dir it is printed next to."""
    if count(fit.d.get("rows")) != len(rows):
        raise FillError(
            f"fit rows {fit.d.get('rows')} != {len(rows)} receipts (stale fit JSON?)"
        )
    nm = sum(1 for r in rows if r.get("failure_class") == "NO-MANIFEST")
    if fit.d.get("no_manifest_excluded") != nm:
        raise FillError(
            f"fit no_manifest_excluded {fit.d.get('no_manifest_excluded')} != {nm} in receipts"
        )
    for e in ECOS:
        want = sum(
            1
            for r in rows
            if r.get("ecosystem") == e
            and r.get("snapshot") == "ERA"
            and r.get("failure_class") != "NO-MANIFEST"
        )
        eco = (fit.d.get("ecosystems") or {}).get(e) or {}
        if eco.get("n_era") != want:
            raise FillError(f"{e} n_era {eco.get('n_era')} != {want} ERA receipts")
        sba = eco.get("success_by_age") or {}
        if sum(count((c or {}).get("n")) for c in sba.values()) != want:
            raise FillError(f"{e} success_by_age counts do not sum to n_era")
        ci = eco.get("h2_ci95") or [None, None]
        if (
            ci[0] is not None
            and ci[1] is not None
            and not isinstance(ci[0], str)
            and not isinstance(ci[1], str)
            and ci[0] > ci[1]
        ):
            raise FillError(f"{e} CI lower bound above upper bound")


def dataset_values(d, rows, expect_void):
    """Values from the packaged dataset; refuses a dataset that is stale relative to the receipts dir."""
    v = {}
    man = os.path.join(d, "MANIFEST.sha256")
    v["manifest_sha256"] = _sha(man)
    listed = {}
    with open(man, encoding="utf-8") as f:
        for line in f:
            h, _, n = line.rstrip("\n").partition("  ")
            listed[n] = h
    rp = os.path.join(d, "receipts.jsonl")
    if listed.get("receipts.jsonl") != _sha(rp):
        raise FillError("dataset receipts.jsonl does not match its MANIFEST.sha256")
    with open(rp, encoding="utf-8") as f:
        ds = [json.loads(x) for x in f if x.strip()]
    key = lambda r, name: (
        name.lower(),
        r["snapshot"],
        r["commit"],
        r["exit_code"],
        r.get("log_sha256"),
    )
    a = sorted(key(r, r["repo"]) for r in ds)
    b = sorted(key(r, "/".join(r["repo"].rstrip("/").split("/")[-2:])) for r in rows)
    if a != b:
        raise FillError(
            f"dataset receipts.jsonl ({len(a)} rows) differs from the receipts dir ({len(b)} rows): stale package"
        )
    with open(os.path.join(d, "MANIFEST.sha256.dsse.json"), encoding="utf-8") as f:
        env = json.load(f)
    v["attestation_keyid"] = env["signatures"][0]["keyid"]
    pred = json.loads(base64.b64decode(env["payload"]))["predicate"]
    if pred.get("builds") != len(rows):
        raise FillError("attestation predicate builds disagrees with the receipts dir")
    parts = pred.get("void_parts") or {}
    if expect_void and not parts:
        raise FillError(
            "dataset carries no A6 void folders (package with --void-dir, or pass --no-void for a dry run)"
        )
    total = 0

    def label_of(k):
        # "standby": folder name kept from the corrected first diagnosis (A8); v2f: A10 part
        if (
            "timeout" in k
        ):  # A12: replaced TIMEOUT originals, kept and published, not void
            return "timeout_original"
        if "standby" in k:
            return "first"
        if "proxy" in k:
            if "v2h" in k:  # A14 part
                return "proxy_v2h"
            return "proxy_v2f" if "v2f" in k else "proxy"
        return "incomplete" if "incomplete" in k else None

    for k in parts:
        if label_of(k) is None:
            raise FillError(f"void part {k!r} has no known label")
    for label in (
        "first",
        "proxy",
        "proxy_v2f",
        "proxy_v2h",
        "incomplete",
        "timeout_original",
    ):
        hits = {k: p for k, p in parts.items() if label_of(k) == label}
        if len(hits) > 1:
            raise FillError(f"more than one {label} void folder: {sorted(hits)}")
        if hits:
            name, p = next(iter(hits.items()))
            vr = os.path.join(d, "void", name, "receipts.jsonl")
            with open(vr, encoding="utf-8") as f:
                nv = sum(1 for x in f if x.strip())
            if listed.get(f"void/{name}/receipts.jsonl") != _sha(vr) or nv != p.get(
                "builds"
            ):
                raise FillError(f"void folder {name} disagrees with its manifest")
            v[f"n_void_{label}"] = str(nv)
            total += nv if label != "timeout_original" else 0
            v[f"void_list_sha256_{label}"] = p.get("void_list_sha256") or "none"
        else:
            v[f"n_void_{label}"] = "0 (no such void folder in this dataset)"
            v[f"void_list_sha256_{label}"] = "none"
    v["n_void_total"] = str(total)
    return v


def agreement_values(path):
    """A8 rebuild-agreement check on 100 pre-07:07:50Z receipts: JSON {"agree": n, "of": m}, or not yet run."""
    if not path:
        return {
            "agree_n": "not yet run",
            "agree_of": "100",
            "agree_class_n": "not yet run",
            "agree_verdict": "not yet run",
        }
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    n, m = d.get("agree"), d.get("of")
    if type(n) is not int or type(m) is not int or not 0 <= n <= m or m == 0:
        raise FillError(f"{path}: agree/of must be ints with 0 <= agree <= of, of > 0")
    c = d.get("agree_class")
    if c is not None and (type(c) is not int or not 0 <= c <= n):
        raise FillError(
            f"{path}: agree_class must be an int with 0 <= agree_class <= agree"
        )
    # A10: threshold fixed before any rebuild; recomputed here, never taken from the file
    verdict = "PASS" if m == 100 and n >= 95 else "REBUILD-ALL"
    if d.get("verdict") not in (None, verdict):
        raise FillError(
            f"{path}: verdict {d.get('verdict')!r} disagrees with {n}/{m} (want {verdict})"
        )
    return {
        "agree_n": str(n),
        "agree_of": str(m),
        "agree_class_n": "not reported" if c is None else str(c),
        "agree_verdict": {
            "PASS": "PASS (95 or more of 100; the original receipts remain the rows of record)",
            "REBUILD-ALL": "REBUILD-ALL (below 95 of 100; all 1,338 were rebuilt and the rebuilds are the rows of record)",
        }[verdict],
    }


def timeout_values(path):
    """A12 TIMEOUT rebuild summary JSON {"rebuilt": n, "class_changed": k} (qa/timeout_rebuild.py), or not yet run."""
    if not path:
        return {
            "n_timeout_rebuilt": "not yet run",
            "n_timeout_class_changed": "not yet run",
        }
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    n, k = d.get("rebuilt"), d.get("class_changed")
    if type(n) is not int or type(k) is not int or not 0 <= k <= n:
        raise FillError(
            f"{path}: rebuilt/class_changed must be ints with 0 <= class_changed <= rebuilt"
        )
    return {"n_timeout_rebuilt": str(n), "n_timeout_class_changed": str(k)}


REASONS = ("timeout", "network_429", "proxy_msg")


def rebuild_reasons_values(path):
    """A12/A16/A17 rebuild reasons per cell (farm figure): JSON {"cells": {cell: {"timeout": a, "network_429": b,
    "proxy_msg": c}}} written by qa/rebuild_reasons.py. A receipt selected for more than one reason counts once, under
    the first of timeout, network_429, proxy_msg."""
    if not path:
        return {
            "n_rebuild_network_429": "not yet run",
            "n_rebuild_proxy_msg": "not yet run",
            "rebuild_reasons_table": "not yet run",
        }
    cells = (_load_obj(path).get("cells")) or {}
    if not isinstance(cells, dict) or not cells:
        raise FillError(f"{path}: cells must be a non-empty object")
    tot = Counter()
    lines = [
        "| cell | TIMEOUT (A12) | NETWORK or 429 (A16) | proxy message (A17) |",
        "|---|---|---|---|",
    ]
    for cell in sorted(cells):
        e = cells[cell]
        if not isinstance(e, dict) or any(
            type(e.get(r)) is not int or e[r] < 0 for r in REASONS
        ):
            raise FillError(f"{path}: {cell} needs non-negative ints {REASONS}")
        tot.update({r: e[r] for r in REASONS})
        lines.append(f"| {cell} | " + " | ".join(str(e[r]) for r in REASONS) + " |")
    lines.append("| all | " + " | ".join(str(tot[r]) for r in REASONS) + " |")
    return {
        "n_rebuild_network_429": str(tot["network_429"]),
        "n_rebuild_proxy_msg": str(tot["proxy_msg"]),
        "rebuild_reasons_table": "\n".join(lines),
    }


def a17_values(path):
    """A17 checks (qa/a17_checks.py --out): {"faults": [{"receipt", "verdict", ...}], "build_step_messages": n,
    "stop_windows": [...]}."""
    if not path:
        return {
            k: "not yet run"
            for k in ("a17_fetch_faults", "a17_verdict", "a17_build_step_messages")
        }
    d = _load_obj(path)
    faults, msgs, wins = (
        d.get("faults"),
        d.get("build_step_messages"),
        d.get("stop_windows"),
    )
    if (
        not isinstance(faults, list)
        or type(msgs) is not int
        or msgs < 0
        or not isinstance(wins, list)
    ):
        raise FillError(
            f"{path}: want faults list, build_step_messages int, stop_windows list"
        )
    bad = [f for f in faults if f.get("verdict") != "UPSTREAM-TRANSIENT"]
    if wins or bad:
        raise FillError(
            f"{path}: a fault is not all-hold or a 60 s stop window exists: the runbook STOPs before the fit"
        )
    return {
        "a17_fetch_faults": str(len(faults)),
        "a17_verdict": (
            "none was found"
            if not faults
            else f"all {len(faults)} met C1 to C5 and were rebuilt as upstream transients; none voided a proxy instance"
        ),
        "a17_build_step_messages": str(msgs),
    }


A18_OUTCOMES = (
    "OFF-REGISTRY",
    "NOT-APPLICABLE",
    "CHECKSUM-DB",
    "NAME-ABSENT",
    "VERSION-ABSENT",
    "YANKED",
    "PRESENT",
    "UNPROBED",
    "UNNAMED",
)


def a18_values(path, rows, frozen_path):
    """A18 secondary, descriptive (analysis/archive_probe.py probe_rows.jsonl). Primary figure: ABSENT-with-EXISTED among
    the DEP-MISSING NOW rows of P, also as a share of all NOW builds of the ecosystem and cohort year (exact 95 %
    interval). Never worded as a cause. An ecosystem whose UNNAMED rows exceed half of its DEP-MISSING rows is
    EXPLORATORY (A18 limit iv)."""
    if not path:
        return {
            k: "not yet run"
            for k in ("a18_table", "a18_primary_table", "a18_exploratory")
        }
    probe = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                probe.append(json.loads(line))
    for p in probe:
        if p.get("outcome") not in A18_OUTCOMES or p.get("snapshot") not in (
            "ERA",
            "NOW",
        ):
            raise FillError(f"{path}: bad row {p.get('receipt')}: outcome/snapshot")
    year = {}
    with open(frozen_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                year[d["full_name"].lower()] = d.get("year")

    def cohort(repo):
        return year.get("/".join(repo.rstrip("/").split("/")[-2:]).lower())

    eco_of = {"pypi": "python", "npm": "node", "go": "go", "cargo": "rust"}
    # ecosystem of a probe row: from the receipt (the pattern's ecosystem may be absent for UNNAMED rows)
    by_name = {}
    for r in rows:
        by_name.setdefault((r.get("commit"), r.get("snapshot")), r)
    rec_eco = {}
    # receipts in fill carry no file name, so the probe row's receipt name is matched through its commit + snapshot
    for p in probe:
        parts = (p.get("receipt") or "").rsplit(".json", 1)[0].split("__")
        sha = parts[2] if len(parts) >= 3 else None
        r = by_name.get((sha, p["snapshot"]))
        p["_eco"] = (r or {}).get("ecosystem") or eco_of.get(p.get("ecosystem"))
        p["_cohort"] = cohort(r["repo"]) if r else None
        rec_eco[p.get("receipt")] = p["_eco"]
    ecos = sorted(
        {p["_eco"] for p in probe if p["_eco"]} | {r.get("ecosystem") for r in rows}
    )

    def key(p):
        o = p["outcome"]
        if o in ("NAME-ABSENT", "VERSION-ABSENT"):
            return o + (" (EXISTED)" if p.get("existed") else " (not EXISTED)")
        return o

    cols = [
        "OFF-REGISTRY",
        "NOT-APPLICABLE",
        "CHECKSUM-DB",
        "NAME-ABSENT (EXISTED)",
        "NAME-ABSENT (not EXISTED)",
        "VERSION-ABSENT (EXISTED)",
        "VERSION-ABSENT (not EXISTED)",
        "YANKED",
        "PRESENT",
        "UNPROBED",
        "UNNAMED",
    ]
    t = [
        "| ecosystem | snapshot | rows of P | " + " | ".join(cols) + " |",
        "|---|---|---|" + "---|" * len(cols),
    ]
    exploratory = []
    for e in ecos:
        for snap in ("NOW", "ERA"):
            ps = [p for p in probe if p["_eco"] == e and p["snapshot"] == snap]
            c = Counter(key(p) for p in ps)
            t.append(
                f"| {e} | {snap} | {len(ps)} | "
                + " | ".join(str(c[k]) for k in cols)
                + " |"
            )
        dep_now = [
            p
            for p in probe
            if p["_eco"] == e
            and p["snapshot"] == "NOW"
            and p.get("failure_class") == "DEP-MISSING"
        ]
        if dep_now and 2 * sum(p["outcome"] == "UNNAMED" for p in dep_now) > len(
            dep_now
        ):
            exploratory.append(e)
    pt = [
        "| ecosystem | cohort | ABSENT-with-EXISTED (DEP-MISSING, NOW) | NOW builds | share (exact 95% interval) |",
        "|---|---|---|---|---|",
    ]
    now_cells = Counter(
        (r.get("ecosystem"), cohort(r["repo"]))
        for r in rows
        if r.get("snapshot") == "NOW"
    )
    for e, y in sorted(now_cells, key=lambda x: (str(x[0]), str(x[1]))):
        k = sum(
            1
            for p in probe
            if p["_eco"] == e
            and p["_cohort"] == y
            and p["snapshot"] == "NOW"
            and p.get("failure_class") == "DEP-MISSING"
            and p["outcome"] in ("NAME-ABSENT", "VERSION-ABSENT")
            and p.get("existed")
        )
        n = now_cells[(e, y)]
        lo, hi = clopper_pearson(k, n)
        tag = " (EXPLORATORY)" if e in exploratory else ""
        pt.append(
            f"| {e}{tag} | {y} | {k} | {n} | {100 * k / n:.1f}% ({100 * lo:.1f}% to {100 * hi:.1f}%) |"
        )
    return {
        "a18_table": "\n".join(t),
        "a18_primary_table": "\n".join(pt),
        "a18_exploratory": ", ".join(exploratory) if exploratory else "none",
    }


def _load_obj(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if not isinstance(d, dict):
        raise FillError(f"{path}: want a JSON object")
    return d


def alias_secondary_values(path):
    """A13 registry-alias secondary (Node): JSON {"rebuilt": n, "outcome_changed": k, "node_summary": str}."""
    if not path:
        return {
            "a13_rebuilt": "not yet run",
            "a13_outcome_changed": "not yet run",
            "a13_node_summary": "not yet run",
        }
    d = _load_obj(path)
    n, k, s = d.get("rebuilt"), d.get("outcome_changed"), d.get("node_summary")
    if type(n) is not int or type(k) is not int or not 0 <= k <= n:
        raise FillError(
            f"{path}: rebuilt/outcome_changed must be ints with 0 <= outcome_changed <= rebuilt"
        )
    if not isinstance(s, str) or not s.strip() or "{{" in s:
        raise FillError(f"{path}: node_summary must be a non-empty string")
    return {
        "a13_rebuilt": str(n),
        "a13_outcome_changed": str(k),
        "a13_node_summary": s.strip(),
    }


A15_IDS = ("v2g", "v2i", "v2j")


def a15_agreement_values(path):
    """A15 check 1: JSON {"v2g": {"agree": a, "of": m}, "v2i": {...}, "v2j": {...}}. The 95 % rule for
    v2g/v2i and the exact (Clopper-Pearson) interval for v2j are recomputed here, never read from the file."""
    if not path:
        v = {f"a15_{r}_agree": "not yet run" for r in A15_IDS}
        v.update({f"a15_{r}_verdict": "not yet run" for r in ("v2g", "v2i")})
        v["a15_v2j_ci"] = "not yet run"
        return v
    d, v = _load_obj(path), {}
    for r in A15_IDS:
        e = d.get(r) or {}
        a, m = e.get("agree"), e.get("of")
        if (
            type(a) is not int
            or type(m) is not int
            or not 0 <= a <= m
            or not 0 < m <= 60
        ):
            raise FillError(
                f"{path}: {r} agree/of must be ints with 0 <= agree <= of, 0 < of <= 60"
            )
        v[f"a15_{r}_agree"] = f"{a} of {m}"
        if r != "v2j":
            ok = 100 * a >= 95 * m
            v[f"a15_{r}_verdict"] = (
                "stands (95 % or more agree)"
                if ok
                else "REBUILD-ALL (below 95 %; every receipt of this revision was rebuilt and the rebuild is the row of record)"
            )
        else:
            lo, hi = clopper_pearson(a, m)
            v["a15_v2j_ci"] = f"{100 * lo:.1f}% to {100 * hi:.1f}%"
    return v


def clopper_pearson(k, n, alpha=0.05):
    """Exact two-sided interval by bisection on the binomial tail (stdlib only)."""
    from math import comb

    def cdf(x, p):  # P(X <= x)
        return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(x + 1))

    def solve(f):
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if f(mid):
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else solve(lambda p: 1 - cdf(k - 1, p) < alpha / 2)
    upper = 1.0 if k == n else solve(lambda p: cdf(k, p) > alpha / 2)
    return lower, upper


def a15_sensitivity_values(path):
    """A15 check 2 (analysis/sensitivity_a15.py output): {"a": {"verdict_changed": bool, "summary": str},
    "b": {"ran": bool, "verdict_changed": bool|null, "summary": str}}."""
    if not path:
        return {
            "a15_sens_a": "not yet run",
            "a15_sens_b": "not yet run",
            "a15_sens_changed": "not yet run",
        }
    d = _load_obj(path)
    out, changed = {}, []
    for k in ("a", "b"):
        e = d.get(k) or {}
        s = e.get("summary")
        if not isinstance(s, str) or not s.strip() or "{{" in s:
            raise FillError(f"{path}: {k}.summary must be a non-empty string")
        vc = e.get("verdict_changed")
        if k == "b" and e.get("ran") is False:
            vc = False
        if type(vc) is not bool:
            raise FillError(f"{path}: {k}.verdict_changed must be a bool")
        if vc:
            changed.append(k)
        out[f"a15_sens_{k}"] = s.strip()
    out["a15_sens_changed"] = (
        "no hypothesis verdict changed under either sensitivity fit"
        if not changed
        else "the verdict of at least one hypothesis changed under sensitivity fit "
        + " and ".join(f"({c})" for c in changed)
    )
    return out


def population_values(frozen_path, rows, a4_path=None):
    """Population flow (frozen list -> eligible -> built), counted from the frozen list and the receipts."""
    if not os.path.isfile(frozen_path):
        raise FillError(f"frozen list {frozen_path} not found")
    st, eligible = Counter(), set()
    with open(frozen_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            name = d["full_name"].lower()
            st[(d.get("status"), d.get("tier"))] += 1
            if d.get("status") == "OK" and d.get("tier") == "CORE":
                eligible.add(name)
    total = sum(st.values())
    by = Counter()
    for (s, t), c in st.items():
        by[s if s != "OK" else f"OK/{t}"] += c
    built = {"/".join(r["repo"].rstrip("/").split("/")[-2:]).lower() for r in rows}
    era = sum(1 for r in rows if r.get("snapshot") == "ERA")
    now = sum(1 for r in rows if r.get("snapshot") == "NOW")
    a4 = 0
    if a4_path and os.path.isfile(a4_path):
        with open(a4_path, encoding="utf-8") as f:
            a4 = sum(1 for ln in f if ln.startswith("CORE\t"))
    known = {"NO-ERA", "NO-MANIFEST", "TREE-FAILED", "OK/CORE", "OK/FULL"}
    other = sum(c for k, c in by.items() if k not in known)
    t = [
        "| stage | repositories |",
        "|---|---|",
        f"| frozen candidate list (CORE freeze, all statuses) | {total} |",
        f"| excluded: NO-ERA (no default-branch commit by the ERA date) | {by['NO-ERA']} |",
        f"| excluded: NO-MANIFEST (no manifest or legacy marker at ERA) | {by['NO-MANIFEST']} |",
        f"| excluded: TREE-FAILED (ERA tree unreadable) | {by['TREE-FAILED']} |",
        f"| beyond the CORE cut (rank or cell quota; FULL tier) | {by['OK/FULL']} |",
    ]
    if other:
        t.append(f"| other status | {other} |")
    t += [
        f"| eligible CORE | {len(eligible)} |",
        f"| built: eligible CORE with at least one analysed receipt | {len(built & eligible)} ({era} ERA and {now} NOW receipts) |",
        f"| eligible CORE without an analysed receipt | {len(eligible - built)} |",
        f"| analysed repositories outside eligible CORE | {len(built - eligible)} |",
        f"| footnote (A4): eligible CORE rows whose depth-2 tree failed but root manifest was confirmed | {a4} |",
    ]
    return {"table_population_flow": "\n".join(t)}


def full_status(full_dir, not_started):
    """A5: FULL is reported only as 'in progress, not analysed' with receipts counted by file name."""
    if full_dir and not_started:
        raise FillError("give --full-dir or --full-not-started, not both")
    if not_started:
        return "not started"
    if not full_dir:
        return None
    if not os.path.isdir(full_dir):
        raise FillError(f"--full-dir {full_dir} does not exist")
    n = sum(1 for n in os.listdir(full_dir) if n.endswith(".json"))
    return (
        f"in progress, not analysed ({n} receipts written, counted by file name only)"
    )


ALLOW = ("AUTHOR", "REPO_URL")


def fill(template_text, values, allow=ALLOW):
    used, unfilled = set(), []

    def sub(m):
        k = m.group(1)
        if k in values:
            used.add(k)
            return values[k]
        if k not in allow:
            unfilled.append(k)
        return m.group(0)

    out = PH.sub(sub, template_text)
    unused = sorted(set(values) - used)
    return out, sorted(set(unfilled)), unused


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("fit_json")
    ap.add_argument("receipts_dir")
    ap.add_argument("out_md")
    ap.add_argument("--template", default=os.path.join(HERE, "paper.md"))
    ap.add_argument(
        "--dataset",
        help="packaged dataset dir (fills manifest_sha256, attestation_keyid)",
    )
    ap.add_argument(
        "--allow",
        action="append",
        default=None,
        help="placeholder allowed to stay (default AUTHOR)",
    )
    ap.add_argument(
        "--no-void",
        action="store_true",
        help="dry run only: the dataset has no A6 void folders",
    )
    ap.add_argument(
        "--full-dir", help="FULL receipts dir; counted by file name only (A5)"
    )
    ap.add_argument("--full-not-started", action="store_true")
    ap.add_argument(
        "--rebuild-agreement",
        help='A8 rebuild-agreement result JSON {"agree": n, "of": m}; omitted -> "not yet run"',
    )
    ap.add_argument(
        "--timeout-rebuild",
        help='A12 TIMEOUT rebuild summary JSON {"rebuilt": n, "class_changed": k}; omitted -> "not yet run"',
    )
    ap.add_argument(
        "--alias-secondary",
        help="A13 registry-alias secondary JSON; omitted -> not yet run",
    )
    ap.add_argument(
        "--a15-agreement",
        help="A15 per-revision agreement JSON; omitted -> not yet run",
    )
    ap.add_argument(
        "--a15-sensitivity",
        help="A15 sensitivity JSON (analysis/sensitivity_a15.py); omitted -> not yet run",
    )
    ap.add_argument(
        "--rebuild-reasons",
        help="A12/A16/A17 rebuild reasons per cell JSON (qa/rebuild_reasons.py); omitted -> not yet run",
    )
    ap.add_argument(
        "--a17-checks",
        help="A17 C1-C5 report JSON (qa/a17_checks.py --out); omitted -> not yet run",
    )
    ap.add_argument(
        "--archive-probe",
        help="A18 probe rows (analysis/archive_probe.py probe_rows.jsonl); omitted -> not yet run",
    )
    ap.add_argument(
        "--frozen-list",
        default=os.path.join(STUDY, "FROZEN_LIST.jsonl"),
        help="frozen CORE list (population flow table)",
    )
    ap.add_argument(
        "--a4-list", default=os.path.join(STUDY, "A4_TREE_FAILED_RECLASS.tsv")
    )
    a = ap.parse_args(argv)
    # A failed run never leaves a paper behind: a stale paper from an earlier run is removed first.
    if os.path.exists(a.out_md):
        os.remove(a.out_md)
    rc = 0
    try:
        with open(a.fit_json, encoding="utf-8") as f:
            fit = Fit(json.load(f))
        rows = load_receipts(a.receipts_dir)
        for r in rows:
            if type(r.get("exit_code")) is not int:
                raise FillError(f"receipt {r.get('repo')} exit_code is not an int")
        check_consistency(fit, rows)
        values = fit_values(fit)
        for k, val in receipt_values(rows).items():
            assert k not in values, k
            values[k] = val
        if a.dataset:
            values.update(dataset_values(a.dataset, rows, not a.no_void))
        fs = full_status(a.full_dir, a.full_not_started)
        if fs is not None:
            values["full_status"] = fs
        values.update(population_values(a.frozen_list, rows, a.a4_list))
        values.update(agreement_values(a.rebuild_agreement))
        values.update(timeout_values(a.timeout_rebuild))
        values.update(alias_secondary_values(a.alias_secondary))
        values.update(a15_agreement_values(a.a15_agreement))
        values.update(a15_sensitivity_values(a.a15_sensitivity))
        values.update(rebuild_reasons_values(a.rebuild_reasons))
        values.update(a17_values(a.a17_checks))
        values.update(a18_values(a.archive_probe, rows, a.frozen_list))
        h1 = h1_overall(fit)
        values["h1_overall"] = {
            "supported": "SUPPORTED (all four ecosystem tests reject at alpha 0.0125)",
            "not_supported": "NOT SUPPORTED (at least one ecosystem test does not reject at alpha 0.0125)",
            "inconclusive": "INCONCLUSIVE (no computable test failed to reject, but at least one ecosystem test is not computable)",
        }[h1]
        with open(a.template, encoding="utf-8") as f:
            text = select_blocks(f.read(), h1)
    except FillError as e:
        print(f"ERROR value: {e}", file=sys.stderr)
        print(f"no paper written to {a.out_md}; rc=2")
        return 2
    allow = tuple(a.allow or ALLOW)
    out, unfilled, unused = fill(text, values, allow)
    unconsumed = sorted(set(fit.leaves) - fit.used)
    # anything brace-shaped left over that the strict placeholder regex did not see ({{ x }}, {{x-y}})
    stray = [
        m
        for m in re.findall(r"\{\{.*?\}\}|\{\{|\}\}", out)
        if m not in {"{{" + k + "}}" for k in allow}
    ]
    for name, items in (
        ("unfilled placeholder", unfilled),
        ("unused value", unused),
        ("unconsumed fit leaf", unconsumed),
        ("stray braces", stray),
    ):
        for it in items:
            print(f"ERROR {name}: {it}", file=sys.stderr)
            rc = 2
    if rc:
        print(f"no paper written to {a.out_md}; rc={rc}")
        return rc
    os.makedirs(os.path.dirname(os.path.abspath(a.out_md)), exist_ok=True)
    with open(a.out_md, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print(f"filled {len(values)} values into {a.out_md}; rc={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
