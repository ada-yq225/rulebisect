# Changelog

## 0.5.0 — From one failure to a regression workflow

- Guided initialization collects a task, explicit check choice, optional setup and model. Repository manifests provide suggestions; commands are never inferred and executed automatically.
- Save, list and remove cases without editing JSON. Existing tasks remain in the suite; generated verifiers are protected, configuration writes are atomic and removing cases preserves files.
- Check every setup/verifier on independent frozen snapshots without Codex. A combined offline report separates behavior failures from infrastructure problems before spending model quota.
- Select case ids for smaller comparisons, with exact planned calls and prominently disclosed omitted cases in JSON, HTML, Markdown and issue summaries.
- Added a bilingual workflow guide, current public demand evidence and focused onboarding/suite regression coverage.
- Single verifier reports now identify the runner as verifier-only instead of implying a model execution.

## 0.4.2

- Doctor now validates experiment snapshots, verifier roles, instruction units, all suite cases and saved budgets using the same checks as actual experiments.
- Added doctor --offline, --config and --proposed for no-Codex input checks and exact comparison-budget validation.
- Added structured scope summaries and actionable notes; doctor never runs setup or verifier commands.
- Added configuration, no-execution and authentication-output privacy regression coverage.

## 0.4.1

- Added zero-model regression and scoped-fix demos, alongside instruction reduction.
- Added demo browser opening and unique default outputs so repeated trials do not collide.
- Added isolated-install instructions, contribution guidance and structured feedback templates.
- CI now checks all three scenarios and installs/runs the packaged wheel outside the checkout.

## 0.4.0

- Added instruction drafts and repeated before/after validation across independent task verifiers, with per-task regression/improvement results.
- Added no-model comparison planning, exact planned call counts, a shared reported-token cap, alternating arm order and frozen snapshots.
- Protect all suite verifiers in every arm and reject noisy/infrastructure-failed comparisons instead of declaring success.
- Added comparison reports, proposed diffs, per-arm token usage, history, latest report and latest reduction resume.
- Capture agent code diffs before the verifier runs so verifier outputs are not attributed to the agent.
- Added a reproducible fixture showing how a change can help one contract and break another.

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
