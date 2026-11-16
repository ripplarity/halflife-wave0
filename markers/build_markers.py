"""HALF-LIFE H3 marker join (PREREG H3, PREREG_AMENDMENTS A5 item 4).

Reads only core/CORE_LIST.jsonl (NOW rows) and FROZEN_LIST.jsonl (cohort year). Reads no build
outcome. For each 2023/2024 CORE repo, at its NOW sha:
  (a) trailer: any commit reachable from NOW with a message line that starts with
      "Co-Authored-By:" (case-insensitive) and names, as a whole word, one of the frozen tools;
  (b) files: CLAUDE.md, .cursorrules, .github/copilot-instructions.md present at NOW (root-relative).
ai_marker = (a) or (b); null with an error when the repo or sha cannot be fetched.
Resumable: rows already in markers/ai_marker.jsonl are skipped; output is rewritten sorted at end.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "ai_marker.jsonl"
TMP = HERE / "_tmp"

TOOLS = (
    "Claude",
    "Copilot",
    "Cursor",
    "ChatGPT",
    "Codex",
    "Devin",
)  # frozen in PREREG H3
FILES = (
    "CLAUDE.md",
    ".cursorrules",
    ".github/copilot-instructions.md",
)  # frozen in PREREG H3
COHORTS = (2023, 2024)

TRAILER_RE = re.compile(r"^[ \t]*co-authored-by[ \t]*:(.*)$", re.IGNORECASE)
TOOL_RE = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(TOOLS) + r")(?![A-Za-z0-9])", re.IGNORECASE
)
GREP = r"^[[:space:]]*co-authored-by[[:space:]]*:.*(" + "|".join(TOOLS) + ")"

ENV = dict(
    os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="echo", GCM_INTERACTIVE="never"
)


def git(args, cwd=None, timeout=900):
    p = subprocess.run(
        ["git", *args], cwd=cwd, env=ENV, capture_output=True, timeout=timeout
    )
    return (
        p.returncode,
        p.stdout.decode("utf-8", "replace"),
        p.stderr.decode("utf-8", "replace"),
    )


def trailer_tool(message: str):
    """Return the canonical tool named on the first qualifying trailer line, else None."""
    for line in message.splitlines():
        m = TRAILER_RE.match(line)
        if m:
            t = TOOL_RE.search(m.group(1))
            if t:
                return next(
                    x for x in TOOLS if x.lower() == t.group(1).lower()
                ), line.strip()
    return None


def scan(gitdir: str, sha: str) -> dict:
    """Compute the marker on an existing (bare) repo. Raises RuntimeError if sha is unusable."""
    rc, _, err = git(["cat-file", "-e", sha + "^{commit}"], cwd=gitdir)
    if rc != 0:
        raise RuntimeError("now_sha not present: " + err.strip()[:200])
    # git's --grep narrows candidates; Python re-checks every hit with the exact rule.
    rc, out, err = git(
        [
            "log",
            "--reverse",
            "--date-order",
            "-i",
            "-E",
            "--grep",
            GREP,
            "--format=%H%x00%B%x1e",
            sha,
        ],
        cwd=gitdir,
        timeout=1800,
    )
    if rc != 0:
        raise RuntimeError("git log failed: " + err.strip()[:200])
    first_sha = first_tool = None
    lines = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        h, _, msg = rec.partition("\x00")
        hit = trailer_tool(msg)
        if hit:
            if first_sha is None:
                first_sha, first_tool = h.strip(), hit[0]
            if len(lines) < 20 and hit[1] not in lines:
                lines.append(hit[1])
    rc, out, err = git(
        ["ls-tree", "-r", "--name-only", "--full-tree", sha], cwd=gitdir, timeout=600
    )
    if rc != 0:
        raise RuntimeError("git ls-tree failed: " + err.strip()[:200])
    paths = set(out.splitlines())
    file_hits = [f for f in FILES if f in paths]
    base = {f.rsplit("/", 1)[-1] for f in FILES}
    anydepth = sorted(
        p for p in paths if p.rsplit("/", 1)[-1] in base and p not in FILES
    )[:50]
    return {
        "trailer_hit": first_sha is not None,
        "trailer_first_sha": first_sha,
        "trailer_tool": first_tool,
        "trailer_lines": lines,
        "file_hits": file_hits,
        "file_hits_other_depth": anydepth,
        "ai_marker": first_sha is not None or bool(file_hits),
    }


def _rm(path):
    def onerr(func, p, _):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onerror=onerr)


def fetch_and_scan(url: str, sha: str) -> dict:
    TMP.mkdir(exist_ok=True)
    d = tempfile.mkdtemp(dir=TMP)
    try:
        g = os.path.join(d, "r.git")
        rc, _, err = git(
            ["clone", "--bare", "--filter=blob:none", "--quiet", url, g], timeout=1800
        )
        if rc != 0:
            raise RuntimeError("clone failed: " + err.strip()[:300])
        if git(["cat-file", "-e", sha + "^{commit}"], cwd=g)[0] != 0:
            git(
                ["fetch", "--quiet", "--filter=blob:none", "origin", sha],
                cwd=g,
                timeout=900,
            )
        return scan(g, sha)
    finally:
        _rm(d)


def targets():
    year = {}
    with open(ROOT / "FROZEN_LIST.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                year[r["html_url"]] = int(r["year"])
    rows = []
    with open(ROOT / "core" / "CORE_LIST.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                if r["snapshot"] == "NOW" and year.get(r["repo"]) in COHORTS:
                    rows.append(
                        {
                            "repo": r["repo"],
                            "now_sha": r["commit"],
                            "cohort": year[r["repo"]],
                            "ecosystem": r["ecosystem"],
                        }
                    )
    rows.sort(key=lambda r: (r["cohort"], r["ecosystem"], r["repo"]))
    return rows


def main():
    rows = targets()
    done = {}
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["repo"]] = r
    with open(OUT, "a", encoding="utf-8") as fh:
        for i, t in enumerate(rows):
            if t["repo"] in done:
                continue
            row = dict(t)
            try:
                row.update(fetch_and_scan(t["repo"], t["now_sha"]))
                row["error"] = None
            except Exception as e:  # noqa: BLE001 - every failure is recorded, never false
                row.update(
                    trailer_hit=None,
                    trailer_first_sha=None,
                    trailer_tool=None,
                    trailer_lines=[],
                    file_hits=[],
                    file_hits_other_depth=[],
                    ai_marker=None,
                    error=f"{type(e).__name__}: {e}"[:500],
                )
            row["fetched_utc"] = dt.datetime.now(dt.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            fh.flush()
            done[t["repo"]] = row
            print(
                f"[{i + 1}/{len(rows)}] {t['repo']} err={row['error'] is not None}",
                flush=True,
            )
    order = [done[t["repo"]] for t in rows if t["repo"] in done]
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in order), encoding="utf-8"
    )
    os.replace(tmp, OUT)
    print(
        f"targets={len(rows)} rows={len(order)} errors={sum(r['error'] is not None for r in order)}"
    )


if __name__ == "__main__":
    sys.exit(main())
