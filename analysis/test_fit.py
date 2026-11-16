import json
import math
import os
import random
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import fit


def synth(T_by_eco, n_per_cell=60, seed=1, asof=2026, years=range(2013, 2025)):
    rng = random.Random(seed)
    rows = []
    for eco, T in T_by_eco.items():
        for y in years:
            age = asof - y
            S = math.exp(-math.log(2) * age / T)
            for _ in range(n_per_cell):
                rows.append(
                    {
                        "ecosystem": eco,
                        "year": y,
                        "snapshot": "ERA",
                        "exit_code": 0 if rng.random() < S else 1,
                        "failure_class": "OK",
                    }
                )
    return rows


def test_recovers_halflife_within_tolerance():
    rows = synth({"python": 4.0, "node": 3.0, "go": 12.0, "rust": 8.0}, n_per_cell=200)
    res = fit.analyse(rows, 2026, seed=3)
    for eco, T in {"python": 4.0, "node": 3.0, "go": 12.0, "rust": 8.0}.items():
        est = res["ecosystems"][eco]["h2_halflife_years"]
        assert abs(est - T) / T < 0.25, (eco, est)
        lo, hi = res["ecosystems"][eco]["h2_ci95"]
        assert lo <= T <= hi, (eco, lo, T, hi)
    assert (
        res["h2_verdict"] is True
        and res["h2_best"] == "go"
        and res["h2_worst"] == "node"
    )


def test_trend_detected_and_null_not_detected():
    decaying = synth({"python": 3.0}, n_per_cell=100)
    flat = [
        dict(r, exit_code=0 if random.Random(i).random() < 0.6 else 1)
        for i, r in enumerate(decaying)
    ]
    assert fit.analyse(decaying, 2026)["ecosystems"]["python"]["h1_verdict"] is True
    assert fit.analyse(flat, 2026)["ecosystems"]["python"]["h1_verdict"] is False


def test_no_manifest_excluded_from_denominator():
    rows = synth({"rust": 5.0}, n_per_cell=10)
    rows.append(
        {
            "ecosystem": "rust",
            "year": 2020,
            "snapshot": "ERA",
            "exit_code": 1,
            "failure_class": "NO-MANIFEST",
        }
    )
    res = fit.analyse(rows, 2026)
    assert res["no_manifest_excluded"] == 1
    assert (
        sum(v["n"] for v in res["ecosystems"]["rust"]["success_by_age"].values()) == 120
    )


def test_fisher_matches_known_value():
    # classic table [[3,1],[1,3]] two-sided p = 0.4857
    assert abs(fit.fisher_two_sided(3, 1, 1, 3) - 0.4857) < 1e-3


def test_h3_direction():
    rows = []
    for i in range(200):
        rows.append(
            {
                "ecosystem": "python",
                "year": 2024,
                "snapshot": "NOW",
                "exit_code": 0 if i % 3 else 1,
                "failure_class": "OK",
                "ai_marker": True,
            }
        )
        rows.append(
            {
                "ecosystem": "python",
                "year": 2024,
                "snapshot": "NOW",
                "exit_code": 0 if i % 10 else 1,
                "failure_class": "OK",
                "ai_marker": False,
            }
        )
    res = fit.analyse(rows, 2026)
    assert res["h3"]["verdict"] is True


def test_cli_runs():
    rows = synth({"go": 6.0}, n_per_cell=5)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    out = subprocess.run(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "fit.py"),
            f.name,
            "--asof",
            "2026",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(out.stdout)["rows"] == len(rows)
    os.unlink(f.name)
