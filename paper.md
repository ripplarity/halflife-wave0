# Does Popular Open-Source Software Stop Building with Age? A Pre-Registered Rebuild of Top GitHub Repositories Does Not Support a Decline in Every Ecosystem

Ripplarity

Analysis year: 2026. Status: version 1 (wave 0), after the single fit. Sections 2, 3, 6.1 (table and verdict lines),
6.2 (counts and p), 6.3, 6.4, 7, 8 (A1 table) and 9 (void, agreement, A15 and rebuild-reason figures) were filled
by `fill.py` from the analysis output (fit.json) and the signed receipts. The following were typed by hand from
pinned files and are traced number by number in NUMBER_SOURCES_v5.md: the added abstract sentences, the model
caveat in 6.1, the limits in 6.2, the 6.5 table and figures (analysis/out/archive_probe/probe_rows.jsonl,
publish/A18_SUMMARY_by_snapshot.txt), 6.6 (qa/A22_EOL.json, PREREG_AMENDMENTS A22/A23), 6.7
(publish/exploratory/), the void and TIMEOUT part hashes in section 9 (dataset MANIFEST.sha256), and the
literature-search counts (prior-art RERUN_2026-11-12 files). The pilot numbers in section 8 are copied from
the timestamped amendment log.

## Abstract

We rebuilt the most-starred GitHub repositories created in each year 2013-2024, in four ecosystems (Python,
Node, Go, Rust), from two snapshots each: the last commit at the end of the year after creation (ERA) and the
current head (NOW), with one fixed recipe per ecosystem, today's toolchains and one attempt. This report
covers the pre-registered CORE tier only (up to 75 repositories per ecosystem and year); the larger FULL tier
has not started and is not analysed here. The analysed data hold 7200 build attempts over
3600 repositories. During CORE a defect in the build farm's allowlist proxy (a descriptor limit in its
use of select and no timeout on request headers) made builds fail at the farm's own git fetch; it was found
from the progress monitor, reproduced and fixed in recipe revision 2f; two further proxy defects (a log file
reopened per connection, fixed in rev 2g, and a single-process throughput ceiling, changed in rev 2h) were
found the same way, and the rev 2h proxy then showed fetch-step faults of its own (A14). Receipts from the
affected windows were voided, whatever their outcome, and the rows rebuilt; the void sets are published
(639 void receipts in five parts by the amendments; 639 counted in the published void parts).
The first diagnosis of the fault was wrong and was corrected before any analysis (amendments A6 to A15). On a random 100-row sample of the earlier
receipts, rebuilt under the fixed proxy, 100 of 100 rows gave the same outcome; per-revision
samples (A15) gave 60 of 60 (rev 2g), 60 of 60 (rev 2i) and 55 of 60 (rev 2j).
Because farm revision changed during CORE, two sensitivity fits were pre-specified (A15): no hypothesis verdict changed under either sensitivity fit.
The pre-registered hypothesis that ERA build success decreases with age in every ecosystem (H1) is not
supported: it holds in 2 of 4 ecosystems, and in the other two the Cochran-Armitage trend test does not
reject at alpha 0.0125.
Per-ecosystem H1 results: Python NOT SUPPORTED, Node NOT SUPPORTED, Go SUPPORTED,
Rust SUPPORTED. Fitted exponential half-lives of ERA build success: Python 6.49 years (95% CI
5.84 to 7.14 years), Node 5.91 years (5.34 to 6.50 years), Go 6.47 years (5.92 to 7.09 years), Rust 4.33 years
(3.95 to 4.72 years). The pre-registered test that ecosystems differ in half-life (H2) is SUPPORTED. The
exponential model assumes steady decay; Python and Node show none, so their T is a fitted summary, not a
measured decay rate. H3 (secondary) meets its pre-registered test as computed (p = 0.045), but one marker row is a
misclassified human co-author; corrected, p = 0.056, and the association also does not survive post-hoc
stratification by ecosystem (sections 6.2, 6.7). Secondary results: the end-of-life comparison (A22/A23) prints "verdict_NOW_rows=DOES NOT
TRACK" and "A22_ERA_rule=UNDERPOWERED"; among DEP-MISSING NOW builds, 0 had a first named artefact that is now
absent and is known to have existed (A18). Every
build has a public receipt; each ecosystem-year cell of receipts and the whole dataset are signed (DSSE).

## 1. Question

What fraction of the most-starred GitHub repositories created in year Y (2013..2024) can be built today from
(a) their end-of-(Y+1) snapshot and (b) their current default-branch head, and how does that fraction decay
with age per ecosystem?

"Survival" in prior work on GitHub projects usually means continued activity (commits, maintainers). Here it
means only one thing: the repository builds today with its ecosystem's standard tools.

## 2. Population

For each year Y in 2013..2024 and each ecosystem in {Python, JavaScript/TypeScript (Node), Go, Rust}, the
candidate set is the most-starred non-fork repositories with GitHub `created_at` in Y and that primary
language, fetched once in monthly slices. Two tiers were frozen and hashed in a notary file: CORE before any
build (the pilot was drawn from it), FULL after CORE builds had started but before any CORE result was read
and before any FULL build:

- CORE: the 75 most-starred buildable repositories per cell (an ERA commit exists and an ecosystem manifest or
  legacy marker is present), drawn from rank <= 100, extended to rank <= 150 only where needed; 12 x 4 cells,
  up to 3,600 repositories. H1-H3 are confirmatory on CORE.
- FULL: the top ~1,000 per cell, reported as a pre-registered replication at scale with the same recipes and
  tests; per-cell FULL results are descriptive.

A repository's ecosystem is defined by the build manifest present at its ERA snapshot (shallowest manifest
wins; ties go to the query language; legacy Go and Rust markers count and such rows stay in the denominator).
Rows with no ERA commit, no manifest or an unreadable tree are listed with their status and excluded from
every denominator. Java, C and C++ are out of scope.

Population flow (counted from the frozen list and the analysed receipts):

| stage | repositories |
|---|---|
| frozen candidate list (CORE freeze, all statuses) | 5100 |
| excluded: NO-ERA (no default-branch commit by the ERA date) | 140 |
| excluded: NO-MANIFEST (no manifest or legacy marker at ERA) | 545 |
| excluded: TREE-FAILED (ERA tree unreadable) | 4 |
| beyond the CORE cut (rank or cell quota; FULL tier) | 811 |
| eligible CORE | 3600 |
| built: eligible CORE with at least one analysed receipt | 3600 (3600 ERA and 3600 NOW receipts) |
| eligible CORE without an analysed receipt | 0 |
| analysed repositories outside eligible CORE | 0 |
| footnote (A4): eligible CORE rows whose depth-2 tree failed but root manifest was confirmed | 4 |

In the data analysed here, 173 of 7200 build rows were classed NO-MANIFEST at build time (3 Go ERA rows, 170
NOW rows: a manifest present at ERA was gone at the head). The fit excludes them from the H1, H2 and H3
denominators (hence Go ERA n = 897 in 6.1 and 6.3). The descriptive tables in 6.4 and section 7 count every
receipt, so they include these rows as failures (Go ERA 434/900 in 6.4; NO-MANIFEST 173 among the 3694
failures in section 7).

## 3. Method

Snapshots. ERA: the last default-branch commit dated on or before Y+1-12-31. NOW: the default-branch head at
fetch time. Both fetched once; commit shas recorded.

Isolation. Each build runs in a container (sha256:cda5044e05fe51bbdb32ef64f32641760a55bac2e9d1dc2165213b5f1751bd35, sha256:cee8cf5d17c1b5e5f9be6a5a943e9bf1d8af4fa9fcf78c85b56ec98966eab593, sha256:d2a8bd3e87d464ffbb004e8bc6259e2be81b41369c4d934553d492be3399d7df, sha256:dd927a0b7b2f56f21c1313b644a4950cef766184735cdc351a5c395f4bb8ec47) with a 20-minute timeout, 2 CPUs and 8 GB RAM.
Network goes only through an allowlist proxy that admits the four ecosystems' live official registries,
toolchain hosts and GitHub; every refused host is logged. One attempt, no manual fixes. The number of
containers building at once varied during CORE (2, 3, 6, 8, then up to 12; A9, A11, A11b) and TIMEOUT rows were rebuilt at
parallel 2 (A12); see Limits.

Statistics (pre-registered; the analysis code was frozen before any build result existed).
H1 (PREREG, verbatim): "ERA build success decreases with age in every ecosystem (Cochran-Armitage trend test
per ecosystem, alpha 0.0125, Bonferroni over 4)." As computed by the frozen analysis code: per ecosystem, ERA
rows are grouped by age in years (analysis year minus cohort year) with the age as the score; z is the
Cochran-Armitage statistic, negative when success falls with age; p = P(Z <= z) under the standard normal,
i.e. one-sided in the direction of decline; an ecosystem's test rejects when p < 0.0125; H1 is supported only
if all four reject. A test with no variance (all rows built, or none) is not computable. H2: maximum-likelihood fit of
S(age) = exp(-ln2 * age / T) per ecosystem on ERA rows, bootstrap 95% CI with 1,000 resamples by repository.
H3: two-sided Fisher exact test.

## 4. Build recipe (one per ecosystem, fixed)

Recipe revisions in these data: halflife-recipe-v2e, halflife-recipe-v2g, halflife-recipe-v2i, halflife-recipe-v2j.

- Python: uv venv with the interpreter the project declares (requires-python or .python-version), else the
  newest stable (CPython 3.13); `uv pip install .` (or `-r requirements.txt` when no package is declared);
  success = install exits 0 and, when a package is declared, `python -c "import <top package>"` exits 0.
- Node: Node version from .nvmrc or an exact engines.node, else current LTS; the declared package manager
  (packageManager field or lockfile; pnpm and yarn through corepack, version pinned from the lockfile when
  undeclared), else `npm ci` with a lockfile or `npm install`; then `npm run build` when a build script
  exists; success = all steps exit 0.
- Go: `go build ./...` with the toolchain go.mod declares (toolchain directive honoured); GOPATH-mode build
  for legacy Go.
- Rust: `cargo build --locked` when Cargo.lock exists, else `cargo build`; toolchain from rust-toolchain,
  else stable. Pre-Cargo Rust is not attempted and recorded as TOOLCHAIN-EOL.

All recipes run in the directory of the ERA-defining manifest, initialise git submodules through the proxy, and
use the declared toolchain if its standard version manager can still install it today, otherwise the newest
stable. The base image carries a generic native toolchain (gcc, g++, make, cmake, pkg-config, file, git,
Python headers, OpenSSL headers) and nothing project-specific.

## 5. Pre-registered hypotheses and kill rule (verbatim from PREREG)

- H1: ERA build success decreases with age in every ecosystem (Cochran-Armitage trend test per ecosystem,
  alpha 0.0125, Bonferroni over 4).
- H2: ecosystems differ in half-life. Fit S(age) = exp(-ln2 * age / T) per ecosystem by maximum likelihood on
  ERA snapshots; report T with a bootstrap 95% CI (1,000 resamples by repo). H2 is supported if the CIs of the
  best and worst ecosystem do not overlap.
- H3 (secondary): among the 2023-2024 cohorts, repos with AI-assist markers (a Co-Authored-By commit trailer
  naming one of six AI coding assistants, or an instruction file of one of them at NOW; the exact frozen list
  is in the pre-registration) have lower NOW build success than those without (two-sided Fisher exact test,
  alpha 0.05). The marker list is frozen there.
- Everything else (failure-class shares, star-count effects, per-year tables) is descriptive or EXPLORATORY
  and labelled so.
- Kill rule: the pilot must place at least 80% of failures in a non-OTHER class, or the taxonomy is redesigned
  before the full run.

H3 measures build success, not the survival of AI-authored lines of code (cf. the line-survival report cited
in section 10).

## 6. Results

### 6.1 H1 and H2 (confirmatory)

| ecosystem | n (ERA) | H1 z | H1 p = P(Z <= z) | H1 verdict (alpha 0.0125) | half-life T | bootstrap 95% CI |
|---|---|---|---|---|---|---|
| python | 900 | 0.50 | 0.693 | NOT SUPPORTED | 6.49 years | 5.84 to 7.14 years |
| node | 900 | 5.37 | 1.000 | NOT SUPPORTED | 5.91 years | 5.34 to 6.50 years |
| go | 897 | -12.05 | 9.17e-34 | SUPPORTED | 6.47 years | 5.92 to 7.09 years |
| rust | 900 | -6.16 | 3.74e-10 | SUPPORTED | 4.33 years | 3.95 to 4.72 years |

H1 per ecosystem: Python NOT SUPPORTED (n = 900, z = 0.50, p = 0.693);
Node NOT SUPPORTED (n = 900, z = 5.37, p = 1.000);
Go SUPPORTED (n = 897, z = -12.05, p = 9.17e-34);
Rust SUPPORTED (n = 900, z = -6.16, p = 3.74e-10).
H1 overall: NOT SUPPORTED (at least one ecosystem test does not reject at alpha 0.0125).

A half-life is reported as "no decay detected within the observed range" when every ERA row in that
ecosystem built (the likelihood has no finite maximum); the observed age range is stated with it.

H2: SUPPORTED (best python, worst rust).

Model caveat. The pre-registered model S(age) = exp(-ln2 * age / T) assumes that success falls at a steady rate
with age. Go and Rust decline; Python and Node do not (H1 z = 0.50 and 5.37; section 6.3). For Python and Node, T
is the half-life of the best-fitting exponential, a summary of the overall success level, not a measured rate of
decay, and H2's comparison of T across ecosystems should be read with that in mind. The model was fixed before
any result and is reported as fixed.

### 6.2 H3 (secondary)

AI-marker repos built 174/369 = 47.2%; others built 115/205 = 56.1%; Fisher exact two-sided p = 0.045. Verdict: SUPPORTED.

A24 (after the fit): one marker row (convex/convex-backend) is marked only by a human co-author whose first name
matches the frozen list; with it counted as other, 174/368 against 115/206, Fisher two-sided p = 0.056, which
does not reject at 0.05. A second row (mckaywrigley/chatbot-ui) rests on a trailer account named
chatgpt-ai-user and is left as classified. The pre-registered verdict is reported as computed; its support rests
on one misclassified row.

Limits of H3. The test is unadjusted: it does not account for ecosystem, cohort year or package manager, any of
which can differ between marker and other repositories. The Node pnpm recipe defect described in 6.7 falls on
NOW rows (94 of the 118 affected builds) and so can enter this comparison. H3 is an association between a
marker and build success, not an effect of AI assistance.

### 6.3 Descriptive: ERA success by age

| ecosystem | age (years) | built / attempted |
|---|---|---|
| python | 2 | 47/75 = 62.7% |
| python | 3 | 30/75 = 40.0% |
| python | 4 | 26/75 = 34.7% |
| python | 5 | 28/75 = 37.3% |
| python | 6 | 25/75 = 33.3% |
| python | 7 | 32/75 = 42.7% |
| python | 8 | 37/75 = 49.3% |
| python | 9 | 41/75 = 54.7% |
| python | 10 | 36/75 = 48.0% |
| python | 11 | 38/75 = 50.7% |
| python | 12 | 32/75 = 42.7% |
| python | 13 | 34/75 = 45.3% |
| node | 2 | 20/75 = 26.7% |
| node | 3 | 26/75 = 34.7% |
| node | 4 | 23/75 = 30.7% |
| node | 5 | 26/75 = 34.7% |
| node | 6 | 23/75 = 30.7% |
| node | 7 | 26/75 = 34.7% |
| node | 8 | 35/75 = 46.7% |
| node | 9 | 33/75 = 44.0% |
| node | 10 | 33/75 = 44.0% |
| node | 11 | 35/75 = 46.7% |
| node | 12 | 41/75 = 54.7% |
| node | 13 | 43/75 = 57.3% |
| go | 2 | 51/75 = 68.0% |
| go | 3 | 54/74 = 73.0% |
| go | 4 | 51/75 = 68.0% |
| go | 5 | 45/75 = 60.0% |
| go | 6 | 53/75 = 70.7% |
| go | 7 | 58/75 = 77.3% |
| go | 8 | 46/74 = 62.2% |
| go | 9 | 15/74 = 20.3% |
| go | 10 | 11/75 = 14.7% |
| go | 11 | 17/75 = 22.7% |
| go | 12 | 13/75 = 17.3% |
| go | 13 | 20/75 = 26.7% |
| rust | 2 | 37/75 = 49.3% |
| rust | 3 | 31/75 = 41.3% |
| rust | 4 | 28/75 = 37.3% |
| rust | 5 | 29/75 = 38.7% |
| rust | 6 | 30/75 = 40.0% |
| rust | 7 | 24/75 = 32.0% |
| rust | 8 | 31/75 = 41.3% |
| rust | 9 | 28/75 = 37.3% |
| rust | 10 | 19/75 = 25.3% |
| rust | 11 | 19/75 = 25.3% |
| rust | 12 | 22/75 = 29.3% |
| rust | 13 | 0/75 = 0.0% |

### 6.4 Descriptive: success by ecosystem and snapshot

| ecosystem | snapshot | built / attempted |
|---|---|---|
| python | ERA | 406/900 = 45.1% |
| python | NOW | 480/900 = 53.3% |
| node | ERA | 364/900 = 40.4% |
| node | NOW | 358/900 = 39.8% |
| go | ERA | 434/900 = 48.2% |
| go | NOW | 656/900 = 72.9% |
| rust | ERA | 298/900 = 33.1% |
| rust | NOW | 510/900 = 56.7% |

### 6.5 Secondary, descriptive: builds whose first named artefact is absent (A18)

Pre-specified in A18 before any CORE outcome was read; no hypothesis test, no threshold, and no change to any
verdict above. For each failed build of population P (a NOW or ERA receipt that failed for a reason other than
TIMEOUT, OOM or a missing manifest, refused no host, and carries no proxy-refusal message), the first registry
artefact the log names was looked up once, after the analysis, at the ecosystem's official registry from an open
network; every response is saved and hashed in the dataset. The registry is read as it is at probe time, not at
build time; both times are recorded per row. An artefact that is absent is counted as EXISTED only if a lockfile
at that commit names the official registry as its source, or the registry or Go checksum database keeps a public
record that it was published. Only ABSENT with EXISTED may be called lost; ABSENT without EXISTED may never have
been public. This section counts builds whose first named artefact is absent; it does not say that a build
failed because of it.

Outcomes of the lookup by ecosystem and snapshot (rows of P; one lookup pass, 183 lookups, 60 distinct saved responses):

| ecosystem | snapshot | rows of P | UNNAMED | OFF-REGISTRY | NOT-APPLICABLE | CHECKSUM-DB | NAME-ABSENT | VERSION-ABSENT | YANKED | PRESENT | UNPROBED | ABSENT with EXISTED |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| go | ERA | 15 | 15 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| go | NOW | 13 | 13 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| node | ERA | 9 | 4 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 3 | 1 |
| node | NOW | 8 | 4 | 0 | 0 | 0 | 1 | 3 | 0 | 0 | 0 | 0 |
| python | ERA | 156 | 146 | 0 | 0 | 0 | 2 | 7 | 0 | 1 | 0 | 0 |
| python | NOW | 94 | 89 | 0 | 0 | 0 | 1 | 4 | 0 | 0 | 0 | 0 |
| rust | ERA | 58 | 0 | 16 | 0 | 0 | 2 | 0 | 0 | 4 | 36 | 1 |
| rust | NOW | 5 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 0 |

Primary figure (ABSENT with EXISTED among the DEP-MISSING NOW rows of P, as a share of all NOW builds in the
ecosystem and cohort year): 0 in every ecosystem and cohort year. Beside it, all classes: ERA rows hold 2
builds whose first named artefact is absent and is known to have existed (one Node, one Rust, both DEP-MISSING
NAME-ABSENT); NOW rows hold none.

Ecosystems labelled EXPLORATORY because unnamed rows exceed half of their DEP-MISSING rows of P: Go (ERA 15 of
15, NOW 13 of 13), Node (ERA 4 of 6, NOW 4 of 5) and Python (ERA 146 of 148, NOW 89 of 90). Rust is not (ERA 0
of 22, NOW 0 of 1). For three of the four ecosystems the log-pattern step names an artefact in few failed
builds, so the figure for them says little either way. Limits fixed in A18: (i) the farm allowlist hides losses on hosts outside it, so the figure
is a lower bound for the listed registries only; (ii) ecosystems outside the study are not covered; (iii) the
first match names one artefact per build, not all, and in a log whose class is not a dependency class it may be
incidental (the table by class shows this); (iv) the EXPLORATORY rule above; (v) farm tool versions differ from
the versions the message patterns were captured with, so an unlisted wording is missed (lower bound); (vi)
descriptive only. Any further archive lookup is EXPLORATORY and labelled so.

### 6.6 Secondary: builds whose declared runtime floor was past end-of-life (A22, A23)

Pre-specified in A22 before any fit, outcome count or analysis; A23 moved the verdict to NOW rows after the
exposure counts, not outcomes, were seen (in ERA rows 783 of 806 declared floors were already past end-of-life,
leaving no comparison arm). A row is EXPOSED when the lowest runtime version its manifest declares (Python
requires-python or .python-version, Node engines.node, Go the go.mod go line) was past end-of-life on the public
calendar before the A22 reference date (2026-11-09, the start of wave 0); Rust is not applicable. Statistic per ecosystem: Mantel-Haenszel risk difference in
success share, NOT-EXPOSED minus EXPOSED, stratified by cohort year, Sato 95% interval; TOOLCHAIN-EOL rows
excluded; an ecosystem is powered with at least 20 rows per arm. TRACKS needs at least two powered ecosystems
with a difference of 10 points or more and a lower bound above 0; DOES NOT TRACK needs at least two powered
ecosystems and every powered one below 10 points at its upper bound; fewer than two powered ecosystems is
UNDERPOWERED.

As printed by the comparison tool: "verdict_NOW_rows=DOES NOT TRACK A22_ERA_rule=UNDERPOWERED".

| ecosystem (NOW rows) | NOT-EXPOSED n | EXPOSED n | MH risk difference | Sato 95% interval |
|---|---|---|---|---|
| python | 159 | 199 | -0.118 | -0.218 to -0.018 |
| node | 206 | 161 | -0.133 | -0.235 to -0.030 |
| go | 426 | 367 | -0.025 | -0.082 to 0.032 |

The differences are negative: in these NOW rows, builds whose declared floor was past end-of-life built at least
as often as the others. Of all NOW failures in the three ecosystems (excluding TOOLCHAIN-EOL), 210 of 1166 (18.0%,
exact 95% interval 15.8% to 20.3%) were EXPOSED. ERA rows (descriptive, UNDERPOWERED): Python 14 and Node 9
NOT-EXPOSED rows contribute; Go ERA has none. Most rows declare no floor the tool reads (UNDECLARED: 1,894 of
2,700 ERA and 1,182 of 2,700 NOW rows), so the comparison describes declaring projects only; a stale floor in a
NOW commit is a declaration in a project that is still changing, a different thing from an old project.

One reading consistent with this, not tested here: our recipes install the declared version where the version
manager still can and fall back to the newest stable release otherwise, so an old floor alone may rarely decide
the build. The wording rule holds throughout: these are
builds whose declared runtime floor was past end-of-life, not builds that failed because of it.

### 6.7 EXPLORATORY: age patterns (post-hoc, chosen after the fit)

EXPLORATORY. This subsection was written after the fit to explain three patterns in section 6.3; it tests
nothing and changes no verdict. Go: the drop between age 8 (46 of 74 built) and age 9 (15 of 74) coincides
with projects that predate Go modules (legacy-go rows: 11 at age 8, 54 at age 9, all 75 at ages 10 to 13) and
with TOOLCHAIN-EOL failures (7 at age 8, 42 at age 9); it is a step at the module boundary of August 2018, not
a gradual decline. Rust: age 13 (0 of 75 built) is the 2013 cohort, which predates Rust 1.0 (May 2015); 20 rows
have no Cargo.toml and are not attempted by design. Node: success rises with age, but plain npm builds succeed
at a similar share in every age band (ERA 50%, 45% and 55% for ages 2-5, 6-9 and 10-13) (package-manager labels come from the build logs, not the receipts); younger cohorts hold
more pnpm and workspace projects, which build less often. In 118 pnpm builds (24 ERA, 94 NOW) the log shows the
package-manager binary missing for a nested script ("pnpm: not found", or a monorepo runner that cannot find
the package-manager binary). That is at least in part a property of our Node recipe, so the Node age gradient
is confounded with package-manager composition by cohort. Testing it needs a new recipe revision and a new
pre-registration; it is not done here.

H3 composition (frozen marker classification, before the A24 correction; EXPLORATORY, post-hoc, chosen after the fit; it changes no verdict, and H3's pre-registered
verdict in 6.2 stands as printed). Marker against other repositories built, by ecosystem: Go 52/70 against 49/74,
Node 32/115 against 15/34, Python 48/89 against 22/47, Rust 42/95 against 29/50. Marker repositories are 31% Node
(115 of 369) against 17% (34 of 205) for the others, and Node builds least often. The direction differs by
ecosystem: marker repositories built more often in Go and Python and less often in Node and Rust. 20 H3 rows are
pnpm-defect rows (19 marker, 1 other), and all 20 failed; without them, marker repositories built 174/350 = 49.7%
against 115/204 = 56.4%. Two post-hoc checks: Fisher exact two-sided without the 20 defect rows, p = 0.135;
Cochran-Mantel-Haenszel stratified by ecosystem, p = 0.494 (0.554 with continuity correction), pooled odds ratio
0.88 (95% CI 0.62 to 1.26). The unadjusted H3 association is not robust to ecosystem composition or to the recipe
defect. (publish/exploratory/h3_composition.txt, h3_sensitivity.txt.)

## 7. Failure taxonomy (descriptive)

Classes are assigned mechanically from logs and receipts by a classifier whose rules and their order were
frozen before the run: TIMEOUT, OOM, NO-MANIFEST, refused-host DEP-MISSING, NETWORK, PACKAGE-MANAGER-MISMATCH,
MANIFEST-INVALID, TOOLCHAIN-EOL, TOOLCHAIN-UNAVAILABLE, NATIVE-BUILD-FAILED, RUNTIME-INCOMPAT, DEP-MISSING,
DEP-VERSION-CONFLICT, COMPILE-ERROR, OTHER; the first match wins.

| class | failures | share |
|---|---|---|
| DEP-MISSING | 858 | 23.2% |
| OTHER | 742 | 20.1% |
| COMPILE-ERROR | 724 | 19.6% |
| TOOLCHAIN-EOL | 345 | 9.3% |
| DEP-VERSION-CONFLICT | 273 | 7.4% |
| NATIVE-BUILD-FAILED | 235 | 6.4% |
| NO-MANIFEST | 173 | 4.7% |
| TOOLCHAIN-UNAVAILABLE | 78 | 2.1% |
| PACKAGE-MANAGER-MISMATCH | 65 | 1.8% |
| OOM | 60 | 1.6% |
| TIMEOUT | 57 | 1.5% |
| NETWORK | 47 | 1.3% |
| MANIFEST-INVALID | 21 | 0.6% |
| RUNTIME-INCOMPAT | 16 | 0.4% |

Of 3694 failures, 2952/3694 = 79.9% fall in a non-OTHER class. The kill rule was a gate on the
pilot only; set against the same 80% bar these data would be FAIL, which is descriptive and
gates nothing. 55 failed builds reached the 8 GiB memory cap (within 1 MiB) and
731 builds had at least one host refused by the allowlist proxy. Build wall-clock:
median 63 s, p95 695 s, total 320.2 h.

## 8. Amendments (all timestamped; A1 to A23 written before any analysis, A24 after it; thresholds never moved)

Hypotheses H1-H3, the alpha levels, the frozen repository list and the 80% kill-rule bar were not changed by
any amendment. A1 to A5 were written before the runs they affect. A7 is prospective. A6 and A8 were written after the
receipts they void had been produced, but before any result was read or analysed; A8 corrects A6's cause and
fixes the void rule from farm-health evidence (timestamps and the farm's own fetch step), not from build outcomes.

| id | what changed | original rule's verdict | amended rule's verdict |
|---|---|---|---|
| A1 (taxonomy redesign) | the first pilot (240 builds) placed 68/111 = 61.3% of failures in a non-OTHER class; four classes were added, regexes extended and the rule order fixed; generic recipe defects removed (base native toolchain, submodules, declared Node package manager, peak memory recorded) | FAIL (61.3% < 80%, first pilot) | PASS (99/110 = 90.0%, re-run pilot); on these data: FAIL |
| A1 outcome / OOM rule | a failed build whose peak memory is within 1 MiB of the 8 GiB cap is OOM, read from the receipt, not only the log | not reconstructable from receipts alone (needs the log-only classification) | 55 builds at the cap |
| R3 (iii) | registry.yarnpkg.com (Yarn's live official default registry) added to the allowlist before CORE; three first-pilot passes had failed only for it | UNTESTED: the original allowlist's verdict on CORE would need a re-run | as reported in section 6 |
| A4 | 32 rows whose depth-2 tree query failed but whose root manifest was confirmed at the ERA sha stay in the denominator (4 CORE); 8 Go rows where a root *.go marker won over a deeper go.mod build at the frozen root | no row moves under either reading; reported as footnotes | denominator unchanged |

The first-pilot receipts are kept and reported next to the re-run pilot.

A24 (2026-11-15, after the fit; the one amendment written after analysis): one H3 marker row is a human
co-author matched by first name; the frozen verdict is kept as computed and the corrected count is reported
beside it (section 6.2); third-party emails in the shipped marker file are redacted.

A5 (written before any CORE result was read) fixed the analysis date as the moment the last CORE receipt is
written; the analysis ran once on CORE at that point. A6 to A17 (written after farm faults, before any analysis) voided or rebuilt receipts on rules fixed by
farm-health evidence, not by build outcomes; they are described under Limits. A12's TIMEOUT rule was written
after early failure-class counts had been visible on the progress page (disclosed under Limits).

## 9. Limits

CORE first, FULL later (A5). This paper reports CORE only. FULL runs after CORE, cell by cell, on the same
recipe revision, and is not analysed, counted or summarised while it runs, because a partial FULL is not a
random sample of the population. FULL status at the time of writing: not started. FULL will be analysed
once, when its last receipt is written, and reported as a replication update; no FULL number appears here.

Farm proxy defects and void receipts (A6 to A15). Every build begins with the farm's own git fetch through the
farm's allowlist proxy. Four proxy problems were found during CORE, in this order. In each case the
allowlist, the allow and refuse decisions, the proxy log format, the build recipe, the classifier, the images
and the per-build limits were unchanged, and each receipt's recipe id names the revision that served it
(halflife-recipe-v2e 1322, halflife-recipe-v2g 319, halflife-recipe-v2i 60, halflife-recipe-v2j 5499).

1. Descriptor limit (A8, fixed in rev 2f). From 2026-11-10 morning UTC, builds began to fail at the first
fetch step with a proxy timeout, before any repository code was fetched; the progress monitor flagged the run
of failures. Inspected at 15:38Z, the proxy held 2,675 open descriptors and 2,679 threads. It used select,
which fails for any descriptor numbered above 1023, and never timed out a client that connected and sent
nothing. Reproduced in the proxy image with 1,500 idle client sockets (rev 2e failed to carry a new tunnel);
fixed with selectors, socket timeouts, a 60 s header limit and the upstream socket closed on every error path.
Every CORE receipt started at or after 2026-11-10T07:07:50Z and before the rev 2f proxy started is void,
whatever its outcome, successes included: 280 receipts moved first (void list sha256
9001d54b35ba0544eb8435d9d9ffad948a71f73c7d2bd21c034c57307a2b185f) and 28 more (void list sha256 96cdce19f416d46534d471631a5bce01aa483412691ee48f628553170e0c3cb9).

2. Per-line log reopen (A10, fixed in rev 2g). Under rev 2f at six parallel builds, containers sat idle for 8
to 11 minutes while the proxy did not answer a new CONNECT within 40 s. Every connection appended one log line
by reopening the bind-mounted log file under a global lock; measured inside the proxy container, one append
cost 0.207 s at 8.5 MB, so the proxy carried only a few connections per second. This throttle existed in every
earlier revision and is the likely driver of the descriptor pile-up in defect 1. Reproduced with 400 tunnels
from 40 threads; fixed with one writer thread that keeps the log open. All receipts written under rev 2f are
void whatever their outcome (23 receipts, files prefixed v2f__; void list sha256
e731dc9379927fbe2ad4a54ecdee60046f41b57da6ea218ce37addcce1efd760).

3. Single-process ceiling (A12, changed in rev 2h). Under rev 2g at eight parallel builds the build VM was 89%
idle while the single proxy process ran at 70 to 137% of one core: builds waited on downloads. Checked with 64
parallel 5.8 MB registry downloads; rev 2h runs 8 worker processes on one listening socket with one log writer
(all 64 returned the full size in 18 s). Rev 2g carried every connection correctly, only slowly, so its
receipts are not void.

4. Log volume and a faulted rev 2h instance (A13, A14; revs 2i and 2j). At twelve parallel builds the batch
runner was pinned on one core: every finishing build parsed the whole live proxy log, which had grown to
857 MB because builds whose lockfiles name a registry host outside the allowlist retried it in a tight
loop. Rev 2i logs an identical attempt at most once per 0.2 s per proxy worker; rev 2j reads the log from
a bisected offset 30 s before the build instead of from the start. Neither changes an allow or refuse
decision. Three receipts under rev 2h then showed a fetch-step proxy fault (likely the log pipe filling
during such a retry storm; inferred, not reproduced). Under the rule fixed in A8, a fetch-step fault voids
every receipt of that proxy instance: all receipts under rev 2h are void whatever their outcome
(307 receipts, files prefixed v2h__; void list sha256 1795dc22715eda2d48baba8a494b27cd51cdc5d8a9a36f7845e2362b84c58dfe).

One receipt with no log file is void as incomplete (1 receipt; part file void/core_void_incomplete/receipts.jsonl,
sha256 058a01bf996f2f3a1809c82dcaacf36f50b80e65206bd67272c4f57a5a9f5ec5). Each voided row was rebuilt once under a later revision and the rebuild is
that row's receipt in the analysed data. The void receipts are published unchanged in separate, labelled parts
of the dataset (`void/`, one part per void list) and are never pooled with the analysed rows. By the
amendments the void total is 639 receipts in five parts (280 first set + 28 more under A8 + 23 under rev 2f
+ 307 under rev 2h + 1 incomplete); the published void parts hold 639.

Per-revision agreement (A15). Farm revision and parallelism changed during CORE while the batch ran cell by
cell, so revision is partly confounded with cohort and ecosystem. For each of revs 2g, 2i and 2j, 60 valid
receipts (all, if fewer), chosen by sha256 of "A15|" and the file name, were rebuilt once at parallel 2
under the final revision. Rev 2g: 60 of 60 agreed on success or failure, stands (95 % or more agree).
Rev 2i: 60 of 60, stands (95 % or more agree). Rev 2j, the revision of most receipts: 55 of 60
(exact 95% interval 81.6% to 97.2%), reported as the farm's measured repeatability; no row is replaced.

Revision sensitivity (A15, secondary; never replaces the headline). (a) The pre-registered model with recipe
id as a fixed effect: no verdict changed. (b) The pre-registered model on rev 2j receipts only, run only if
every cell has at least 30 of them: v2j-only fit not run: 11 cells hold fewer than 30 v2j receipts. Result: no hypothesis verdict changed under either sensitivity fit.

Registry-alias secondary (A13, pre-specified; disclosed as written after refused-host names were seen in the
proxy log). The allowlist was not changed; the primary analysis counts a build that needs a non-listed host
as DEP-MISSING. Every receipt whose refused hosts are a non-empty subset of the official npm registry alias
and two mirrors of it is to be rebuilt once with those three hosts allowed. Not run in this release: the
rebuild needs a proxy configuration that has not been approved; no A13 figure appears here.

Agreement check (A8, threshold fixed in A10 before any rebuild). The 1,338 Go receipts started before
07:07:50Z under rev 2e stand (16 of them were later replaced as rows of record by the A12/A16/A17 rebuilds
below: 4 TIMEOUT, 11 NETWORK, 1 COMPILE-ERROR with a proxy message; hence 1,322 rev 2e receipts among the rows of
record): none of their logs has a fetch-step proxy fault or other proxy-failure signature.
The throttle of defect 2 still slowed their downloads, and a degraded proxy could in principle have dropped a
single download without leaving such a signature. A random sample of 100 of them (seed 20261110, drawn from
the sorted file names, committed before CORE ended) was rebuilt under rev 2g or later: 100 of
100 gave the same outcome (success or failure) and 100 the same failure class. The rule:
at 95 or more of 100 the original receipts remain the rows of record; below 95, all 1,338 are rebuilt and the
rebuilds become the rows of record. Result of the rule: PASS (95 or more of 100; the original receipts remain the rows of record).

TIMEOUT rebuild (A12). Slowness can change only the TIMEOUT class. After CORE completed, every CORE receipt
classed TIMEOUT, under any revision, was rebuilt once under the final revision at parallel 2; the rebuild is
the row of record and the original is kept and published in its own labelled part, not void
(386 TIMEOUT receipts). Together with the A16 and A17 rebuilds below, 506 receipts were rebuilt (386 + 110 + 10);
their originals are in void/core_timeout_original/receipts.jsonl (sha256
7edf65f6e355035ee09b3beb1d2b55b548f3f23aa3ca23752144223f721bd0bc). Over all 506, 344 rebuilds have a different
outcome or failure class from the original (success counted as its own class); over the 386 TIMEOUT originals,
329 are no longer TIMEOUT. Disclosure: this rule was written after early failure-class counts
had been visible on the farm's progress page; it was fixed before any analysis.

Network and proxy-message rebuilds (A16, A17). Up to twelve builds shared one public address, so a registry or
code host could throttle or drop a connection for reasons unrelated to a repository's age. In the same pass as
the TIMEOUT rebuilds, every valid receipt classed NETWORK or whose log matches an HTTP 429 or rate-limit wording
(A16; 110 receipts), and every receipt whose log contains the client message "Proxy CONNECT
aborted" in any step, whatever its outcome (A17; 10 receipts), was rebuilt once at parallel
2 under the final revision; the rebuild is the row of record and the first receipt is published. The classifier
was not edited. Rebuild reasons per cell (a farm figure; a receipt selected for more than one reason counts once):

| cell | TIMEOUT (A12) | NETWORK or 429 (A16) | proxy message (A17) |
|---|---|---|---|
| go-2013 | 1 | 1 | 0 |
| go-2014 | 1 | 1 | 0 |
| go-2015 | 4 | 1 | 0 |
| go-2016 | 0 | 0 | 0 |
| go-2017 | 1 | 1 | 0 |
| go-2018 | 0 | 0 | 0 |
| go-2019 | 9 | 1 | 0 |
| go-2020 | 0 | 0 | 0 |
| go-2021 | 0 | 2 | 0 |
| go-2022 | 0 | 2 | 0 |
| go-2023 | 4 | 1 | 0 |
| go-2024 | 1 | 5 | 0 |
| node-2013 | 1 | 1 | 0 |
| node-2014 | 1 | 4 | 0 |
| node-2015 | 2 | 5 | 0 |
| node-2016 | 4 | 3 | 0 |
| node-2017 | 2 | 4 | 0 |
| node-2018 | 4 | 5 | 0 |
| node-2019 | 8 | 2 | 0 |
| node-2020 | 3 | 7 | 0 |
| node-2021 | 6 | 7 | 0 |
| node-2022 | 7 | 10 | 0 |
| node-2023 | 3 | 13 | 0 |
| node-2024 | 4 | 8 | 0 |
| python-2013 | 0 | 0 | 0 |
| python-2014 | 2 | 0 | 0 |
| python-2015 | 0 | 1 | 0 |
| python-2016 | 4 | 3 | 0 |
| python-2017 | 13 | 5 | 0 |
| python-2018 | 15 | 0 | 0 |
| python-2019 | 22 | 0 | 1 |
| python-2020 | 21 | 5 | 0 |
| python-2021 | 15 | 1 | 0 |
| python-2022 | 30 | 2 | 0 |
| python-2023 | 13 | 0 | 0 |
| python-2024 | 35 | 2 | 0 |
| rust-2013 | 0 | 1 | 0 |
| rust-2014 | 1 | 1 | 0 |
| rust-2015 | 2 | 0 | 0 |
| rust-2016 | 0 | 2 | 0 |
| rust-2017 | 6 | 0 | 0 |
| rust-2018 | 13 | 0 | 0 |
| rust-2019 | 12 | 0 | 0 |
| rust-2020 | 18 | 2 | 5 |
| rust-2021 | 21 | 0 | 4 |
| rust-2022 | 19 | 1 | 0 |
| rust-2023 | 26 | 0 | 0 |
| rust-2024 | 32 | 0 | 0 |
| all | 386 | 110 | 10 |

A17 decided when that client message is a proxy fault. The message means the proxy closed the connection during
the CONNECT handshake, which happens both when the proxy itself fails and when the upstream connection fails
after the allow decision. A fetch-step occurrence under rev 2i or 2j counts as an upstream transient, not a proxy
fault, only if five checks hold from logs alone (an allowed proxy-log row for that build and host; empty proxy
stderr; no other fetch-step fault on the instance within 30 minutes and at most one per 1,000 receipts it
served; rows from at least two other clients within 60 s; no thread sample above 1,000). Fetch-step
occurrences: 1; all 1 met C1 to C5 and were rebuilt as upstream transients; none voided a proxy instance. Occurrences inside a build tool's own downloads (a farm
figure): 9. Deviation from the letter of A8, disclosed: read literally, A8 would have
voided at least 2,390 receipts (every receipt started at or after the 02:39Z clean audit on 2026-11-11).

Parallelism varied during CORE: 2 and 3 containers at first, 6 from A9, 8 from A11 and up to 12 from A11b, with per-build limits
unchanged (2 CPUs, 8 GiB, 1,200 s). After CORE the VM kernel log was checked for out-of-memory kills (A9);
any kill voids every receipt overlapping it by 60 s either side. Going forward, a fetch-step proxy fault
under rev 2g or later voids all receipts from the previous clean proxy sample to the proxy restart, unless it
meets the five A17 checks above; three or more receipts carrying the message within 60 s with no fetch step
completing in that window stop the batch. The
frozen failure classifier has no pattern for the proxy timeout message; it was not edited, so any such fault
outside a voided set would be counted as OTHER.

Other limits. Four ecosystems only; today's toolchains and today's registries (a package deleted since the snapshot is a
failure by design); one attempt with no manual fixes; stars as a popularity proxy; a generic base image that
lacks project-specific system libraries; the build-success criterion for Python includes an import check but
no test suite for any ecosystem. Literature search: after a serial rerun on 2026-11-12, cells that still
could not be queried are UNTESTED: for archive loss 10 (dblp 4, web 4, GitHub issue search 2), for end-of-life
calendars 8 (dblp 4, web 4), for repeated-wave rebuilding 10 (dblp 4, web 4, Semantic Scholar 2).

Log retention (A19). One of the 7,200 CORE receipts (nicocha30/ligolo-ng, ERA) has no retained log. On this host
its log file was removed within seconds of being written, in all six builds of that row, including two
diagnostic runs. The cause is unknown. The receipt keeps its fields, and its sha256 of the full log text, which
was computed in the same process. It counts in every figure that uses receipt fields only. It is excluded from
every log-reading step (the A8 and A15 samples, the A12/A16/A17 text selection, A18) and cannot be re-classified
from text.

Future work (A20, notarised 2026-11-12). The same 7,200 CORE rows (repository, commit and snapshot label) are
planned to be rebuilt as a whole once per quarter under the wave-0 recipe (rev 2j), limits, allowlist, classifier
and rebuild rules. This report is wave 0. Wave 1 is planned to start between 2027-02-08 and 2027-02-22, with later
waves about every 13 weeks. Each wave's receipts will be hashed before any share is computed. A wave that is not
run, or runs late, will be reported as missed or late. This is a plan, not a result.

### What we got wrong on the way

Each item below was found during CORE and fixed before any analysis; none moved a threshold.

- A6: we blamed the faults on the host going to sleep (standby), because a sleep window lined up with them, and voided
  280 receipts on that basis. Wrong: faults went on with the host awake. The cause was the proxy.
- A6 also miscounted (126 faults; 124 by its own literal test plus 2 with a second step, A7), and its first
  wording guessed a cause for the one receipt with no log; the cause is not known.
- A7: our first fault test would have missed faults in logs with more than one farm step; reworded.
- A8: we then named the proxy's descriptor limit as the cause. True but secondary: A10 found the main driver
  was the proxy reopening its log file for every connection, which made it slow enough to pile up.
- A8 to A10: the fix in rev 2f still had the slow log, so all rev 2f receipts were voided too.
- A9, A11, A11b: we raised parallelism from 3 to 12 during the run, so farm load is not constant across
  cells (addressed by A15).
- A12: the proxy was one process and became the bottleneck; and the TIMEOUT rebuild rule was written after
  early failure-class counts had been visible on the progress page.
- A13: builds stuck retrying a non-listed npm mirror filled the proxy log, slowing every finishing build;
  the registry-alias secondary was written after those host names had been seen.
- A14: our audit tool matched only the long form of the proxy fault message and missed three faults under
  rev 2h for about two hours; all rev 2h receipts were then voided.
- A15: changing the farm mid-run confounds farm revision with cohort and ecosystem; the per-revision
  agreement samples and the two sensitivity fits were added for that reason.

## 10. Related work

Build decay of past snapshots has been measured before, notably for Java (Tufano et al. 2017; Maes-Bermejo
et al. 2022). This study differs in design: a pre-registered, paired ERA/NOW rebuild in four
ecosystems under one fixed recipe each, with every build's outcome in a signed receipt. The works below
border that design; some search cells were not reachable (see Limits).

Dependency selection. Mahmud, Rahman and Shahriyar (2026, arXiv 2610.41263) show for PHP that the dependency
selection policy (versions current today versus versions released by the project's date) changes whether old
projects pass their tests. Our policy is the same for every cohort: a lockfile or checksum file at the
snapshot (package-lock, pnpm-lock, yarn.lock, go.sum with go.mod, Cargo.lock with --locked) fixes versions
where present; otherwise, and for every Python build (section 4 reads no Python lockfile), the resolver picks
from the registry as it is at build time. No release-date selection
is applied, so older cohorts without lockfiles resolve against today's registry.

- Sulir and Poruban (2017), "A Quantitative Study of Java Software Buildability", arXiv 1712.01024: 7,264 Java
  repositories, 38% fail to build; one ecosystem, one point in time.
- Sulir, Poruban and Chodarev, "Local Software Buildability across Java Versions (Registered Report)",
  arXiv 2408.11544 (ESEM 2024 registered report): a protocol to build Java projects under JDK 6 to 23, with
  the hypothesis that failures grow with Java version; the arXiv record reports no results.
- Tufano, Palomba, Bavota, Di Penta, Oliveto, De Lucia and Poshyvanyk (2017), "There and back again: Can you
  compile that snapshot?", Journal of Software: Evolution and Process 29(4), e1838, doi:10.1002/smr.1838:
  100 Apache Maven projects, 219,395 snapshots; on average 38% of a project's history compiles today.
- Maes-Bermejo, Gallego, Gortazar, Robles and Gonzalez-Barahona (2022), "Revisiting the building of past
  snapshots - a replication and reproduction study", Empirical Software Engineering 27(3), 65,
  doi:10.1007/s10664-022-10117-6: replication of the above.
- Maes-Bermejo, Gallego, Gortazar, Robles and Gonzalez-Barahona (2024), "Testing the past: can we still run
  tests in past snapshots for Java projects?", Empirical Software Engineering 29(5), 127,
  doi:10.1007/s10664-024-10530-z: 86 Java projects; building from source is the main obstacle to running
  past tests.
- Solarin (2026), "It's Not Just Timestamps: A Study on Docker Reproducibility", arXiv 2602.17678: 2,000
  GitHub repositories with a Dockerfile; buildability of container images at one point in time.
- "Understanding Build Reproducibility in the F-Droid Ecosystem" (2026), arXiv 2607.01890: 83% of 18,904 app
  versions rebuild; bitwise reproducibility in one ecosystem.
- Nix reproducibility studies (2024, arXiv 2402.00424; EMSE 2026): bitwise reproducibility of Nix packages.
- "An Empirical Study on the Survival Rate of GitHub Projects" (MSR 2022): activity survival, not buildability.
- "Assessing OSS Survivability using Kaplan-Meier" (2024): activity survivability versus contributors and
  popularity.
- Causari Survival Report #8 (Zenodo 23892452, 2026): survival of lines from AI-tagged commits in 59
  repositories; line survival, not build success.
- "Maintenance Signals in AI-Assisted GitHub Repositories: Evidence from GenAI Adopters" (SSRN 7113578, 2026):
  maintenance activity, not builds.
- Pimentel et al. (2019), Jupyter notebook reproducibility; ICSE artifacts study (2025, arXiv 2601.02066);
  "Temporal Dependency Archaeology" (R, 2026); "To Pin or Not to Pin" (Zenodo 22271234, 2026): executability
  or rebuildability in single domains.
- MSR 2017, "Empirical Analysis of Build Failures in the Continuous Integration Workflows of Java-Based
  Open-Source Software", and the Java OSS Travis-CI build failure dataset (Zenodo 1745638): contemporaneous CI
  failures, not decay.

## 11. Data availability

Every build attempt is one row of `receipts.jsonl` (repository, commit sha, snapshot, recipe, toolchain,
image digest, exit code, duration, failure class, refused hosts, peak memory, log sha256), documented in
`DATA_README.md`. Each ecosystem-year cell of `receipts.jsonl` has its own DSSE attestation
(`cells/<ecosystem>_<year>.dsse.json`) over that cell's exact rows, as the pre-registration promises.
`MANIFEST.sha256` (sha256 687e1b345642aa79d174a6de11a7774481711e4b6e0417fc17e933a5c0ff72b8) lists every file, the cell attestations included; one DSSE
attestation over it is signed by keyid 1c8554a8d693dec7a62e73879acf41298629283718302584134b7034a13007f8. `package.py verify` checks the manifest
attestation with the attestation format's reference verifier (v1.4) and every cell attestation. The frozen
repository lists, their notary hashes, the pre-registration, its amendments, the recipes and the analysis
code are released with the data at https://github.com/ripplarity/halflife-wave0.

## Unverified, not cited

- "Local Software Buildability across Java Versions" as an EASE 2026 journal-first paper: the arXiv record
  (2408.11544) carries no journal reference; the venue was seen only in search summaries. Cited above as the
  arXiv registered report.
- "Effects of Artifact Age on Maven Dependency Resolution" (TU Delft bachelor project): author and record not
  confirmed on the repository page.
- A study of containerized bioinformatics tools 2021-2025 (50 of 195 rebuild): seen only in a blog summary; the
  primary paper was not identified.
- A decade-of-snapshots study of nixpkgs rebuildability: not matched to a specific record.
- Figures quoted for Solarin (2026) in search summaries were not checked against the paper text and are not used.
