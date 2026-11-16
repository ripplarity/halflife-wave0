import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import archive_probe as ap

REC = {
    "repo": "o/r",
    "commit": "c0ffee",
    "started_utc": "2026-11-10T00:00:00Z",
    "manifest_path": "package.json",
}
RAW = "https://raw.githubusercontent.com/o/r/c0ffee/"


def canned(table):
    calls = []

    def get(url):
        calls.append(url)
        v = table.get(url, (404, b""))
        if isinstance(v, Exception):
            raise v
        st, body = v
        return st, body if isinstance(body, bytes) else json.dumps(body).encode()

    get.calls = calls
    return get


def run(tmp_path, row, table, rec=REC, sleeps=None):
    g = canned(table)
    p = ap.Probe(
        tmp_path,
        getter=g,
        wait=600,
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
    )
    return (
        ap.probe_row(
            p,
            dict({"pattern": 6, "transient_before": False, "receipt": "x.json"}, **row),
            rec,
        ),
        p,
        g,
    )


def npm(name, version, **kw):
    return dict(ecosystem="npm", name=name, version=version, **kw)


# ---------- outcomes ----------


def test_unnamed_not_probed(tmp_path):
    out, p, g = run(
        tmp_path,
        {"pattern": None, "ecosystem": "npm", "name": None, "version": None},
        {},
    )
    assert out["outcome"] == "UNNAMED" and g.calls == []


def test_transient_is_unprobed(tmp_path):
    out, _, g = run(tmp_path, dict(npm("a", "1.0.0"), transient_before=True), {})
    assert out["outcome"] == "UNPROBED" and g.calls == []


def test_off_registry_from_url_host(tmp_path):
    out, _, g = run(
        tmp_path, dict(npm("a", "1.0.0"), host="npm.example.com", off_registry=True), {}
    )
    assert out["outcome"] == "OFF-REGISTRY" and g.calls == []


def test_off_registry_from_lockfile_declared_source(tmp_path):
    lock = {
        "packages": {
            "node_modules/a": {
                "version": "1.0.0",
                "resolved": "git+https://github.com/x/a.git#abc",
            }
        }
    }
    out, _, _ = run(
        tmp_path, npm("a", "1.0.0"), {RAW + "package-lock.json": (200, lock)}
    )
    assert out["outcome"] == "OFF-REGISTRY"


def test_npm_name_absent_without_existed(tmp_path):
    out, _, _ = run(tmp_path, npm("zzqx-not-a-real-pkg-9431", "1.0.0"), {})
    assert out["outcome"] == "NAME-ABSENT" and out["existed"] is False


def test_npm_name_absent_with_lockfile_existed(tmp_path):
    lock = {
        "packages": {
            "node_modules/gone": {
                "version": "1.0.0",
                "resolved": "https://registry.npmjs.org/gone/-/gone-1.0.0.tgz",
            }
        }
    }
    out, _, _ = run(
        tmp_path, npm("gone", "1.0.0"), {RAW + "package-lock.json": (200, lock)}
    )
    assert (
        out["outcome"] == "NAME-ABSENT"
        and out["existed"]
        and out["existed_basis"] == "a:lockfile"
    )


def test_npm_lockfile_hash_alone_does_not_count(tmp_path):
    lock = "lockfileVersion: 6\npackages:\n  /gone@1.0.0:\n    resolution: {integrity: sha512-abc}\n"
    out, _, _ = run(
        tmp_path, npm("gone", "1.0.0"), {RAW + "pnpm-lock.yaml": (200, lock.encode())}
    )
    assert out["outcome"] == "NAME-ABSENT" and out["existed"] is False


def test_npm_unpublished_is_existed_b(tmp_path):
    doc = {
        "time": {"unpublished": {"time": "2020-01-01T00:00:00Z", "versions": ["1.0.0"]}}
    }
    out, _, _ = run(
        tmp_path,
        npm("left-pad-x", "1.0.0"),
        {"https://registry.npmjs.org/left-pad-x": (200, doc)},
    )
    assert (
        out["outcome"] == "NAME-ABSENT"
        and out["existed_basis"] == "b:npm time.unpublished"
    )


def test_npm_version_absent_and_present(tmp_path):
    doc = {"versions": {"1.3.0": {}}, "dist-tags": {"latest": "1.3.0"}}
    t = {"https://registry.npmjs.org/left-pad": (200, doc)}
    assert (
        run(tmp_path, npm("left-pad", "99.99.99"), t)[0]["outcome"] == "VERSION-ABSENT"
    )
    assert run(tmp_path, npm("left-pad", "1.3.0"), t)[0]["outcome"] == "PRESENT"
    assert run(tmp_path, npm("left-pad", "latest"), t)[0]["outcome"] == "PRESENT"


def test_npm_range_rule(tmp_path):
    t = {
        "https://registry.npmjs.org/a": (
            200,
            {"versions": {"1.2.0": {}, "2.0.0-beta.1": {}}},
        )
    }
    assert run(tmp_path, npm("a", "^1.0.0"), t)[0]["outcome"] == "PRESENT"
    assert (
        run(tmp_path, npm("a", "^3.0.0"), t)[0]["outcome"] == "UNPROBED"
    )  # range unsatisfied -> UNPROBED
    assert run(tmp_path, npm("a", "1.x"), t)[0]["outcome"] == "PRESENT"
    assert run(tmp_path, npm("a", "~1.2.0"), t)[0]["outcome"] == "PRESENT"


def test_npm_scoped_name_url(tmp_path):
    out, _, g = run(
        tmp_path,
        npm("@s/p", "1.0.0"),
        {"https://registry.npmjs.org/@s%2fp": (200, {"versions": {"1.0.0": {}}})},
    )
    assert (
        out["outcome"] == "PRESENT" and "https://registry.npmjs.org/@s%2fp" in g.calls
    )


def test_pypi_pep503_and_versions(tmp_path):
    rec = dict(REC, manifest_path="requirements.txt")
    url = "https://pypi.org/pypi/my-pkg/json"
    doc = {"releases": {"1.0": [{"filename": "x"}], "2.0": []}}
    row = dict(ecosystem="pypi", pattern=1)
    assert (
        run(
            tmp_path,
            dict(row, name="My_Pkg[extra]", version="1.0"),
            {url: (200, doc)},
            rec,
        )[0]["outcome"]
        == "PRESENT"
    )
    assert (
        run(tmp_path, dict(row, name="my.pkg", version="2.0"), {url: (200, doc)}, rec)[
            0
        ]["outcome"]
        == "VERSION-ABSENT"
    )
    assert (
        run(tmp_path, dict(row, name="my-pkg", version=None), {url: (200, doc)}, rec)[
            0
        ]["outcome"]
        == "PRESENT"
    )
    assert (
        run(tmp_path, dict(row, name="nope", version="1.0"), {}, rec)[0]["outcome"]
        == "NAME-ABSENT"
    )


def test_pypi_uv_lock_existed(tmp_path):
    rec = dict(REC, manifest_path="pyproject.toml")
    lock = '[[package]]\nname = "gone-pkg"\nversion = "1.0"\nsource = { registry = "https://pypi.org/simple" }\n'
    out, _, _ = run(
        tmp_path,
        dict(ecosystem="pypi", pattern=1, name="Gone_Pkg", version="1.0"),
        {RAW + "uv.lock": (200, lock.encode())},
        rec,
    )
    assert out["outcome"] == "NAME-ABSENT" and out["existed_basis"] == "a:lockfile"


def test_cargo_yanked_exact_and_range(tmp_path):
    rec = dict(REC, manifest_path="Cargo.toml")
    doc = {
        "versions": [
            {"num": "1.0.0", "yanked": True},
            {"num": "1.1.0", "yanked": False},
        ]
    }
    t = {"https://crates.io/api/v1/crates/serde": (200, doc)}
    row = dict(ecosystem="cargo", pattern=15, name="serde")
    assert run(tmp_path, dict(row, version="=1.0.0"), t, rec)[0]["outcome"] == "YANKED"
    assert (
        run(tmp_path, dict(row, version="=99.0.0"), t, rec)[0]["outcome"]
        == "VERSION-ABSENT"
    )
    assert (
        run(tmp_path, dict(row, version="1.0"), t, rec)[0]["outcome"] == "PRESENT"
    )  # bare = caret, 1.1.0 fits
    assert run(tmp_path, dict(row, version="^2"), t, rec)[0]["outcome"] == "UNPROBED"


def test_cargo_lock_registry_source_is_existed(tmp_path):
    rec = dict(REC, manifest_path="Cargo.toml")
    lock = '[[package]]\nname = "gone"\nversion = "0.1.0"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n'
    out, _, _ = run(
        tmp_path,
        dict(ecosystem="cargo", pattern=15, name="gone", version="=0.1.0"),
        {RAW + "Cargo.lock": (200, lock.encode())},
        rec,
    )
    assert out["outcome"] == "NAME-ABSENT" and out["existed_basis"] == "a:lockfile"


def test_cargo_lock_path_dependency_is_off_registry(tmp_path):
    rec = dict(REC, manifest_path="Cargo.toml")
    lock = '[[package]]\nname = "local"\nversion = "0.1.0"\n'
    out, _, _ = run(
        tmp_path,
        dict(ecosystem="cargo", pattern=14, name="local", version=None),
        {RAW + "Cargo.lock": (200, lock.encode())},
        rec,
    )
    assert out["outcome"] == "OFF-REGISTRY"


def test_go_not_applicable_without_go_mod(tmp_path):
    rec = dict(REC, manifest_path="main.go")
    out, _, _ = run(
        tmp_path,
        dict(ecosystem="go", pattern=12, name="github.com/A/b", version="v1.0.0"),
        {},
        rec,
    )
    assert out["outcome"] == "NOT-APPLICABLE"


def test_go_version_absent_with_sumdb_record(tmp_path):
    rec = dict(REC, manifest_path="go.mod")
    t = {
        RAW + "go.mod": (200, b"module x\n"),
        "https://proxy.golang.org/github.com/!a/b/@v/list": (200, b"v0.9.0\n"),
        "https://proxy.golang.org/github.com/!a/b/@v/v1.0.0.info": (410, b"gone"),
        "https://sum.golang.org/lookup/github.com/A/b@v1.0.0": (200, b"record"),
    }
    out, _, _ = run(
        tmp_path,
        dict(ecosystem="go", pattern=12, name="github.com/A/b", version="v1.0.0"),
        t,
        rec,
    )
    assert (
        out["outcome"] == "VERSION-ABSENT"
        and out["existed_basis"] == "b:sum.golang.org"
    )


def test_go_checksum_db_host(tmp_path):
    out, _, _ = run(
        tmp_path,
        dict(
            ecosystem="go",
            pattern=13,
            name="m",
            version="v1",
            host="sum.golang.org",
            off_registry=True,
        ),
        {},
    )
    assert out["outcome"] == "CHECKSUM-DB"


# ---------- probe mechanics ----------


def test_failed_probe_retried_once_after_ten_minutes_then_unprobed(tmp_path):
    sleeps = []
    out, p, g = run(
        tmp_path,
        npm("a", "1.0.0"),
        {"https://registry.npmjs.org/a": (503, b"busy")},
        sleeps=sleeps,
    )
    assert out["outcome"] == "UNPROBED" and "probe failed twice" in out["reason"]
    assert sleeps == [600] and g.calls.count("https://registry.npmjs.org/a") == 2


def test_network_exception_counts_as_failure(tmp_path):
    out, _, _ = run(
        tmp_path, npm("a", "1.0.0"), {"https://registry.npmjs.org/a": OSError("reset")}
    )
    assert out["outcome"] == "UNPROBED"


def test_responses_saved_hashed_and_timestamps(tmp_path):
    out, p, _ = run(
        tmp_path,
        npm("a", "1.0.0"),
        {"https://registry.npmjs.org/a": (200, {"versions": {"1.0.0": {}}})},
    )
    assert out["build_utc"] == REC["started_utc"] and out["probe_utc"].endswith("Z")
    import hashlib

    for e in p.log:
        f = tmp_path / "responses" / f"{e['sha256']}.bin"
        assert f.is_file() and hashlib.sha256(f.read_bytes()).hexdigest() == e["sha256"]


def test_main_reads_no_outcome_fields(tmp_path, monkeypatch):
    rd = tmp_path / "rec"
    rd.mkdir()
    (rd / "x.json").write_text(
        json.dumps(dict(REC, exit_code=1, failure_class="DEP-MISSING"))
    )
    rows = tmp_path / "rows.jsonl"
    rows.write_text(
        json.dumps(
            {
                "pattern": None,
                "receipt": "x.json",
                "ecosystem": "npm",
                "failure_class": "DEP-MISSING",
            }
        )
        + "\n"
    )
    monkeypatch.setattr(ap, "http_get", lambda url: (404, b""))
    assert (
        ap.main([str(rows), "--record-dir", str(rd), "--out", str(tmp_path / "o")]) == 0
    )
    r = json.loads((tmp_path / "o" / "probe_rows.jsonl").read_text())
    assert r["outcome"] == "UNNAMED" and "exit_code" not in r


def test_receipt_repo_url_and_directory_manifest_path(tmp_path):
    # receipts record repo as a full GitHub URL and manifest_path as a file or a build directory
    assert ap.raw_url("https://github.com/o/r", "c", "a/b.lock") == "https://raw.githubusercontent.com/o/r/c/a/b.lock"
    assert ap.raw_url("o/r.git", "c", "x") == "https://raw.githubusercontent.com/o/r/c/x"
    assert ap.manifest_dir("archiver") == "archiver/"
    assert ap.manifest_dir("web/package.json") == "web/"
    assert ap.manifest_dir("package.json") == "" and ap.manifest_dir(".") == ""
    rec = dict(REC, repo="https://github.com/o/r", manifest_path="web")
    lock = {"packages": {"node_modules/gone": {"version": "1.0.0", "resolved": "https://registry.npmjs.org/gone/-/gone-1.0.0.tgz"}}}
    out, _, _ = run(tmp_path, npm("gone", "1.0.0"), {RAW + "web/package-lock.json": (200, lock)}, rec)
    assert out["existed_basis"] == "a:lockfile"
