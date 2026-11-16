"""A22 exposure tool: declared runtime floor per CORE_LIST row versus the frozen endoflife.date calendar.

Outcome-blind by construction: reads ONLY core/CORE_LIST.jsonl (repo, commit, snapshot, ecosystem, build_dir)
and repository files at that commit via public GET of raw.githubusercontent.com (no token, no auth header).
It never opens a receipt or a log.

Usage:
  python -B qa/eol_exposure.py core/CORE_LIST.jsonl --calendar qa/eol_calendar --out qa/EOL_EXPOSURE.jsonl
Exit 0 on completion. Prints counts by ecosystem x status and out=... sha256=....

Status per row: EXPOSED | NOT-EXPOSED | BOUNDARY | UNDECLARED | UNFETCHED | N/A (rust).
Reference window: wave 0 ran 2026-11-09..2026-11-12. EXPOSED = cycle EOL date < 2026-11-09, or the calendar marks
the cycle isEol with no date, or the declared version is older than the oldest calendar cycle and that cycle is
EXPOSED. NOT-EXPOSED = EOL date > 2026-11-12 or not yet set (isEol false). EOL inside the window, or a version
newer than every calendar cycle = BOUNDARY.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import tomllib
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version

REF_START, REF_END = "2026-11-09", "2026-11-12"
PRODUCT = {"python": "python", "node": "nodejs", "go": "go"}
RETRY_S = 600


def vkey(name):
    return tuple(int(x) for x in name.split("."))


def load_calendar(d):
    cal = {}
    for eco, prod in PRODUCT.items():
        rel = json.load(open(os.path.join(d, prod + ".json"), encoding="utf-8"))[
            "result"
        ]["releases"]
        cyc = {}
        for r in rel:
            if re.fullmatch(r"\d+(\.\d+)?", r["name"]):
                cyc[vkey(r["name"])] = (r.get("eolFrom"), bool(r.get("isEol")))
        cal[eco] = dict(sorted(cyc.items()))
    return cal


def classify_cycle(cal, eco, key):
    """key: tuple (major,) for node, (major, minor) for python/go."""
    cyc = cal[eco]
    if key in cyc:
        eol, is_eol = cyc[key]
        if eol is None:
            return "EXPOSED" if is_eol else "NOT-EXPOSED"
        if eol < REF_START:
            return "EXPOSED"
        if eol > REF_END:
            return "NOT-EXPOSED"
        return "BOUNDARY"
    keys = list(cyc)
    if keys and key < keys[0] and classify_cycle(cal, eco, keys[0]) == "EXPOSED":
        return "EXPOSED"
    return "BOUNDARY"


# ---------- parse rules (frozen) ----------
def python_floor(pyver_text, requires_python, cal):
    """Returns (major, minor) or None (UNDECLARED)."""
    if pyver_text is not None:
        first = pyver_text.splitlines()[0].strip() if pyver_text.strip() else ""
        m = re.match(r"^(?:python-?|cpython-?)?(\d+)\.(\d+)", first)
        if m:
            return (int(m.group(1)), int(m.group(2)))
    if requires_python:
        try:
            ss = SpecifierSet(requires_python.strip())
        except InvalidSpecifier:
            return None
        lower = [s for s in ss if s.operator in (">=", ">", "==", "~=", "===")]
        if not lower:
            return None
        if all(s.operator in (">=", ">") and "." not in s.version for s in lower):
            return None  # only a major bound such as >=3
        for key in cal["python"]:
            if len(key) != 2:
                continue
            if any(
                ss.contains(Version(f"{key[0]}.{key[1]}.{p}"), prereleases=False)
                for p in (0, 99)
            ):
                return key
    return None


_NPM_PART = re.compile(r"^(\d+|[xX*])(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?")


def _npm_lower_major(comp):
    """Lower-bound major implied by one comparator, or None if it sets no lower bound."""
    comp = comp.strip().lstrip("v=").strip()
    m = re.match(r"^(\^|~|>=|>|<=|<|=)?\s*v?(.*)$", comp)
    op, ver = m.group(1) or "", m.group(2).strip()
    pm = _NPM_PART.match(ver)
    if op in ("<", "<="):
        return None
    if not pm or pm.group(1) in ("x", "X", "*"):
        return None
    major = int(pm.group(1))
    if op == ">":
        rest = [
            g for g in pm.groups()[1:] if g is not None and g not in ("x", "X", "*")
        ]
        return major + 1 if not rest else major
    return major


def node_floor(engines_node, cal):
    """Returns (major,) or None (UNDECLARED)."""
    if engines_node is None:
        return None
    rng = str(engines_node).strip()
    if rng in ("", "*", "x", "X", "latest"):
        return None
    lows = []
    for alt in rng.split("||"):
        alt = alt.strip()
        if alt in ("", "*", "x", "X"):
            return None
        hy = re.match(r"^(\S+)\s+-\s+(\S+)$", alt)
        comps = (
            [hy.group(1)]
            if hy
            else re.findall(r"(?:[<>]=?|[\^~=])?\s*v?[\dxX*][\w.*]*", alt)
        )
        alt_low = [l for l in (_npm_lower_major(c) for c in comps) if l is not None]
        if not alt_low:
            return None
        lows.append(max(alt_low))
    low = min(lows)
    for key in cal["node"]:
        if key[0] >= low:
            return key
    return (low,)


def go_floor(gomod_text):
    if gomod_text is None:
        return None
    m = re.search(r"(?m)^go\s+(\d+)\.(\d+)", gomod_text)
    return (int(m.group(1)), int(m.group(2))) if m else None


# ---------- fetch ----------
def owner_repo(url):
    m = re.match(r"https?://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$", url)
    return (m.group(1), m.group(2)) if m else None


def fetch(owner, repo, commit, path, sleep=time.sleep):
    """Returns text, None for 404 (file absent), or raises RuntimeError after two failed tries."""
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit}/{urllib.parse.quote(path, safe='/')}"
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "halflife-research"}
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        if attempt == 1:
            sleep(RETRY_S)
    raise RuntimeError("unfetched")


def exposure_row(row, cal, get):
    eco = row["ecosystem"]
    out = {k: row.get(k) for k in ("repo", "commit", "snapshot", "ecosystem", "cell")}
    if eco == "rust":
        out.update(status="N/A", declared=None)
        return out
    orr = owner_repo(row["repo"])
    base = (row.get("build_dir") or ".").strip("./")
    p = lambda f: f"{base}/{f}" if base else f
    try:
        if eco == "python":
            pv = get(*orr, row["commit"], p(".python-version"))
            rp = None
            if pv is None:
                pp = get(*orr, row["commit"], p("pyproject.toml"))
                if pp is not None:
                    try:
                        rp = tomllib.loads(pp).get("project", {}).get("requires-python")
                    except tomllib.TOMLDecodeError:
                        rp = None
            key = python_floor(pv, rp, cal)
        elif eco == "node":
            pj = get(*orr, row["commit"], p("package.json"))
            eng = None
            if pj is not None:
                try:
                    eng = (json.loads(pj).get("engines") or {}).get("node")
                except (json.JSONDecodeError, AttributeError):
                    eng = None
            key = node_floor(eng, cal)
        elif eco == "go":
            key = go_floor(get(*orr, row["commit"], p("go.mod")))
        else:
            out.update(status="N/A", declared=None)
            return out
    except RuntimeError:
        out.update(status="UNFETCHED", declared=None)
        return out
    if key is None:
        out.update(status="UNDECLARED", declared=None)
    else:
        out.update(
            status=classify_cycle(cal, eco, key), declared=".".join(map(str, key))
        )
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("core_list")
    ap.add_argument("--calendar", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if os.path.basename(a.core_list) != "CORE_LIST.jsonl":
        print(
            "refusing: input must be core/CORE_LIST.jsonl (no receipts)",
            file=sys.stderr,
        )
        return 2
    cal = load_calendar(a.calendar)
    rows = [json.loads(l) for l in open(a.core_list, encoding="utf-8") if l.strip()]
    counts = {}
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            e = exposure_row(r, cal, fetch)
            counts[(e["ecosystem"], e["status"])] = (
                counts.get((e["ecosystem"], e["status"]), 0) + 1
            )
            f.write(json.dumps(e, sort_keys=True) + "\n")
    for k in sorted(counts):
        print(f"{k[0]} {k[1]} {counts[k]}")
    print(f"out={a.out} sha256={hashlib.sha256(open(a.out, 'rb').read()).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
