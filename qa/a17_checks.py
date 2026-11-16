"""HALF-LIFE A17 checks over a whole proxy instance (block 11; review_fault17/RESULT.md, verdict T). Report only.

A fetch-step proxy fault under rev 2i/2j is an UPSTREAM TRANSIENT only if ALL hold, from logs alone (reviewer's
wording):
  C1 the proxy log has an allowed row for the build's client and the fetch host in [started_utc - 30 s,
     started_utc + duration_s];
  C2 the proxy container stderr is empty since the instance started;
  C3 the instance has no other fetch-step fault within +-30 min, and at most 1 fetch-step fault per 1,000 receipts
     it served;
  C4 the proxy log has rows from at least 2 other clients within +-60 s of the fault;
  C5 no thread sample above 1,000 on the instance.
If any fails, A8 applies as written. Going-forward stop rule (A17 item 4): 3 or more receipts started within any
60 s window carry the message (any step) and no build started in that window completed its fetch step at first
attempt -> STOP.

Fetch-step fault = qa/proxy_audit.fetch_fault (pinned). A proxy instance = one proxy log file (the proxy moves its
log aside at each start, so each file holds exactly one instance); a receipt belongs to the instance whose first..last
row interval contains its started_utc. Reads from receipts ONLY recipe_id, started_utc, duration_s, client_ip and
the log's FARM-STEP lines and proxy message; prints no outcome.

Inputs the tool cannot read itself (never touch hl-proxy): --stderr FILE, the operator's capture of
`docker logs hl-proxy` stderr for the instance (absent -> C2 UNTESTED); --threads FILE, lines "<epoch> <count>"
(absent -> C5 UNTESTED, which also fails the all-hold test, so it is stated as a limit, as A17 did).

Usage: python -B qa/a17_checks.py RECEIPTS_DIR PROXY_LOG [PROXY_LOG ...] [--stderr F] [--threads F] [--out qa/A17_CHECKS.json]
Exit 0 every fault UPSTREAM-TRANSIENT and no 60 s stop window; 10 otherwise (STOP: founder queue); 2 bad input.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proxy_audit as pa

SCANNED = ("halflife-recipe-v2i", "halflife-recipe-v2j")


def epoch(s: str) -> float:
    return (
        dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
        .replace(tzinfo=dt.timezone.utc)
        .timestamp()
    )


def load_instances(paths):
    inst = []
    for p in paths:
        rows = []
        for line in Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict) and isinstance(r.get("ts"), (int, float)):
                rows.append(r)
        if rows:
            rows.sort(key=lambda r: r["ts"])
            inst.append(
                {
                    "file": str(p),
                    "first": rows[0]["ts"],
                    "last": rows[-1]["ts"],
                    "rows": rows,
                }
            )
    return inst


def fetch_host(log: Path):
    for ln in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if ln.startswith("FARM-STEP: fetch ") and len(ln.split()) > 2:
            return urlparse(ln.split()[2]).hostname
    return None


def fetch_completed(log: Path) -> bool:
    """Fetch step completed at first attempt: a later FARM-STEP line exists and the fetch step did not fault."""
    try:
        steps = [
            ln
            for ln in log.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.startswith("FARM-STEP: ")
        ]
    except OSError:
        return False
    return (
        len(steps) >= 2
        and steps[0].startswith("FARM-STEP: fetch ")
        and not pa.fetch_fault(log)
    )


def read_receipts(rdir: Path):
    out = []
    for p in sorted(rdir.glob("*.json"), key=lambda x: x.name):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            t0 = epoch(r["started_utc"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        log = p.with_suffix(".log")
        out.append(
            {
                "name": p.name,
                "recipe": r.get("recipe_id"),
                "t0": t0,
                "dur": float(r.get("duration_s") or 0),
                "client": r.get("client_ip") or "",
                "log": log,
                "fault": r.get("recipe_id") in SCANNED
                and log.is_file()
                and pa.fetch_fault(log),
                "msg": log.is_file() and pa.any_step_msg(log),
            }
        )
    return out


def instance_of(inst, t):
    for i, x in enumerate(inst):
        if x["first"] <= t <= x["last"]:
            return i
    return None


def check_fault(f, recs, inst, i, stderr_lines, threads):
    x = inst[i] if i is not None else None
    res = {}
    host = fetch_host(f["log"])
    lo, hi = f["t0"] - 30, f["t0"] + f["dur"]
    res["C1"] = bool(x) and any(
        r.get("allowed")
        and r.get("client") == f["client"]
        and r.get("host") == host
        and lo <= r["ts"] <= hi
        for r in x["rows"]
    )
    res["C2"] = None if stderr_lines is None else len(stderr_lines) == 0
    served = [r for r in recs if instance_of(inst, r["t0"]) == i] if x else []
    faults = [r for r in served if r["fault"]]
    near = [r for r in faults if r is not f and abs(r["t0"] - f["t0"]) <= 1800]
    res["C3"] = bool(x) and not near and len(faults) * 1000 <= max(len(served), 1) * 1
    others = {
        r.get("client")
        for r in (x["rows"] if x else [])
        if abs(r["ts"] - f["t0"]) <= 60 and r.get("client") != f["client"]
    }
    res["C4"] = len(others) >= 2
    if threads is None:
        res["C5"] = None
    else:
        ts = [c for t, c in threads if x and x["first"] <= t <= x["last"]]
        res["C5"] = None if not ts else all(c <= 1000 for c in ts)
    res["verdict"] = (
        "UPSTREAM-TRANSIENT"
        if all(res[c] is True for c in ("C1", "C2", "C3", "C4", "C5"))
        else "A8-APPLIES"
    )
    return res


def stop_windows(recs):
    """A17 item 4: windows [t, t+60] anchored at each message-carrying receipt's start."""
    out = []
    msg = sorted((r for r in recs if r["msg"]), key=lambda r: r["t0"])
    for a in msg:
        win = [r for r in msg if a["t0"] <= r["t0"] <= a["t0"] + 60]
        if len(win) < 3:
            continue
        started = [r for r in recs if a["t0"] <= r["t0"] <= a["t0"] + 60]
        if not any(fetch_completed(r["log"]) for r in started):
            out.append({"from": a["t0"], "receipts": [r["name"] for r in win]})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("receipts")
    ap.add_argument("proxy_logs", nargs="+")
    ap.add_argument("--stderr")
    ap.add_argument("--threads")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        inst = load_instances(a.proxy_logs)
        recs = read_receipts(Path(a.receipts))
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    stderr_lines = None
    if a.stderr:
        stderr_lines = [
            ln
            for ln in Path(a.stderr)
            .read_text(encoding="utf-8", errors="replace")
            .splitlines()
            if ln.strip()
        ]
    threads = None
    if a.threads:
        threads = []
        for ln in Path(a.threads).read_text(encoding="utf-8").splitlines():
            p = ln.split()
            if len(p) >= 2:
                threads.append((float(p[0]), int(p[1])))
    report = {
        "faults": [],
        "stop_windows": stop_windows(recs),
        "build_step_messages": 0,
    }
    for f in (r for r in recs if r["fault"]):
        res = check_fault(
            f, recs, inst, instance_of(inst, f["t0"]), stderr_lines, threads
        )
        report["faults"].append(dict(receipt=f["name"], **res))
        fmt = " ".join(
            f"{c}={'UNTESTED' if res[c] is None else ('ok' if res[c] else 'FAIL')}"
            for c in ("C1", "C2", "C3", "C4", "C5")
        )
        print(f"{f['name']} {fmt} {res['verdict']}")
    report["build_step_messages"] = sum(1 for r in recs if r["msg"] and not r["fault"])
    print(
        f"fetch_faults={len(report['faults'])} build_step_messages={report['build_step_messages']} stop_windows={len(report['stop_windows'])}"
    )
    if a.out:
        Path(a.out).write_text(
            json.dumps(report, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
    bad = report["stop_windows"] or any(
        x["verdict"] != "UPSTREAM-TRANSIENT" for x in report["faults"]
    )
    return 10 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
