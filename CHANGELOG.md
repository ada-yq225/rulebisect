# Changelog

## Skill / plugin 0.1.0 — Bundled Codex workflow

- Added a Codex-only Skill for experiment setup, independent acceptance checks, instruction reduction, proposed-rule comparisons and saved evidence review. Its entrypoint includes RuleBisect engine 0.7.0 and requires no pip install.
- Reuse existing session authorization; establish a model and execution budget before real Codex calls. Keep simulations, verification and model evidence distinct, and interpret finite observations without causal or global-minimality claims.
- Added a portable skills-only plugin manifest, original SVG icon, GitHub marketplace, standalone Skill ZIP, privacy description and bilingual installation/submission guide.
- Added fixed-allowlist vendoring and reproducible ZIP packaging, plus isolated launcher and extracted-package workflow checks. No MCP server, account collection, lifecycle hooks or automatic uploads.
- OpenAI public-directory submission awaits the owner's developer verification. GitHub distribution does not indicate OpenAI acceptance; the CLI engine remains version 0.7.0.

## 0.7.0 — An evidence workspace you can navigate

- Rebuilt local reports around the outcome and next action, with explicit Codex/simulation/verifier-only source badges and section navigation.
- Added light/dark themes and English/中文 interface controls. Original tasks, instructions, code and logs keep their original text; the report remains readable without JavaScript.
- Jump from task results to run evidence. Combine text search with outcome, phase and task filters; reset filters and see the live count of matching runs.
- Added colored code-diff lines, clearer evidence cards, accessible named controls, table captions and scoped headers. Styles, icons and scripts remain inline for offline use.
- Link only to existing local evidence artifacts. Reject symlink components, directory traversal, URL schemes, backslashes and unsafe URL delimiters before reading or linking saved evidence.
- Restyled aggregate sharing to match the reports while preserving the fixed metadata allowlist, no executable JavaScript and no links.
- Existing evidence can be refreshed with `rulebisect report PATH --open` without model calls. Added a bilingual report-navigation guide and privacy distinctions between full reports and aggregate summaries.
- Added three compact, reproducible workflow GIFs and static alternatives to the English and Chinese READMEs: no-code setup, failure reduction, and regression/fix/sharing.
- Animations use verified model-free CLI fixtures, display simulation labels, and include generator scripts, checked facts and automated GIF decoding/size validation. The light presentation matches the new report UI; these are edited constructed examples, not real account screen recordings.
- UI validation uses static HTML/DOM checks. Automated browser visual QA was not completed because localhost access was rejected by tool policy; this update does not claim fresh real-model validation.

## 0.6.0 — Define the result, debug the rules, share the outcome

- Define deterministic acceptance checks in JSON without writing Python: file existence/absence, text inclusion/exclusion, regex search and exact JSON Pointer values. Strict schema validation catches mistakes before configuration is written.
- Compile checks into self-contained, protected verifiers. Saved criteria stay fixed across fresh workspaces, reduction and proposed-instruction comparisons; editing the input JSON does not change them.
- Guided initialization offers file, text and JSON checks plus `@FILE` imports. Regression cases accept the same `--assertions` option as initialization.
- Export standalone offline summaries with `share`, using a fixed allowlist of outcomes and numeric aggregates. Tasks, instructions, code, filenames, case IDs, models, commands and logs are excluded. Exports refuse overwriting and stay outside the evidence directory.
- Reject unsafe/symlinked initialization paths; roll back generated verifiers if configuration creation fails. Deeply nested JSON and share-path symlink loops return actionable errors.
- Added a bilingual assertion/sharing guide, a complete output-contract fixture, installed-package coverage of the new workflow and a primary-source comparison that separates workflow differentiation from algorithmic novelty.

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
