# Validation — v0.7.0

Executed on macOS, 2026-10-08. This update changes offline evidence presentation, not the experiment algorithm.

- All **163 automated tests passed** on Python 3.11.15, including 13 report UI tests for semantic navigation, named controls, escaped content, task/run links, zero-model checks, omitted cases, missing artifacts and summary privacy.
- Reproduced and fixed unsafe saved-report artifact links: URL schemes/delimiters, traversal and symlink components are rejected. Optional downloads appear only for existing local regular files; inline diffs cannot follow symlinks outside the report and previews are capped at 256 KiB.
- Reusable Node mock-DOM checks extract actual nodes, text, options and the fixed script from generated HTML. Reduction (5 units/48 runs), regression (8 runs), fix (8 runs), and single-verifier (0 runs) passed conjunction/search/reset, bilingual counters, theme state, blocked preference storage, initial empty states and repeated task-anchor navigation. These are logic checks with a simulated DOM, not browser interaction or layout validation.
- Built and installed the wheel into an isolated Python 3.11 environment. From outside the source checkout, the fix demo and both installed guided/assertion workflows completed, including frozen checks and aggregate-only export without private fixture text.
- Three freshly generated demos produced their expected statuses: observed_1_minimal, regressions_observed and no_regressions_observed. Summary exports and regenerated older verifier evidence preserved recorded outcomes and source/version metadata.
- Regenerated all three workflow GIFs from checked 0.7.0 model-free fixtures. The generator checks every decoded frame against its intended pixels; all 96 frames and static posters were reviewed. Media validation passed: each GIF is 1000×620, 32 frames, 20.16 seconds per loop and under 183 KB. These are edited illustrations, not report screenshots or actual account recordings.
- **No actual Codex/model calls were made for v0.7.** Simulations and verifier checks validate the workflow; they do not measure model effectiveness on user repositories.
- Browser security policy rejected localhost access. No alternate browser or rendering route was used. Actual report CSS/layout, browser accessibility-tree and visual acceptance remain unverified. The GIF illustrations were inspected as locally generated images.
- CI covers Linux/macOS/Windows × Python 3.11/3.13, the three demos, wheel installation and installed workflows, plus media checks and the Node mock-DOM check on Linux. Revision-specific results are recorded in GitHub Actions.

# Validation — v0.6.0

Executed on macOS, 2026-10-08. Constructed fixtures; no real-world defect or model-performance claim.

- All **150 automated tests passed** on Python 3.11.15. New coverage includes strict assertion schemas, UTF-8/JSON behavior failures, JSON Pointer/type handling, output-size and symlink errors, standalone verifier generation, assertion-based reduction, frozen criteria and no-write cancellation.
- Share tests check allowlisted aggregates, missing/partial usage, adversarial HTML/text, excluded private fields, racing output publication, refusal to overwrite and source/output symlink-loop errors. Summary rendering is checked as HTML content, not visually inspected.
- Review reproduced and fixed broken configuration symlink handling, initializer partial-write/interrupt rollback, instruction/oracle symlink ancestors and deeply nested input JSON. New tests check that existing user files are preserved when initialization fails.
- Initial Python 3.13 CI exposed a test's assumption about JSON decoder recursion limits. Newer decoders accepted the nested invalid input, which the strict schema correctly rejected. Tests now accept either valid rejection path and independently inject decoder recursion errors. All 13 initializer-integrity tests also passed locally on Python 3.14.4. The CI matrix collects all platform results instead of cancelling remaining jobs after the first failure.
- Built and installed the wheel into an isolated Python 3.11 virtual environment. From outside the checkout, both the existing guided workflow and the new no-code workflow completed: wizard JSON check, assertion case creation, input-spec mutation, whole-suite checks, summary export and malformed-spec rejection. Saved criteria stayed unchanged after editing the input JSON.
- Followed the output-contract example in a separate Git repository. Both initial verifiers failed for missing output, without infrastructure failure or model calls. The comparison plan reported exactly 12 calls. Both generated verifiers then passed independently under `python -I` against correct outputs outside that repository, using only the standard library. Original instructions and source remained unchanged.
- Installed demos completed with expected statuses: regression (8 simulator executions), scoped fix (8) and reduction (48). These are explicitly labeled simulations, not actual Codex runs.
- **No actual Codex/model calls were made for v0.6.** Prior actual Codex runs are documented below; they do not establish effectiveness of the new release on user repositories.
- Automated browser access remains blocked by the browser security policy; no alternate route was used. Visual/browser-interaction verification was not completed. Static report/privacy tests and installed export checks passed.
- CI runs Linux/macOS/Windows × Python 3.11/3.13, all three demos, wheel installation and both installed workflows. Revision-specific results are recorded in GitHub Actions.
- [Demand and differentiation review](docs/INNOVATION.md) compares primary sources and adjacent tools. Assertions, paired evaluation and delta debugging have prior art; workflow differentiation is a product hypothesis, not a first-in-the-world claim.

# Validation — v0.5.0

Executed on macOS, 2026-10-08. Constructed fixtures; no real-world defect claim.

- All 98 automated checks passed on Python 3.11.15. New coverage includes manifest suggestions, cancellation without writes, case schema/collision checks, atomic configuration rollback, protected untracked verifiers, independent suite-check workspaces, initial behavior failures and infrastructure errors.
- A focused review reproduced a subset-selection bug: omitted untracked verifiers disappeared from the snapshot. Fixed selection to retain the full suite's oracle/protected-file union; a regression test confirms full and selected checks use identical snapshot hashes.
- Built the wheel with the locally available setuptools runtime, installed it in an isolated virtual environment, and ran the installed CLI outside the source checkout. Guided init, add/list/remove case, whole-suite checks, draft creation and a selected comparison plan completed successfully.
- The installed workflow checked two initial behavior failures (both exit 1) without treating them as infrastructure failures. A selected comparison planned six calls and explicitly omitted the other task, with zero model calls.
- Installed regression demo completed eight deterministic simulator executions and caught the constructed improvement plus regression.
- No actual Codex/model calls were made for this release. These checks exercise configuration, isolation, evidence and workflow rather than model effectiveness.
- Automated browser inspection was blocked by the browser security policy. No alternate browser route was used. Report content and links were checked by automated tests; visual/browser-interaction verification was not completed in this release.
- CI covers Linux/macOS/Windows × Python 3.11/3.13, all three demos, packaged installation and the installed guided workflow. Current revision results are recorded in GitHub Actions.

# Validation — v0.4.2

Executed on macOS, 2026-10-07.

- All 67 automated checks passed on Python 3.11.15. Added doctor coverage for malformed JSON, invalid file roles/budgets, all suite cases, proposed-file comparison budgets, custom configuration, source preservation and authentication-output redaction.
- Offline validation subprocesses were observed: only Git queries ran, with no setup, verifier or Codex execution and no preflight artifacts created.
- Built and installed the wheel; the installed CLI outside the checkout validated the instruction-regression fixture with a custom config and proposed files, reporting exactly eight required comparison calls and zero model calls.
- No real Codex/model calls were made for this release. Static input validation does not establish that dependencies or verifier commands execute successfully; use check for that.
- Cross-platform CI results are recorded in GitHub Actions for the current revision.

# Validation — v0.4.1

Executed on macOS, 2026-10-07.

- All 60 automated checks passed on Python 3.11.15. New onboarding checks cover regression/fix matrices, browser-opening URLs, preserved existing evidence, distinct default outputs and unexpected-demo failure handling.
- Built the wheel, installed it in a clean virtual environment, and ran the installed CLI outside the source checkout. Regression and fix demos each completed eight deterministic simulator executions with the expected verdicts.
- No real Codex/model calls were made for this release. The demos validate the pipeline and teach the workflow; they do not measure model performance.
- CI adds all demo scenarios and an installed-wheel smoke test to the existing six OS/Python combinations. Current revision results are available in GitHub Actions.

# Validation — v0.4.0

Executed on macOS, 2026-10-07. Experimental tool; constructed cases, not a real-world defect claim.

- 54 regression checks passed on Python 3.11.15, including before/after task matrices, regressions despite improvements elsewhere, remaining failures, noise, setup errors, shared token stopping, interruptions, frozen source guards, no-model planning, draft preservation and latest-history selection.
- An additional passing check confirms verifier-created files are excluded from agent diffs (55 checks); a further passing POSIX check confirms read-only source instructions produce editable drafts without changing source permissions (56 checks); read-only instructions also pass full/empty workspace generation without altering source bytes or modes (57 total checks).
- Wheel built and installed in a clean Python 3.11 virtual environment. Installed compare --plan reported eight planned calls with zero model calls; installed draft preserved the original files.
- Windows CI exposed implicit system decoding in a new report-reading test; the test now uses explicit UTF-8. Checkpoint loading was also updated to read report JSON explicitly as UTF-8.
- In-app browser verified narrow-screen case cards, desktop comparison tables and expandable inline diffs.
- Eight actual local authenticated Codex executions, CLI 0.159.2; requested gpt-6.1-sol. Two independently verified API contracts, two instruction variants, two repetitions per arm. The blanket instruction proposal intentionally changes whitespace semantics.
- Modern task: original instructions failed 2/2; proposed instructions passed 2/2 (observed improvement).
- Compatibility task: original instructions passed 2/2; proposed instructions failed 2/2 (observed regression).
- Overall status: regressions_observed, CLI exit 2. The improvement did not hide the other task's regression. Every original snapshot file was hash-checked and remained unchanged.
- Reported tokens: input 520043, output 2919, cached input 464896. Cached input is part of input. No monetary cost inferred; provider routing is not independently verified.
- Reproducible fixture: examples/instruction-regression. No raw account/session logs are published in this source repo.
- No claims of statistical confidence, causal attribution, generalization to other tasks or superiority over other tools. Comparison does not validate instruction-loading provenance or long-session compaction behavior.

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
