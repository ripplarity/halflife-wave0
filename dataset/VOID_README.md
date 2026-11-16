# VOID receipts (NOT part of any analysed denominator)

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
