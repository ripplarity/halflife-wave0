"""HALF-LIFE A18 second-source probe: is the first named artefact of a failed build absent from its registry today?

Runs AFTER the fit, from an open network (not the farm proxy), one pass, GET of public metadata only. Every response
is saved and hashed. Outcome rules are exactly those fixed in PREREG_AMENDMENTS.md A18 (NOTARY block 12); this tool
is hashed into the notary before it runs.

Input: analysis/out/archive_loss_rows.jsonl (archive_loss.py). From each named receipt in --record-dir it reads only
repo, commit, started_utc and manifest_path (to date the build and find lockfiles at that commit); no outcome field.

Usage: python -B analysis/archive_probe.py ROWS --record-dir OUT/core_record --out analysis/out/archive_probe
Writes OUT/probe_rows.jsonl (one row per input row), OUT/responses.jsonl (url, status, sha256, fetched_utc) and
OUT/responses/<sha256>.bin. Prints only the output paths and sha256 values.

Outcomes: UNNAMED (no pattern matched; not probed), OFF-REGISTRY, NOT-APPLICABLE, CHECKSUM-DB, NAME-ABSENT,
VERSION-ABSENT, YANKED, PRESENT, UNPROBED. EXISTED (a) lockfile / (b) public removal record, set only on the two
ABSENT outcomes. Network: every request goes through Probe.get, so tests inject canned responses.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

UA = "halflife-archive-probe/1 (research; metadata GET only)"
CARGO_INDEX = 'source = "registry+https://github.com/rust-lang/crates.io-index"'
NPM_HOSTS = ("https://registry.npmjs.org/", "https://registry.yarnpkg.com/")
PY_HOSTS = ("pypi.org", "files.pythonhosted.org")
OK = (200, 404, 410)  # any other status, or an exception, is a failed probe


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_get(url: str, timeout: float = 30.0):
    """The only network call. Returns (status, body bytes)."""
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""


class ProbeFailed(Exception):
    pass


class Probe:
    """Fetches, saves and hashes; a failed fetch is retried once after `wait` seconds (A18: failed twice 10 min apart)."""

    def __init__(
        self, out: Path, getter=http_get, wait: float = 600.0, sleep=time.sleep
    ):
        self.out, self.getter, self.wait, self.sleep = out, getter, wait, sleep
        (out / "responses").mkdir(parents=True, exist_ok=True)
        self.log = []
        self.cache = {}

    def get(self, url: str):
        if url in self.cache:
            return self.cache[url]
        for attempt in (1, 2):
            try:
                status, body = self.getter(url)
            except Exception as e:  # network error
                status, body = None, repr(e).encode()
            h = hashlib.sha256(body).hexdigest()
            (self.out / "responses" / f"{h}.bin").write_bytes(body)
            self.log.append(
                {
                    "url": url,
                    "status": status,
                    "sha256": h,
                    "fetched_utc": now(),
                    "attempt": attempt,
                }
            )
            if status in OK:
                self.cache[url] = (status, body)
                return status, body
            if attempt == 1:
                self.sleep(self.wait)
        raise ProbeFailed(url)

    def json(self, url: str):
        status, body = self.get(url)
        if status != 200:
            return status, None
        try:
            return status, json.loads(body)
        except ValueError:
            raise ProbeFailed(url)


# ---------- names and versions ----------


def pep503(name: str) -> str:
    return re.sub(r"[-_.]+", "-", re.sub(r"\[.*\]$", "", name)).lower()


def go_escape(path: str) -> str:
    """Module path escaping of the Go module proxy: an upper-case letter becomes '!' + lower case."""
    return re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), path)


SEMVER = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.\-]+))?(?:\+[0-9A-Za-z.\-]+)?$"
)


def parse_semver(v: str):
    m = SEMVER.match(v.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) or "")


def _key(t):
    # a pre-release sorts below its release
    return (t[0], t[1], t[2], 0 if t[3] else 1, t[3])


def _cmp_ok(op: str, v, b) -> bool:
    kv, kb = _key(v), _key(b)
    return {"=": kv == kb, ">": kv > kb, ">=": kv >= kb, "<": kv < kb, "<=": kv <= kb}[
        op
    ]


def _expand(term: str, cargo: bool):
    """One comparator term -> list of (op, version tuple), or None when the syntax is not understood."""
    term = term.strip()
    if term in ("*", "", "x", "X", "latest"):
        return []
    m = re.match(
        r"^(\^|~|>=|<=|>|<|=)?\s*v?([0-9xX*]+)(?:\.([0-9xX*]+))?(?:\.([0-9xX*]+))?(?:-([0-9A-Za-z.\-]+))?$",
        term,
    )
    if not m:
        return None
    op = m.group(1) or ("^" if cargo else "=")
    parts = [m.group(2), m.group(3), m.group(4)]
    wild = [p is None or p in ("x", "X", "*") for p in parts]
    nums = [0 if w else int(p) for p, w in zip(parts, wild)]
    pre = m.group(5) or ""
    if wild[0]:
        return []
    if op in ("=",) and any(wild):  # x-range: 1.x, 1.2.x
        n = wild.index(True)
        lo = (nums[0], nums[1] if n > 1 else 0, 0, "")
        hi = (nums[0] + 1, 0, 0, "") if n == 1 else (nums[0], nums[1] + 1, 0, "")
        return [(">=", lo), ("<", hi)]
    base = (nums[0], nums[1], nums[2], pre)
    if op == "^":
        if nums[0] > 0 or wild[1]:
            hi = (nums[0] + 1, 0, 0, "")
        elif nums[1] > 0 or wild[2]:
            hi = (0, nums[1] + 1, 0, "")
        else:
            hi = (0, 0, nums[2] + 1, "")
        return [(">=", base), ("<", hi)]
    if op == "~":
        hi = (nums[0] + 1, 0, 0, "") if wild[1] else (nums[0], nums[1] + 1, 0, "")
        return [(">=", base), ("<", hi)]
    return [(op, base)]


def satisfies(version: str, req: str, cargo: bool = False):
    """True/False, or None when the requirement syntax is not understood (the row is then UNPROBED)."""
    v = parse_semver(version)
    if v is None:
        return False
    for alt in req.split("||"):
        terms = (
            [t for t in re.split(r"[,\s]+(?=[\^~<>=0-9v*xX])", alt.strip()) if t]
            if alt.strip()
            else ["*"]
        )
        conds = []
        for t in terms:
            e = _expand(t, cargo)
            if e is None:
                return None
            conds += e
        if v[3] and not any(b[3] and b[:3] == v[:3] for _, b in conds):
            continue  # pre-releases match only a comparator that names the same release with a pre-release
        if all(_cmp_ok(op, v, b) for op, b in conds):
            return True
    return False


def exact_version(v: str, cargo: bool, eco_pypi: bool = False):
    """The single version a requirement names exactly, or None for a range."""
    s = v.strip()
    if eco_pypi:
        return s.lstrip(
            "="
        )  # the pip/uv patterns capture only ==<version> pins: always exact
    if cargo:
        return s[1:].strip() if s.startswith("=") and parse_semver(s[1:]) else None
    return s.lstrip("=v") if parse_semver(s.lstrip("=")) else None


# ---------- lockfiles (EXISTED (a), declared source) ----------


MANIFESTS = re.compile(
    r"(^|/)(package\.json|Cargo\.toml|go\.mod|pyproject\.toml|setup\.py|setup\.cfg|Pipfile|requirements[^/]*\.txt)$"
)


def manifest_dir(manifest_path: str) -> str:
    """Receipts record manifest_path either as a manifest file or as the build directory: return the directory
    with a trailing slash, or "" for the repository root."""
    m = (manifest_path or "").strip().strip("/")
    if m in ("", "."):
        return ""
    if MANIFESTS.search(m):
        return m.rsplit("/", 1)[0] + "/" if "/" in m else ""
    return m + "/"


def lock_paths(eco: str, manifest_path: str):
    d = manifest_dir(manifest_path)
    names = {
        "npm": [
            "package-lock.json",
            "npm-shrinkwrap.json",
            "yarn.lock",
            "pnpm-lock.yaml",
        ],
        "cargo": ["Cargo.lock"],
        "pypi": ["uv.lock", "Pipfile.lock", "poetry.lock"],
        "go": [],
    }[eco]
    out = [d + n for n in names]
    if d:
        out += names  # a workspace lockfile at the root
    return out


def lock_source(eco: str, fname: str, text: str, name: str, version):
    """'official', 'other' (the artefact is declared from another source) or None (not named in this lockfile)."""
    base = fname.rsplit("/", 1)[-1]
    if eco == "npm" and base in ("package-lock.json", "npm-shrinkwrap.json"):
        try:
            d = json.loads(text)
        except ValueError:
            return None
        entries = []
        for k, e in (d.get("packages") or {}).items():
            if k.split("node_modules/")[-1] == name:
                entries.append(e)

        def walk(deps):
            for k, e in (deps or {}).items():
                if k == name:
                    entries.append(e)
                walk(e.get("dependencies") if isinstance(e, dict) else None)

        walk(d.get("dependencies"))
        for e in entries:
            if not isinstance(e, dict) or (version and e.get("version") != version):
                continue
            res = e.get("resolved") or ""
            if res:
                return "official" if res.startswith(NPM_HOSTS) else "other"
        return None
    if eco == "npm" and base == "yarn.lock":
        for block in re.split(r"\n(?=\S)", text):
            head = block.split("\n", 1)[0]
            if not re.search(r'(^|[\s,"])' + re.escape(name) + r"@", head):
                continue
            if version and not re.search(
                r'\n\s+version:? "?' + re.escape(version) + r'"?', block
            ):
                continue
            m = re.search(r'\n\s+resolved:? "?([^"\s]+)', block)
            if m:
                return "official" if m.group(1).startswith(NPM_HOSTS) else "other"
        return None
    if eco == "npm" and base == "pnpm-lock.yaml":
        for m in re.finditer(r"tarball: (\S+)", text):
            url = m.group(1)
            if "/" + name + "/-/" in url and (not version or f"-{version}.tgz" in url):
                return "official" if url.startswith(NPM_HOSTS) else "other"
        return None  # pnpm usually records only an integrity hash: a hash alone does not count
    if eco in ("cargo", "pypi") and base in ("Cargo.lock", "uv.lock", "poetry.lock"):
        for block in text.split("[[package]]")[1:]:
            n = re.search(r'\nname = "([^"]+)"', block)
            if not n or (
                pep503(n.group(1)) != pep503(name)
                if eco == "pypi"
                else n.group(1) != name
            ):
                continue
            vv = re.search(r'\nversion = "([^"]+)"', block)
            if version and (not vv or vv.group(1) != version):
                continue
            if eco == "cargo":
                src = re.search(r'\nsource = "([^"]+)"', block)
                if not src:
                    return "other"  # a path or workspace member
                return (
                    "official"
                    if f'source = "{src.group(1)}"' == CARGO_INDEX
                    else "other"
                )
            src = re.search(r"\nsource = \{([^}]*)\}", block) or re.search(
                r'\nurl = "([^"]+)"', block
            )
            if src:
                return (
                    "official" if any(h in src.group(1) for h in PY_HOSTS) else "other"
                )
            return None
        return None
    if eco == "pypi" and base == "Pipfile.lock":
        try:
            d = json.loads(text)
        except ValueError:
            return None
        srcs = [s.get("url", "") for s in (d.get("_meta") or {}).get("sources") or []]
        for sect in ("default", "develop"):
            for k, e in (d.get(sect) or {}).items():
                if pep503(k) != pep503(name) or not isinstance(e, dict):
                    continue
                if version and e.get("version", "").lstrip("=") != version:
                    continue
                if "git" in e or "path" in e or "file" in e:
                    return "other"
                if e.get("hashes") and srcs:
                    return (
                        "official"
                        if all(any(h in s for h in PY_HOSTS) for s in srcs)
                        else "other"
                    )
        return None
    return None


def raw_url(repo: str, commit: str, path: str) -> str:
    """repo is recorded as a full GitHub URL in receipts (https://github.com/owner/name); owner/name also works."""
    slug = re.sub(r"^https?://github\.com/", "", repo.strip()).strip("/")
    slug = re.sub(r"\.git$", "", slug)
    return f"https://raw.githubusercontent.com/{slug}/{commit}/{quote(path)}"


# ---------- one row ----------


def probe_row(p: Probe, row: dict, rec: dict) -> dict:
    eco, name, version = row.get("ecosystem"), row.get("name"), row.get("version")
    out = {
        "receipt": row.get("receipt"),
        "snapshot": row.get("snapshot"),
        "failure_class": row.get("failure_class"),
        "ecosystem": eco,
        "name": name,
        "version": version,
        "host": row.get("host"),
        "build_utc": rec.get("started_utc"),
        "probe_utc": now(),
        "existed": False,
        "existed_basis": None,
    }

    def done(outcome, **kw):
        out.update(outcome=outcome, **kw)
        return out

    if row.get("pattern") is None:
        return done("UNNAMED")
    if row.get("transient_before"):
        return done("UNPROBED", reason="transient")
    if not name:
        return done("UNPROBED", reason="no usable name")
    if row.get("host") == "sum.golang.org":
        return done("CHECKSUM-DB")
    if row.get("off_registry"):
        return done("OFF-REGISTRY")
    repo, commit, man = (
        rec.get("repo"),
        rec.get("commit"),
        rec.get("manifest_path") or "",
    )
    try:
        exact = (
            exact_version(version, eco == "cargo", eco == "pypi") if version else None
        )
        # the dependency's declared source, from a lockfile at the build commit
        lock = None
        if repo and commit:
            for lp in lock_paths(eco, man):
                st, body = p.get(raw_url(repo, commit, lp))
                if st == 200:
                    s = lock_source(
                        eco, lp, body.decode("utf-8", "replace"), name, exact
                    )
                    if s:
                        lock = s
                        break
        if lock == "other":
            return done("OFF-REGISTRY", declared_source="lockfile")
        if eco == "go":
            gomod = manifest_dir(man) + "go.mod"
            if repo and commit and p.get(raw_url(repo, commit, gomod))[0] != 200:
                return done("NOT-APPLICABLE")
            mod = go_escape(name)
            st, _ = p.get(f"https://proxy.golang.org/{mod}/@v/list")
            if st in (404, 410):
                outcome = "NAME-ABSENT"
            elif not version:
                return done("PRESENT")
            else:
                st, _ = p.get(
                    f"https://proxy.golang.org/{mod}/@v/{go_escape(version)}.info"
                )
                if st == 200:
                    return done("PRESENT")
                outcome = "VERSION-ABSENT"
            if version:
                st, _ = p.get(f"https://sum.golang.org/lookup/{name}@{version}")
                if st == 200:
                    out.update(existed=True, existed_basis="b:sum.golang.org")
            return done(outcome)
        if eco == "pypi":
            st, d = p.json(f"https://pypi.org/pypi/{pep503(name)}/json")
            if st in (404, 410):
                outcome = "NAME-ABSENT"
            elif not version:
                return done("PRESENT")
            elif exact is None:
                vs = [v for v, files in (d.get("releases") or {}).items() if files]
                ok = [satisfies(v, version) for v in vs]
                if any(o is True for o in ok):
                    return done("PRESENT")
                return done("UNPROBED", reason="range not satisfied or not understood")
            else:
                files = (d.get("releases") or {}).get(exact)
                if files:
                    return done("PRESENT")
                outcome = "VERSION-ABSENT"
        elif eco == "npm":
            st, d = p.json("https://registry.npmjs.org/" + name.replace("/", "%2f"))
            unpub = bool(d and (d.get("time") or {}).get("unpublished"))
            if st in (404, 410) or (d is not None and unpub and not d.get("versions")):
                outcome = "NAME-ABSENT"
            elif not version or version in (d.get("dist-tags") or {}):
                return done("PRESENT")
            elif exact is None:
                ok = [satisfies(v, version) for v in (d.get("versions") or {})]
                if any(o is True for o in ok):
                    return done("PRESENT")
                return done("UNPROBED", reason="range not satisfied or not understood")
            elif exact in (d.get("versions") or {}):
                return done("PRESENT")
            else:
                outcome = "VERSION-ABSENT"
            if unpub:
                out.update(existed=True, existed_basis="b:npm time.unpublished")
        elif eco == "cargo":
            st, d = p.json(f"https://crates.io/api/v1/crates/{name}")
            if st in (404, 410):
                outcome = "NAME-ABSENT"
            elif not version:
                return done("PRESENT")
            else:
                vers = {
                    v["num"]: v.get("yanked", False)
                    for v in d.get("versions") or []
                    if "num" in v
                }
                if exact is not None:
                    if exact not in vers:
                        outcome = "VERSION-ABSENT"
                    else:
                        return done("YANKED" if vers[exact] else "PRESENT")
                else:
                    ok = [
                        satisfies(v, version, cargo=True)
                        for v, y in vers.items()
                        if not y
                    ]
                    if any(o is True for o in ok):
                        return done("PRESENT")
                    return done(
                        "UNPROBED", reason="range not satisfied or not understood"
                    )
        else:
            return done("UNPROBED", reason=f"unknown ecosystem {eco}")
    except ProbeFailed as e:
        return done("UNPROBED", reason=f"probe failed twice: {e}")
    if lock == "official" and not out["existed"]:
        out.update(existed=True, existed_basis="a:lockfile")
    return done(outcome)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("--record-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--retry-wait", type=float, default=600.0)
    a = ap.parse_args(argv)
    out = Path(a.out)
    p = Probe(out, getter=lambda u: http_get(u), wait=a.retry_wait)
    rd = Path(a.record_dir)
    keep = ("repo", "commit", "started_utc", "manifest_path")
    res = []
    for line in Path(a.rows).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rec = {}
        rp = rd / (row.get("receipt") or "")
        if row.get("receipt") and rp.is_file():
            r = json.loads(rp.read_text(encoding="utf-8"))
            rec = {k: r.get(k) for k in keep}  # no outcome field is read
        res.append(probe_row(p, row, rec))
    files = {
        "probe_rows.jsonl": "".join(json.dumps(x, sort_keys=True) + "\n" for x in res),
        "responses.jsonl": "".join(json.dumps(x, sort_keys=True) + "\n" for x in p.log),
    }
    for fn, txt in files.items():
        data = txt.encode("utf-8")
        (out / fn).write_bytes(data)
        print(f"out={out / fn} sha256={hashlib.sha256(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
