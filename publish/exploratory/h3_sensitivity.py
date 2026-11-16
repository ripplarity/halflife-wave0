"""EXPLORATORY, post-hoc (chosen after the fit; changes no verdict). Two checks on H3 counts from
publish/exploratory/h3_composition.txt: (1) Fisher two-sided without the 20 pnpm-defect rows; (2) Cochran-Mantel-Haenszel
stratified by ecosystem (chi-square with continuity correction, Mantel-Haenszel pooled odds ratio).
Usage: python -B publish/exploratory/h3_sensitivity.py > publish/exploratory/h3_sensitivity.txt"""

from scipy.stats import fisher_exact
from scipy.stats.contingency import crosstab  # noqa: F401  (scipy present check)
from statsmodels.stats.contingency_tables import StratifiedTable

# (marker_ok, marker_n, other_ok, other_n), copied from h3_composition.txt (sha256 6ba255a2...)
ALL = (174, 369, 115, 205)
NO_DEFECT = (174, 350, 115, 204)
ECO = {
    "go": (52, 70, 49, 74),
    "node": (32, 115, 15, 34),
    "python": (48, 89, 22, 47),
    "rust": (42, 95, 29, 50),
}


def tab(c):
    a, n1, b, n2 = c
    return [[a, n1 - a], [b, n2 - b]]


assert (
    sum(v[1] for v in ECO.values()) == ALL[1]
    and sum(v[3] for v in ECO.values()) == ALL[3]
)
print("# EXPLORATORY post-hoc; changes no verdict")
for name, c in (("all (fit H3 table)", ALL), ("without pnpm-defect rows", NO_DEFECT)):
    odds, p = fisher_exact(tab(c))
    print(
        f"fisher_two_sided {name}: marker {c[0]}/{c[1]} other {c[2]}/{c[3]} OR {odds:.3f} p {p:.4f}"
    )
for e, c in ECO.items():
    odds, p = fisher_exact(tab(c))
    print(
        f"fisher_two_sided eco={e}: marker {c[0]}/{c[1]} other {c[2]}/{c[3]} OR {odds:.3f} p {p:.4f}"
    )
st = StratifiedTable([tab(c) for c in ECO.values()])
r = st.test_null_odds(correction=True)
print(
    f"cmh_by_ecosystem: chi2 {r.statistic:.4f} p {r.pvalue:.4f} pooled_OR_MH {st.oddsratio_pooled:.3f} "
    f"CI95 {st.oddsratio_pooled_confint()[0]:.3f} to {st.oddsratio_pooled_confint()[1]:.3f}"
)
r0 = st.test_null_odds(correction=False)
print(f"cmh_by_ecosystem_no_correction: chi2 {r0.statistic:.4f} p {r0.pvalue:.4f}")
bd = st.test_equal_odds()
print(f"breslow_day_homogeneity: chi2 {bd.statistic:.4f} p {bd.pvalue:.4f}")
print(
    f"node share: marker {ECO['node'][1]}/{ALL[1]} = {ECO['node'][1] / ALL[1]:.3f}; other {ECO['node'][3]}/{ALL[3]} = {ECO['node'][3] / ALL[3]:.3f}"
)
