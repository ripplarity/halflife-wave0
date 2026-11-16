"""HALF-LIFE A18 extraction: the first registry-reported absent dependency named in a failed build log.

Reads from each receipt ONLY exit_code, failure_class, refused_hosts, snapshot and the log text. Writes one JSONL
row per receipt of population P (A18). It runs no probe and prints no outcome: only the output path and its sha256.

Usage: python -B analysis/archive_loss.py RECORD_DIR --out analysis/out/archive_loss_rows.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

EXCLUDE = re.compile(
    r"farm proxy: host not listed|Proxy response \(403\)|Received HTTP code 403 from proxy|ERR_PNPM_FETCH_40[37]"
)
TRANSIENT = re.compile(
    r"\b5\d\d (?:Bad Gateway|Service Unavailable|Gateway Timeout|Internal Server Error)\b"
    r"|429 Too Many Requests|status code 429|HTTP 429|ETIMEDOUT|ECONNRESET|TLS handshake"
)
NPM = r"((?:@[\w.\-]+/)?[\w.\-]+)"
# (id, ecosystem, pattern); groups are parsed by NAMED below
PATTERNS = [
    (
        1,
        "pypi",
        r"No matching distribution found for ([A-Za-z0-9._\-\[\]]+)(?:==([^\s;,]+))?",
    ),
    (2, "pypi", r"Because (\S+?)(?:==(\S+))? was not found in the package registry"),
    (3, "pypi", r"there is no version of (\S+?)==(\S+)"),
    (4, "npm", r"'?" + NPM + r"(?:@([^'\s]+))?'? is not in (?:this|the npm) registry"),
    (5, "npm", r"The requested resource '" + NPM + r"@([^'\s]+)' could not be found"),
    (6, "npm", r"No matching version found for " + NPM + r"@(\S+)"),
    (7, "npm", r"Couldn't find package \"([^\"]+)\" on the \"npm\" registry"),
    (
        8,
        "npm",
        r"Couldn't find any versions for \"([^\"]+)\" that matches \"([^\"]+)\"",
    ),
    (9, "npm", r"404 Not Found - GET (https?://\S+)"),
    (10, "npm", r"ERR_PNPM_FETCH_404\D{0,120}(https?://\S+)"),
    (11, "npm", r"error Error: (https?://\S+?): Not found"),
    (12, "go", r"go: (\S+)@(\S+): .{0,300}?unknown revision (\S+)"),
    (13, "go", r"reading (https?://\S+): (?:404 Not Found|410 Gone)"),
    (14, "cargo", r"no matching package named `([^`]+)` found"),
    (
        15,
        "cargo",
        r"failed to select a version for the requirement `([^` ]+) = \"([^\"]+)\"`",
    ),
    (16, "cargo", r"failed to load source for dependency `([^`]+)`"),
]
COMPILED = [(i, eco, re.compile(p)) for i, eco, p in PATTERNS]
URL_IDS = {9, 10, 11, 13}
OFFICIAL = {"npm": "registry.npmjs.org", "go": "proxy.golang.org"}


def squash(text: str) -> str:
    """Whitespace runs become one space (uv wraps its sentences); offsets then give log order."""
    return re.sub(r"\s+", " ", text)


def clean(v):
    return v.rstrip(".,:;") if v else v


def from_url(eco: str, url: str):
    """(name, version, host). npm: path is the name (percent-decoded); a tarball path /-/<base>-<ver>.tgz gives
    the version. go: /<module>/@v/<ver>.(mod|zip|info)."""
    u = urlparse(clean(url))
    path = unquote(u.path).strip("/")
    if eco == "go":
        m = re.match(r"(.+)/@v/(.+)\.(?:mod|zip|info)$", path)
        return (m.group(1), m.group(2), u.hostname) if m else (path, None, u.hostname)
    m = re.match(r"(.+)/-/.+?-(\d[^/]*)\.tgz$", path)
    return (m.group(1), m.group(2), u.hostname) if m else (path, None, u.hostname)


def first_named(text: str):
    """The earliest match of any frozen pattern, or None."""
    t = squash(text)
    best = None
    for i, eco, rx in COMPILED:
        m = rx.search(t)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), i, eco, m)
    if best is None:
        return None
    pos, i, eco, m = best
    host = None
    if i in URL_IDS:
        name, version, host = from_url(eco, m.group(1))
    else:
        name, version = (
            clean(m.group(1)),
            clean(m.group(2)) if m.lastindex and m.lastindex >= 2 else None,
        )
    row = {"pattern": i, "ecosystem": eco, "name": name, "version": version}
    if host is not None:
        row["host"] = host
        row["off_registry"] = host != OFFICIAL.get(eco)
    row["transient_before"] = bool(TRANSIENT.search(t[:pos]))
    return row


def in_population(r: dict, text: str) -> bool:
    return (
        r.get("exit_code") not in (0, None)
        and r.get("failure_class") not in ("TIMEOUT", "OOM", "NO-MANIFEST")
        and not r.get("refused_hosts")
        and not EXCLUDE.search(text)
    )


def rows(record_dir: Path):
    for p in sorted(record_dir.glob("*.json"), key=lambda x: x.name):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            text = p.with_suffix(".log").read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        if not isinstance(r, dict) or not in_population(r, text):
            continue
        named = first_named(text)
        if named is None and r.get("failure_class") != "DEP-MISSING":
            continue  # A18: an unmatched row is UNNAMED only when its class is DEP-MISSING
        yield dict(
            named or {"pattern": None},
            receipt=p.name,
            snapshot=r.get("snapshot"),
            failure_class=r.get("failure_class"),
        )


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("record_dir")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    data = "".join(
        json.dumps(x, sort_keys=True) + "\n" for x in rows(Path(a.record_dir))
    ).encode("utf-8")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_bytes(data)
    print(f"out={a.out} sha256={hashlib.sha256(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
