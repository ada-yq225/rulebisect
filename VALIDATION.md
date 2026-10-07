# Validation — v0.3.0

Executed on macOS, 2026-10-07. Constructed fixtures; no real-world defect claim.

- 36 regression tests passed on Python 3.11.15, followed by three additional passing checks for invalid setup arguments, internal symlink ancestors and setup timeout (39 checks), followed by a passing large-file evidence regression (40 total checks).
- Wheel built and installed in a clean Python 3.11 virtual environment; installed CLI demo completed all 48 simulator executions.
- Setup success, failure and snapshot mutation tested. Failed or timed-out setup skips the agent and produces an inconclusive result.
- New/deleted file diffs, missing final newlines, ignored output and setup-created dependency exclusions checked; original source preserved.
- Two actual authenticated local Codex executions, CLI 0.159.2, requested model gpt-6.1-sol. A workspace setup command created an ignored dependency marker; Codex then created labels.py. Both independent verifier checks passed, so status was not_reproduced and reduction did not start.
- Both trials retained the newly created labels.py diff; setup output was excluded. No labels.py or dependency marker was written into the original repository.
- Reported input tokens: 92227; output: 522; cached input: 79104. Cached input is already included in input. No dollar cost inferred.
- Reproducible fixture: examples/new-file. Supply your available model explicitly. Raw logs remain outside this repository.
- Previous v0.2 passed all six GitHub CI jobs (Linux/macOS/Windows, Python 3.11/3.13): https://github.com/ada-yq225/rulebisect/actions/runs/37577224909. Current revision CI is recorded by GitHub after pushing.
- Setup does not freeze remote dependencies or external services. New ignored files are not recorded. Copies remain local workspaces, not containers.

# Earlier validation — v0.2.0

Executed on macOS, 2026-10-07. The tool is experimental; these are constructed fixtures, not reported real-world defects.

## Automated and installation checks

- 30 unittest checks passed on Python 3.11.15.
- Runtime modules parsed and executed on Python 3.11; repaired the v0.1 report f-string that depended on Python 3.12 syntax.
- Wheel built, installed into a clean Python 3.11 virtual environment, and installed CLI demo completed (five units reduced to two, 48 simulator executions).
- Installed `doctor` reported all checks passing, with zero model calls.
- Init/plan/check workflow exercised against the coding fixture; plan/check invoked no model.
- Tests cover resume/cache reuse, fresh resumed baselines, changed source/role rejection, interrupted attempt accounting, token stopping, setup/mixed-result fail-fast behavior, protected verification, source preservation, section/file modes and diff retention.
- In-app browser checked retained-only filtering, keyword search, evidence details and inline source diffs.
- Linux/Windows CI is configured but not executed locally. Windows direct-process timeout behavior is documented.

## Actual local Codex executions in this revision

Local authenticated Codex CLI 0.159.2; requested model gpt-6.1-sol. Authentication was the user's existing login, and the user explicitly authorized continued testing. Served model identity is not independently confirmed.

### Coding fixture: 14 executions

Task: implement an existing Python normalization function following repository conventions. Two intentionally constructed guidance paragraphs jointly enable legacy whitespace preservation. The independent modern contract requires trimming and lowercasing; the mismatch is deliberate. It is not evidence of a semantic contradiction or an AI defect.

- Full instruction baseline: 2/2 verifier failures.
- Empty selected instruction control: 2/2 passes.
- Each individual unit: 2/2 passes.
- Fresh two-unit confirmation: 2/2 failures.
- Each fresh single-removal control: 2/2 passes.
- Result: observed_1_minimal, retained [0, 1].
- Existing labels.py code changes preserved in per-run changes.diff. Original source still contains NotImplementedError and was not edited.

### Negative case: 2 executions

Same source and verifier, with an explicit task requiring modern trimming/lowercasing over legacy guidance. Both full-instruction repetitions passed. Result: not_reproduced; the tool did not start reduction or assert a conflict.

## Reported model usage

Usage below is parsed from Codex events. Cached input is included in input, not added to it. No dollar cost is inferred and missing/unreported usage cannot be counted.

- Coding fixture: input 1,000,891, output 5,216, cached input 909,952; 14 runs reported usage.
- Negative case: input 141,024, output 771, cached input 125,056; 2 runs reported usage.

Raw logs and account-specific evidence remain outside this source repository. Reproducible coding fixture: examples/normalize-label. Verifier independence and finite repeated controls do not prove general usefulness, causal attribution, statistical confidence, or an identical external environment.

## Earlier v0.1 validation

17 checks and an installed simulator passed locally. A separate deliberately constructed JSON-format fixture completed 14 local Codex executions with observed_1_minimality. Its raw evidence is retained separately; v0.1 evidence may be rendered but is rejected for v0.2 resume.
