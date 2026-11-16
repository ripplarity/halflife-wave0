import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import archive_loss as al

CAP = Path(__file__).resolve().parent / "a18_captures"
N, C = "zzqx-not-a-real-pkg-9431", "zzqx-not-a-real-crate-9431"

# real messages captured 2026-11-11 (npm 11.13, pnpm 11.21, yarn 1.22.22, uv 0.11.17, cargo 1.99.1, go 1.27, pip 26.1)
REAL = [
    ("pip_name", 1, N, None),
    ("pip_ver", 1, "requests", "0.0.999"),
    ("uv_name", 2, N, None),
    ("uv_ver", 3, "requests", "0.0.999"),
    ("npm_name", 9, N, None),
    ("npm_ver", 6, "left-pad", "99.99.99"),
    ("pnpm_name", 10, N, None),
    ("pnpm_ver", 6, "left-pad", "99.99.99"),
    ("yarn_name", 11, N, None),
    ("yarn_ver", 8, "left-pad", "99.99.99"),
    ("cargo_name", 14, C, None),
    ("cargo_ver", 15, "serde", "=99.0.0"),
    ("go_name", 13, "github.com/zzqx-nope/nope-9431", "v1.0.0"),
    ("go_ver", 12, "github.com/pkg/errors", "v0.99.99"),
]


@pytest.mark.parametrize("fn,pat,name,ver", REAL)
def test_real_captured_message(fn, pat, name, ver):
    r = al.first_named((CAP / f"{fn}.txt").read_text(encoding="utf-8"))
    assert r is not None and (r["pattern"], r["name"], r["version"]) == (pat, name, ver)
    assert not r.get("off_registry")


# forms not captured from a run (older tool versions): written from documentation, labelled as such in A18
SYNTH = [
    ("npm ERR! 404  'foo@1.2.3' is not in the npm registry.", 4, "foo", "1.2.3"),
    ("npm ERR! 404 '@a/b' is not in this registry.", 4, "@a/b", None),
    (
        "npm error 404  The requested resource '@a/b@2.0.0' could not be found",
        5,
        "@a/b",
        "2.0.0",
    ),
    ('error Couldn\'t find package "foo" on the "npm" registry.', 7, "foo", None),
    ("error: failed to load source for dependency `bar`", 16, "bar", None),
]


@pytest.mark.parametrize("line,pat,name,ver", SYNTH)
def test_synthetic_forms(line, pat, name, ver):
    r = al.first_named(line)
    assert (r["pattern"], r["name"], r["version"]) == (pat, name, ver)


def test_url_parsing_off_registry_and_transient():
    r = al.first_named(
        "npm ERR! 404 Not Found - GET https://registry.npmjs.org/@a%2fb/-/b-1.2.3.tgz"
    )
    assert (r["name"], r["version"], r["off_registry"]) == ("@a/b", "1.2.3", False)
    r = al.first_named(
        "x\n502 Bad Gateway\nnpm ERR! 404 Not Found - GET https://npm.corp.example/foo - Not found"
    )
    assert (
        r["off_registry"] and r["transient_before"] and r["host"] == "npm.corp.example"
    )
    assert (
        al.first_named(
            "version 1.429.0 timed out\nNo matching distribution found for q"
        )["transient_before"]
        is False
    )
    assert (
        al.first_named(
            "ModuleNotFoundError: No module named 'x'\nCannot find module 'y'"
        )
        is None
    )


def test_population_and_rows(tmp_path):
    def mk(n, rec, log):
        (tmp_path / f"{n}.json").write_text(json.dumps(rec))
        (tmp_path / f"{n}.log").write_text(log)

    base = {
        "exit_code": 1,
        "failure_class": "DEP-MISSING",
        "refused_hosts": [],
        "snapshot": "NOW",
    }
    mk("a", base, "No matching distribution found for q==1")
    mk("b", dict(base, refused_hosts=["h"]), "No matching distribution found for q")
    mk("c", base, "ERR_PNPM_FETCH_403 x\nNo matching version found for q@1")
    mk(
        "d",
        base,
        "ERR_PNPM_FETCH_404 GET https://registry.npmjs.org/q: Not Found - 404",
    )
    mk("e", dict(base, failure_class="OTHER"), "No matching distribution found for q")
    mk("f", dict(base, exit_code=0), "No matching distribution found for q")
    mk("g", base, "ImportError: No module named z")
    got = {r["receipt"]: r for r in al.rows(tmp_path)}
    mk("h", dict(base, failure_class="TIMEOUT"), "No matching distribution found for q")
    mk("i", dict(base, failure_class="OTHER"), "nothing named")
    assert sorted(got) == ["a.json", "d.json", "e.json", "g.json"]
    assert sorted(r["receipt"] for r in al.rows(tmp_path)) == sorted(got)
    assert got["g.json"]["pattern"] is None and got["d.json"]["name"] == "q"
    out = tmp_path / "o" / "r.jsonl"
    assert (
        al.main([str(tmp_path), "--out", str(out)]) == 0
        and len(out.read_text().splitlines()) == 4
    )


def test_bounded_patterns_do_not_span_unrelated_modules():
    nl = chr(10)
    filler = ("ok line" + nl) * 200
    log = (
        "go: a.example/m@v1.0.0: downloading"
        + nl
        + filler
        + "go: b.example/n@v2.0.0: reading b.example/n/go.mod at revision v2.0.0: unknown revision v2.0.0"
        + nl
    )
    r = al.first_named(log)
    assert (r["pattern"], r["name"], r["version"]) == (12, "b.example/n", "v2.0.0")
    log = (
        "ERR_PNPM_FETCH_404 no url here"
        + nl
        + filler
        + "see https://registry.npmjs.org/zzz for docs"
        + nl
    )
    assert al.first_named(log) is None
