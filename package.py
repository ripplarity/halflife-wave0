"""HALF-LIFE dataset packager: receipts dir -> dataset folder.

Output (in OUT_DIR):
  receipts.jsonl             one row per build, fields documented in DATA_README.md
  DATA_README.md             field documentation (copied from publish/DATA_README.md)
  MANIFEST.sha256            "<sha256>  <name>" for every file above
  MANIFEST.sha256.dsse.json  one DSSE attestation (attest-spec v1.4, predicateType halflife/receipt/v1)
                             whose subjects are MANIFEST.sha256 and every file it lists.
  cells/<eco>_<year>.dsse.json  one DSSE attestation per ecosystem-cohort cell (predicateType
                             halflife/receipt-cell/v1) over that cell's byte-exact rows of receipts.jsonl.

Usage: python package.py RECEIPTS_DIR OUT_DIR --key KEYFILE [--year-source FILE ...] [--run-mode REAL]
KEYFILE holds the 32-byte ed25519 seed as 64 hex characters. The real key path is only ever an argument.
Exit 0 ok; 2 if any row has no cohort year in the year sources.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections import Counter

sys.dont_write_bytecode = (
    True  # never leave __pycache__ in the read-only attest-spec dir
)
HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
def _spec_dir():
    """attest-spec location: --spec DIR (or --spec=DIR) on the command line, else the ATTEST_SPEC env var; no default."""
    for i, a in enumerate(sys.argv):
        if a == "--spec" and i + 1 < len(sys.argv):
            d = sys.argv[i + 1]
            del sys.argv[i : i + 2]
            return d
        if a.startswith("--spec="):
            del sys.argv[i]
            return a.split("=", 1)[1]
    d = os.environ.get("ATTEST_SPEC")
    if not d:
        raise SystemExit("package.py: give the attest-spec directory with --spec DIR or the ATTEST_SPEC env var")
    return d


ATTEST_DIR = _spec_dir()
sys.path.insert(0, ATTEST_DIR)
from attest_verify import BASE, PAYLOAD_TYPE, jcs, keyid, pae
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

TOOL_VERSION = "1.0.0"
PREDICATE = BASE + "halflife/receipt/v1"
# Published fields, in order (DATA_README.md). client_ip is deliberately NOT published.
FIELDS = [
    "repo",
    "year",
    "snapshot",
    "commit",
    "ecosystem",
    "manifest_path",
    "flags",
    "recipe_id",
    "toolchain",
    "image_digest",
    "exit_code",
    "success",
    "duration_s",
    "failure_class",
    "refused_hosts",
    "mem_peak_bytes",
    "log_sha256",
    "started_utc",
]
DEFAULT_YEAR_SOURCES = [
    os.path.join(STUDY, p)
    for p in ("PILOT.txt", "FROZEN_LIST.jsonl", "FROZEN_LIST_FULL.jsonl")
]


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


ASCII_YEAR = re.compile(
    r"[0-9]{4}"
)  # str.isdigit()/int() accept non-ASCII digits; we do not
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
REPO_RE = re.compile(r"[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+")
SNAPSHOTS = ("ERA", "NOW")
MANIFEST_LINE = re.compile(r"([0-9a-f]{64})  (\S(?:.*\S)?)")


def _year(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 1000 <= v <= 9999 else None
    if isinstance(v, str) and ASCII_YEAR.fullmatch(v):
        return int(v)
    return None


def load_years(paths):
    years = {}
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("{"):
                    d = json.loads(line)
                    y = _year(d.get("year"))
                    if y is not None:
                        years.setdefault(d["full_name"].lower(), y)
                else:
                    parts = line.split("\t")
                    if len(parts) >= 2 and _year(parts[1]) is not None:
                        years.setdefault(parts[0].lower(), int(parts[1]))
    return years


def repo_name(url):
    return "/".join(url.rstrip("/").split("/")[-2:])


def _check_receipt(p, r):
    """Reject receipts whose fields would be silently coerced (bool/str exit codes, non-ASCII digits)."""
    bad = []
    if type(r.get("exit_code")) is not int:
        bad.append(f"exit_code {r.get('exit_code')!r} is not an int")
    if r.get("snapshot") not in SNAPSHOTS:
        bad.append(f"snapshot {r.get('snapshot')!r}")
    if not (isinstance(r.get("commit"), str) and HEX40.fullmatch(r["commit"])):
        bad.append(f"commit {r.get('commit')!r} is not 40 lowercase ASCII hex")
    if not isinstance(r.get("repo"), str) or not REPO_RE.fullmatch(
        repo_name(r["repo"])
    ):
        bad.append(f"repo {r.get('repo')!r}")
    d = r.get("duration_s")
    if isinstance(d, bool) or not isinstance(d, (int, float)) or d != d or d < 0:
        bad.append(f"duration_s {d!r}")
    if bad:
        raise SystemExit(f"bad receipt {os.path.basename(p)}: " + "; ".join(bad))


# A8/A10/A12: rows of record come from these revisions (v2c = the rev-2 pilot); every v2f receipt is void.
# A14: every v2h receipt is void (VOID_LIST_v2h.tsv, files prefixed v2h__); v2i and v2j are valid rows.
RECIPE_VALID = (
    "halflife-recipe-v2e",
    "halflife-recipe-v2g",
    "halflife-recipe-v2i",
    "halflife-recipe-v2j",
)
RECIPE_VOID_ONLY = ("halflife-recipe-v2f", "halflife-recipe-v2h")
PREFIXED_RE = re.compile(
    r"^v2[a-z]__"
)  # A10: void files of one revision carry e.g. the prefix v2f__


def _in_part(base, prefix):
    """prefix None: files without a revision prefix; else only files that start with it."""
    return base.startswith(prefix) if prefix else not PREFIXED_RE.match(base)


def build_rows(receipts_dir, years, allow_empty=False, void=False, prefix=None):
    rows = []
    for p in sorted(glob.glob(os.path.join(receipts_dir, "*.json"))):
        if void and not _in_part(os.path.basename(p), prefix):
            continue
        with open(p, encoding="utf-8") as f:
            r = json.load(f)
        _check_receipt(p, r)
        if not void and r.get("recipe_id") in RECIPE_VOID_ONLY:
            raise SystemExit(
                f"bad receipt {os.path.basename(p)}: {r['recipe_id']} receipts are all void (A10, A14); "
                "they belong only in a void part"
            )
        name = repo_name(r["repo"])
        row = {k: r.get(k) for k in FIELDS}
        row["repo"] = name
        row["year"] = years.get(name.lower())
        row["success"] = r["exit_code"] == 0
        rows.append(row)
    if not rows and not allow_empty:
        raise SystemExit(f"no *.json receipts in {receipts_dir}")
    seen = {}
    for r in rows:
        k = (r["repo"].lower(), r["snapshot"])
        if k in seen:
            raise SystemExit(
                f"duplicate receipt for {r['repo']} {r['snapshot']} in {receipts_dir} "
                "(one receipt per repo and snapshot; void rows belong in a void folder)"
            )
        seen[k] = r
    rows.sort(key=lambda x: (x["repo"].lower(), x["snapshot"], x["commit"] or ""))
    return rows


def load_key(path):
    seed = bytes.fromhex(open(path, encoding="ascii").read().strip())
    if len(seed) != 32:
        raise SystemExit("key file must hold a 32-byte ed25519 seed as 64 hex chars")
    priv = Ed25519PrivateKey.from_private_bytes(seed)
    raw = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return priv, raw


def now_z():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


VOID_README = """# VOID receipts (NOT part of any analysed denominator)

Every folder under void/ holds build receipts that were declared VOID by a pre-registered amendment
(PREREG_AMENDMENTS.md, A6 as corrected by A8) and replaced by a rebuild whose receipt is in ../receipts.jsonl.
They are published for audit only. Do not pool them with receipts.jsonl.

- void/<folder>/receipts.jsonl  the void receipts, same fields as ../receipts.jsonl plus void_part
- void/<folder>/VOID_LIST.tsv   the void list exactly as written when the rule was applied (when one exists)

A8 (corrects A6: the fault was a defect in the farm's allowlist proxy, fixed in recipe rev 2f): every CORE
receipt started at or after 2026-11-10T07:07:50Z and before the rev 2f proxy started is void, whatever its
outcome. Folder core_void_standby_* holds the first 280 (name kept from the first, corrected diagnosis);
core_void_proxy_* holds the rest. A10: every receipt written under rev 2f is void (the proxy log was
reopened per connection; fixed in rev 2g); these are the files prefixed v2f__, published as their own part
with VOID_LIST_v2f.tsv. A14: every receipt written under rev 2h is void (three fetch-step proxy faults in
that proxy instance); these are the files prefixed v2h__, published as their own part with VOID_LIST_v2h.tsv.
A6 Rule 3: one receipt with no log file (folder core_void_incomplete). Five void parts, 639 receipts in all.
Each row's recipe_id names the recipe revision (and so the proxy) that served it; halflife-recipe-v2e,
-v2g, -v2i and -v2j receipts are equally valid rows; no halflife-recipe-v2f or -v2h receipt is a row of record.
"""


def _prepare_out(out_dir):
    """Refuse to mix a new package with unknown files; a previous package (has MANIFEST.sha256) is replaced."""
    if os.path.isdir(out_dir) and os.listdir(out_dir):
        if not os.path.isfile(os.path.join(out_dir, "MANIFEST.sha256")):
            raise SystemExit(
                f"{out_dir} is not empty and is not a previous package; refusing"
            )
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)


def _write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def _p(out_dir, name):
    return os.path.join(out_dir, *name.split("/"))


def package(
    receipts_dir,
    out_dir,
    key_path,
    year_sources=None,
    run_mode="REAL",
    void_dirs=(),
    void_list_sha=None,
    void_parts=(),
):
    """void_dirs: A6 void folders, published under void/<basename>/. void_list_sha: {basename: sha256}
    pins a VOID_LIST.tsv to the hash recorded in the amendment (mismatch = refuse)."""
    started = now_z()
    years = load_years(year_sources or DEFAULT_YEAR_SOURCES)
    rows = build_rows(receipts_dir, years)
    voids = []
    specs = [
        (
            os.path.basename(os.path.normpath(vd)),
            vd,
            os.path.join(vd, "VOID_LIST.tsv"),
            None,
        )
        for vd in void_dirs or ()
    ] + list(void_parts or ())
    for vname, vd, vl, prefix in specs:
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", vname) or vname in {
            v[0] for v in voids
        }:
            raise SystemExit(f"bad or duplicate void folder name {vname!r}")
        if not os.path.isdir(vd):
            raise SystemExit(f"{vname}: void folder {vd} not found")
        vrows = build_rows(vd, years, allow_empty=True, void=True, prefix=prefix)
        for r in vrows:
            r["void_part"] = vname
        vl = vl if vl and os.path.isfile(vl) else None
        want = (void_list_sha or {}).get(vname)
        if want and (vl is None or sha256_file(vl) != want):
            raise SystemExit(
                f"{vname}: VOID_LIST.tsv missing or sha256 differs from the amendment"
            )
        if not vrows and vl is None:
            raise SystemExit(
                f"{vname}: void folder has no receipts and no VOID_LIST.tsv"
            )
        voids.append((vname, vrows, vl))
    _prepare_out(out_dir)
    _write_jsonl(os.path.join(out_dir, "receipts.jsonl"), rows)
    shutil.copyfile(
        os.path.join(HERE, "DATA_README.md"), os.path.join(out_dir, "DATA_README.md")
    )
    names = ["DATA_README.md", "receipts.jsonl"]
    void_meta = {}
    if voids:
        with open(
            os.path.join(out_dir, "VOID_README.md"), "w", encoding="utf-8", newline="\n"
        ) as f:
            f.write(VOID_README)
        names.append("VOID_README.md")
    for vname, vrows, vl in voids:
        _write_jsonl(_p(out_dir, f"void/{vname}/receipts.jsonl"), vrows)
        names.append(f"void/{vname}/receipts.jsonl")
        if vl:
            shutil.copyfile(vl, _p(out_dir, f"void/{vname}/VOID_LIST.tsv"))
            names.append(f"void/{vname}/VOID_LIST.tsv")
        void_meta[vname] = {
            "builds": len(vrows),
            "void_list_sha256": sha256_file(vl) if vl else None,
        }
    priv, raw = load_key(key_path)
    # PREREG "each batch of receipts is signed (DSSE)": one attestation per ecosystem-cohort cell over
    # that cell's rows of receipts.jsonl (byte-exact lines, in file order). Listed in the manifest too.
    with open(os.path.join(out_dir, "receipts.jsonl"), "rb") as f:
        cells = cell_lines(f.read())
    for (eco, year), blines in sorted(cells.items()):
        crow = [json.loads(b) for b in blines]
        cstmt = {
            "_type": "https://in-toto.io/Statement/v1",
            "subject": [
                {
                    "name": cell_subject(eco, year),
                    "digest": {"sha256": hashlib.sha256(b"".join(blines)).hexdigest()},
                }
            ],
            "predicateType": CELL_PREDICATE,
            "predicate": {
                "producer": {"tool": "halflife-package", "version": TOOL_VERSION},
                "started": started,
                "ended": now_z(),
                "environment": {
                    "host_os": platform.system().lower() or "unknown",
                    "run_mode": run_mode,
                },
                "cell": {"ecosystem": eco, "year": year},
                "builds": len(crow),
                "successes": sum(1 for r in crow if r["success"]),
            },
        }
        cname = cell_file(eco, year)
        os.makedirs(os.path.dirname(_p(out_dir, cname)), exist_ok=True)
        with open(_p(out_dir, cname), "w", encoding="utf-8", newline="\n") as f:
            f.write(canonical_envelope(_sign(cstmt, priv, raw)))
        names.append(cname)
    man = os.path.join(out_dir, "MANIFEST.sha256")
    with open(man, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(f"{sha256_file(_p(out_dir, n))}  {n}\n" for n in names)
    subjects = [{"name": "MANIFEST.sha256", "digest": {"sha256": sha256_file(man)}}] + [
        {"name": n, "digest": {"sha256": sha256_file(_p(out_dir, n))}} for n in names
    ]
    pred = {
        "producer": {"tool": "halflife-package", "version": TOOL_VERSION},
        "started": started,
        "ended": now_z(),
        "environment": {
            "host_os": platform.system().lower() or "unknown",
            "run_mode": run_mode,
        },
        "builds": len(rows),
        "repos": len({r["repo"] for r in rows}),
        "successes": sum(1 for r in rows if r["success"]),
        "rows_without_year": sum(1 for r in rows if r["year"] is None),
        "recipe_ids": sorted({str(r["recipe_id"]) for r in rows}),
        "recipe_id_counts": dict(
            sorted(Counter(str(r["recipe_id"]) for r in rows).items())
        ),
    }
    if void_meta:
        pred["void_parts"] = void_meta
    stmt = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": subjects,
        "predicateType": PREDICATE,
        "predicate": pred,
    }
    env = _sign(stmt, priv, raw)
    with open(man + ".dsse.json", "w", encoding="utf-8", newline="\n") as f:
        f.write(canonical_envelope(env))
    return {
        "cells": len(cells),
        "keyid": keyid(raw),
        "public_key_hex": raw.hex(),
        "builds": len(rows),
        "manifest_sha256": sha256_file(man),
        "rows_without_year": pred["rows_without_year"],
        "void_parts": void_meta,
        "recipe_id_counts": pred["recipe_id_counts"],
    }


def canonical_envelope(env):
    return json.dumps(env, indent=2) + "\n"


CELL_PREDICATE = BASE + "halflife/receipt-cell/v1"


def _sign(stmt, priv, raw):
    payload = jcs(stmt)
    sig = priv.sign(pae(PAYLOAD_TYPE, payload))
    return {
        "payloadType": PAYLOAD_TYPE,
        "payload": base64.b64encode(payload).decode(),
        "signatures": [{"keyid": keyid(raw), "sig": base64.b64encode(sig).decode()}],
    }


def _cell_key(d):
    eco = d.get("ecosystem") if isinstance(d.get("ecosystem"), str) else "none"
    y = _year(d.get("year"))
    return (eco, y if y is not None else "none")


def cell_lines(data):
    """receipts.jsonl bytes -> {(ecosystem, year): [line bytes incl. LF]} in file order."""
    cells = {}
    for line in data.split(b"\n")[:-1]:
        try:
            k = _cell_key(json.loads(line))
        except ValueError:
            k = ("none", "none")
        cells.setdefault(k, []).append(line + b"\n")
    return cells


def cell_subject(eco, year):
    return f"receipts.jsonl/ecosystem={eco}/year={year}"


def cell_file(eco, year):
    return f"cells/{eco}_{year}.dsse.json"


def _check_cells(out_dir, names, pub_hex, kid, probs):
    """Every ecosystem-cohort cell of receipts.jsonl has exactly one valid signed attestation."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
    except ValueError:
        probs.append("public key is not 32 bytes hex")
        return
    rp = _p(out_dir, "receipts.jsonl")
    cells = cell_lines(open(rp, "rb").read()) if os.path.isfile(rp) else {}
    want = {cell_file(*k): k for k in cells}
    have = {n for n in names if n.startswith("cells/")}
    probs += [f"cell attestation missing: {x}" for x in sorted(set(want) - have)]
    probs += [f"cell attestation for no cell: {x}" for x in sorted(have - set(want))]
    for n in sorted(have & set(want)):
        eco, year = want[n]
        p = _p(out_dir, n)
        if not os.path.isfile(p):
            continue  # reported as missing file above
        raw_env = open(p, "rb").read()
        try:
            env = json.loads(raw_env)
            payload = base64.b64decode(env["payload"], validate=True)
            stmt = json.loads(payload)
            sigs = env["signatures"]
        except (ValueError, KeyError, TypeError):
            probs.append(f"{n}: unreadable envelope")
            continue
        if raw_env != canonical_envelope(env).encode() or jcs(stmt) != payload:
            probs.append(f"{n}: envelope or payload not canonical")
        if env.get("payloadType") != PAYLOAD_TYPE or len(sigs) != 1:
            probs.append(f"{n}: payloadType or signature count wrong")
            continue
        if sigs[0].get("keyid") != kid:
            probs.append(f"{n}: keyid differs from the pinned keyid")
        try:
            pub.verify(base64.b64decode(sigs[0]["sig"]), pae(PAYLOAD_TYPE, payload))
        except (InvalidSignature, ValueError, KeyError, TypeError):
            probs.append(f"{n}: signature does not verify")
        blines = cells[(eco, year)]
        rows = [json.loads(b) for b in blines]
        pred = stmt.get("predicate") or {}
        if stmt.get("predicateType") != CELL_PREDICATE or stmt.get("subject") != [
            {
                "name": cell_subject(eco, year),
                "digest": {"sha256": hashlib.sha256(b"".join(blines)).hexdigest()},
            }
        ]:
            probs.append(
                f"{n}: subject does not match the cell's rows in receipts.jsonl"
            )
        if (
            pred.get("cell") != {"ecosystem": eco, "year": year}
            or pred.get("builds") != len(rows)
            or pred.get("successes") != sum(1 for r in rows if r.get("success") is True)
        ):
            probs.append(f"{n}: predicate cell/builds/successes disagree")


def _check_rows(n, data, pred, probs):
    rows = []
    for i, line in enumerate(data.split(b"\n")[:-1]):
        try:
            d = json.loads(line)
        except ValueError:
            probs.append(f"{n}:{i + 1} not JSON")
            continue
        want_keys = FIELDS + (["void_part"] if n.startswith("void/") else [])
        if list(d) != want_keys:
            probs.append(f"{n}:{i + 1} fields differ from the documented order")
        if line.decode("utf-8") != json.dumps(d, ensure_ascii=False):
            probs.append(f"{n}:{i + 1} not canonical")
        if type(d.get("exit_code")) is not int or d.get("success") is not (
            d.get("exit_code") == 0
        ):
            probs.append(f"{n}:{i + 1} exit_code/success inconsistent")
        if d.get("year") is not None and _year(d.get("year")) is None:
            probs.append(f"{n}:{i + 1} year not an ASCII 4-digit int")
        if d.get("snapshot") not in SNAPSHOTS or not HEX40.fullmatch(
            str(d.get("commit"))
        ):
            probs.append(f"{n}:{i + 1} snapshot/commit malformed")
        rows.append(d)
    keys = [(str(d.get("repo")).lower(), d.get("snapshot")) for d in rows]
    if len(set(keys)) != len(keys):
        probs.append(f"{n}: duplicate repo/snapshot row")
    order = [
        (str(d.get("repo")).lower(), str(d.get("snapshot")), d.get("commit") or "")
        for d in rows
    ]
    if order != sorted(order):
        probs.append(f"{n}: rows not in canonical order")
    if n == "receipts.jsonl" and (
        pred.get("builds") != len(rows)
        or pred.get("successes") != sum(1 for d in rows if d.get("success") is True)
    ):
        probs.append("predicate builds/successes disagree with receipts.jsonl")
    if n.startswith("void/"):
        part = n.split("/")[1]
        if (pred.get("void_parts") or {}).get(part, {}).get("builds") != len(rows):
            probs.append(f"{n}: predicate void_parts count disagrees")


def verify_dataset(out_dir, pub_hex, kid):
    """Full dataset check. Returns a list of problems ([] = valid).
    1. the reference verifier (signature, keyid pin, every subject's digest);
    2. what the reference verifier does not check: MANIFEST.sha256 is LF-only and well formed, its names
       equal the signed subjects, the folder holds exactly those files (no extra, none missing), the
       envelope is in this tool's canonical serialisation, and every receipts.jsonl is canonical (field
       order, ASCII digits, sorted, one row per repo and snapshot, predicate counts agree)."""
    envp = os.path.join(out_dir, "MANIFEST.sha256.dsse.json")
    r = subprocess.run(
        [
            sys.executable,
            "-B",
            os.path.join(ATTEST_DIR, "attest_verify.py"),
            envp,
            "--key",
            pub_hex,
            "--expect-keyid",
            kid,
            "--check-subjects",
            out_dir,
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return [
            f"reference verifier rc {r.returncode}: {(r.stderr or r.stdout).strip()}"
        ]
    probs = []
    raw_env = open(envp, "rb").read()
    env = json.loads(raw_env)
    if raw_env != canonical_envelope(env).encode():
        probs.append("envelope is not in canonical serialisation (re-serialised)")
    payload = base64.b64decode(env["payload"])
    stmt = json.loads(payload)
    if jcs(stmt) != payload:
        probs.append("payload is not JCS")
    man_b = open(os.path.join(out_dir, "MANIFEST.sha256"), "rb").read()
    if b"\r" in man_b or not man_b.endswith(b"\n"):
        probs.append("MANIFEST.sha256 line endings are not LF")
    names = []
    for line in man_b.decode("utf-8", "replace").split("\n")[:-1]:
        m = MANIFEST_LINE.fullmatch(line)
        if not m:
            probs.append(f"bad manifest line {line!r}")
            continue
        names.append(m.group(2))
    if len(set(names)) != len(names):
        probs.append("duplicate manifest entry")
    if [s["name"] for s in stmt["subject"]] != ["MANIFEST.sha256"] + names:
        probs.append("signed subjects differ from MANIFEST.sha256 names")
    on_disk = set()
    for root, _dirs, files in os.walk(out_dir):
        for fn in files:
            on_disk.add(
                os.path.relpath(os.path.join(root, fn), out_dir).replace(os.sep, "/")
            )
    expected = set(names) | {"MANIFEST.sha256", "MANIFEST.sha256.dsse.json"}
    probs += [f"file not in manifest: {x}" for x in sorted(on_disk - expected)]
    probs += [f"file missing: {x}" for x in sorted(expected - on_disk)]
    for n in names:
        if n.endswith("receipts.jsonl") and n in on_disk:
            _check_rows(n, open(_p(out_dir, n), "rb").read(), stmt["predicate"], probs)
    _check_cells(out_dir, names, pub_hex, kid, probs)
    return probs


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["verify"]:
        vp = argparse.ArgumentParser(prog="package.py verify")
        vp.add_argument("dataset")
        vp.add_argument("--key", required=True, help="public key hex")
        vp.add_argument("--expect-keyid", required=True)
        va = vp.parse_args(argv[1:])
        probs = verify_dataset(va.dataset, va.key, va.expect_keyid)
        for pr in probs:
            print(f"INVALID: {pr}", file=sys.stderr)
        print("DATASET-VALID" if not probs else "DATASET-INVALID")
        return 0 if not probs else 2
    ap = argparse.ArgumentParser()
    ap.add_argument("receipts_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--key", required=True, help="path to ed25519 seed (64 hex chars)")
    ap.add_argument(
        "--year-source",
        action="append",
        help="PILOT.txt-style TSV or FROZEN_LIST-style JSONL",
    )
    ap.add_argument(
        "--run-mode", default="REAL", choices=["REAL", "MOCK", "FIXTURE", "DRY-RUN"]
    )
    ap.add_argument(
        "--void-dir",
        action="append",
        default=[],
        help="A6 void folder (OUT/core_void_*); published under void/<name>/",
    )
    ap.add_argument(
        "--void-list-sha",
        action="append",
        default=[],
        metavar="NAME=SHA256",
        help="pin a void folder's VOID_LIST.tsv to the hash in the amendment",
    )
    ap.add_argument(
        "--void-part",
        action="append",
        default=[],
        metavar="LABEL=DIR,LIST[,PREFIX]",
        help="labelled void part: receipts in DIR (only those named PREFIX* when given, else those with no "
        "revision prefix), its void list LIST ('-' for none); pin LIST with --void-list-sha LABEL=SHA256",
    )
    a = ap.parse_args(argv)
    pins = dict(x.split("=", 1) for x in a.void_list_sha)
    parts = []
    for s in a.void_part:
        label, _, rest = s.partition("=")
        bits = rest.split(",")
        if not label or len(bits) not in (2, 3) or not bits[0]:
            raise SystemExit(f"--void-part {s!r}: want LABEL=DIR,LIST[,PREFIX]")
        parts.append(
            (
                label,
                bits[0],
                None if bits[1] == "-" else bits[1],
                bits[2] if len(bits) == 3 else None,
            )
        )
    info = package(
        a.receipts_dir,
        a.out_dir,
        a.key,
        a.year_source,
        a.run_mode,
        a.void_dir,
        pins,
        parts,
    )
    print(json.dumps(info))
    if info["rows_without_year"]:
        print(
            f"ERROR: {info['rows_without_year']} rows have no year in any year source",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
