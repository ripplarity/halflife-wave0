# HALF-LIFE dataset

Files: `receipts.jsonl` (one JSON object per build attempt), `MANIFEST.sha256` (sha256 of every file),
`MANIFEST.sha256.dsse.json` (one DSSE attestation, attestation format v1.4, predicateType
`<format base>/halflife/receipt/v1`; its subjects are the manifest and every file it lists), and
`cells/<ecosystem>_<year>.dsse.json` (one DSSE attestation per ecosystem-cohort cell, predicateType
`<format base>/halflife/receipt-cell/v1`; one subject `receipts.jsonl/ecosystem=<e>/year=<y>` whose sha256 is
over that cell's rows of `receipts.jsonl`, byte-exact, in file order; predicate `cell`, `builds`, `successes`).

Verify: `python attest_verify.py MANIFEST.sha256.dsse.json --key <published public key hex> --expect-keyid <published keyid> --check-subjects .`
(exit 0 = valid; 2 = bad signature or keyid mismatch; 3 = a file differs from what was signed).
Full check, cells included: `python package.py verify <dataset dir> --key <public key hex> --expect-keyid <keyid>`
(exit 0 = DATASET-VALID).

## receipts.jsonl fields

| field | type | meaning |
|---|---|---|
| repo | string | GitHub `owner/name` |
| year | int | GitHub `created_at` year of the repository (cohort), joined from the frozen list |
| snapshot | string | `ERA` (last default-branch commit on or before Y+1-12-31) or `NOW` (default-branch head at fetch time) |
| commit | string | 40-hex commit sha that was built |
| ecosystem | string | `python`, `node`, `go` or `rust`, defined by the manifest at the ERA snapshot |
| manifest_path | string | directory of the ecosystem-defining manifest (`.` = root); the build ran there |
| flags | string | e.g. `legacy-go`, `legacy-rust`; empty if none |
| recipe_id | string | recipe revision the build ran under |
| toolchain | list of string | toolchain versions actually used (FARM-TOOLCHAIN log lines) |
| image_digest | string | container image digest of the build farm |
| exit_code | int | exit code of the recipe (0 = built) |
| success | bool | `exit_code == 0` |
| duration_s | number | wall-clock seconds |
| failure_class | string or null | class from the frozen mechanical classifier (null on success) |
| refused_hosts | list of string | hosts the allowlist proxy refused during this build |
| mem_peak_bytes | int | peak memory of the build container (cap 8 GiB) |
| log_sha256 | string | sha256 of the full build log |
| started_utc | string | build start, UTC ISO-8601 |

Not published: the farm-internal container IP of each build (no analytic value). Build logs are not in this
folder; `log_sha256` binds each row to its log.
