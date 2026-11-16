import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit, sensitivity_a15 as S
import pytest


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    # fit.bootstrap_ci (1000 resamples) only feeds H2's CI; H1/H3 logic under test is unaffected.
    monkeypatch.setattr(fit, "bootstrap_ci", lambda ages, outs, n=1000, seed=0: (1.0, 2.0))


def rows(n_per_cell, revs, seed=1, decay=True):
    rnd = random.Random(seed); out = []
    for e in fit.ECOSYSTEMS:
        for y in range(2013, 2025):
            for i in range(n_per_cell):
                p = 0.2 + 0.06 * (y - 2013) if decay else 0.5
                out.append({"snapshot": "ERA", "ecosystem": e, "year": y, "exit_code": 0 if rnd.random() < p else 1,
                            "recipe_id": "halflife-recipe-" + revs[i % len(revs)], "failure_class": ""})
    return out


def test_stratified_ca_equals_plain_for_one_stratum():
    g = [(1, 8, 10), (2, 5, 10), (3, 2, 10)]
    assert S.stratified_ca([g]) == fit.cochran_armitage(g)


def test_fixed_effect_detects_trend_and_no_change():
    r = rows(30, ["v2g", "v2j"])
    head = fit.analyse(r, 2026, 1); fa = S.fixed_effect(r, 2026, 1)
    assert all(fa["ecosystems"][e]["h1_verdict"] for e in fit.ECOSYSTEMS)
    assert fa["ecosystems"]["go"]["recipe_strata"] == ["v2g", "v2j"]
    assert S.verdict_changes(head, fa) == []


def test_confound_is_removed_by_strata():
    # no age effect within a revision; revision alone tracks age -> pooled trend, stratified none
    rnd = random.Random(3); r = []
    for e in fit.ECOSYSTEMS:
        for y in range(2013, 2025):
            old = y < 2019
            for i in range(40):
                r.append({"snapshot": "ERA", "ecosystem": e, "year": y, "failure_class": "",
                          "recipe_id": "x-" + ("v2g" if old else "v2j"),
                          "exit_code": 0 if rnd.random() < (0.2 if old else 0.8) else 1})
    head = fit.analyse(r, 2026, 1); fa = S.fixed_effect(r, 2026, 1)
    assert head["ecosystems"]["python"]["h1_verdict"]
    assert not any(fa["ecosystems"][e]["h1_verdict"] for e in fit.ECOSYSTEMS)
    assert "H1/python" in S.verdict_changes(head, fa)


def test_v2j_only_threshold():
    short = S.v2j_only(rows(40, ["v2g", "v2j"]), 2026)  # 20 v2j per cell
    assert short["skipped"] and len(short["short_cells"]) == 48
    ok = S.v2j_only(rows(30, ["v2j"]), 2026)
    assert ok["skipped"] is False and ok["ecosystems"]["rust"]["n_era"] == 360


def test_summary_matches_fill_contract():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "publish"))
    import json, tempfile, fill
    r = rows(30, ["v2g", "v2j"])
    head = fit.analyse(r, 2026, 1)
    res = S.summarise(head, S.fixed_effect(r, 2026, 1), S.v2j_only(r, 2026, 1))
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"a": res["a"], "b": res["b"]}, f)
    v = fill.a15_sensitivity_values(f.name)
    assert v["a15_sens_changed"].startswith("no hypothesis")
