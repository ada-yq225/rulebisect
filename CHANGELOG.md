# Changelog

## 0.3.0

- Added optional per-workspace dependency setup, init --setup, setup logs, and no-model environment checking.
- Stop before Codex when setup fails, times out or changes snapshot content; include setup in resume matching.
- Retain new non-ignored file diffs and deleted file content; exclude files created by setup and mark missing final newlines.
- Reject symlink ancestors in snapshot paths.
- Expanded regression coverage for setup isolation, failure accounting and file evidence.

## 0.2.0

- Added init, doctor, plan, check, resume and report commands; saved settings and automatic output paths.
- Added heading-section and whole-file reduction modes and override-aware instruction discovery.
- Added matching-snapshot resume with fresh baselines/confirmation, reported token stopping, fail-fast errors and interrupted attempt accounting.
- Added bilingual actionable reports, search/retained filtering, usage breakdown, inline code diffs, candidate patches and compact issue drafts.
- Fixed Python 3.11 report compatibility and normalized setup paths across macOS symlinked temporary directories.
- Expanded to 30 checks and exercised a Python coding fixture plus a negative control on actual local Codex.

## 0.1.0

- Initial paragraph reducer, independent verifier, protected files, bounded executions, deterministic demo and local reports.
