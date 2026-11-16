# Data kept privately
The raw registry responses of the A18 archive probe (analysis/out/archive_probe/responses/*.bin) are not shipped:
they contain package-maintainer email addresses. Each response's sha256 is recorded in
analysis/out/archive_probe/responses.jsonl; the raw files are available on request.
The unredacted AI-marker file is kept locally; markers/ai_marker.jsonl here has every email in trailer_lines
replaced by <redacted> (A24).
