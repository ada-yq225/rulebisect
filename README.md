# RuleBisect

[中文说明](README.zh-CN.md)

**Debug Codex rules. Keep the fix from breaking another task.**

Provide a task and an independent check. RuleBisect runs local Codex in fresh repository copies, shrinks failing instruction sets, and leaves an inspectable evidence bundle. It reports uncertainty instead of inventing a conflict.

MIT licensed, permanently free, local-first, no telemetry or hosted service. Codex only. Alpha software. **Actual runs use your installed Codex CLI, authentication and account quota or billing.** No model calls are made by setup, planning or verifier checks.

## See what it does — no Codex account needed

Install using Python 3.11+ and Git, then try:

```sh
rulebisect demo --scenario regression --open
rulebisect demo --scenario fix --open
```

The first catches a proposed rule that fixes modern labels but breaks legacy labels. The second checks a scoped fix that preserves both contracts. Each uses eight **deterministic simulation executions, zero model calls**. Reports open locally; repeated demos get separate output directories. A successful regression demo exits 0 because catching the constructed regression is expected; real `compare` still exits 2 when it finds a regression.

**Choose your workflow:** a failing task → `run`; a proposed instruction change → `draft` + `compare`; just exploring → `demo`. You need a task with an executable pass/fail check; this does not grade arbitrary prompts automatically.

## Install and run your own experiment

Python 3.11+, Git, and an authenticated [Codex CLI](https://learn.chatgpt.com/docs/non-interactive-mode) are required for real experiments. The [v0.5.0 release](https://github.com/ada-yq225/rulebisect/releases/tag/v0.5.0) includes an installable wheel; the project is not on PyPI yet.

For a release install, create and activate a virtual environment, then:

```sh
python -m pip install https://github.com/ada-yq225/rulebisect/releases/download/v0.5.0/rulebisect-0.5.0-py3-none-any.whl
```

Or install from source:

```sh
git clone https://github.com/ada-yq225/rulebisect.git
cd rulebisect
python3 -m venv .venv
# macOS / Linux:
. .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install .
```

Inside the Git repository you want to investigate, start with the guided flow:

```sh
rulebisect init --wizard
rulebisect doctor --offline
rulebisect check --all --open
rulebisect run --model YOUR_CODEX_MODEL_ID --open
```

The wizard asks four questions: concrete task, independent check, optional environment setup, optional model. It suggests commands based on project manifests; you must choose explicitly. It does not install dependencies or run checks/model calls. Configuration creation is the only write. Review `instructions` and `protected_files` before a real run.

You can also configure directly:

```sh
rulebisect init \
  --task "Implement normalize_label in labels.py following repository conventions." \
  --check "python -m unittest discover -s tests" \
  --model YOUR_CODEX_MODEL_ID
rulebisect plan
rulebisect check
rulebisect run
```

`init` discovers tracked `AGENTS.md` / `AGENTS.override.md` files, preferring an override in the same directory. Untracked root instructions are also considered. Skills and untracked nested instructions are opt-in with `--instructions`. It creates `.rulebisect.json` and a trusted Python check wrapper; common test filenames are automatically protected. Review both instruction and protection lists.

`plan` validates configuration and the snapshot, showing scope and the execution cap. `check` runs only your verifier against a fresh initial copy. A behavior failure may be expected before the coding task is implemented; inspect `check.log` to distinguish it from test setup failures. Neither command calls Codex.

`run` uses the saved model and options. Evidence goes into a new `.rulebisect-runs/<repo-name>/...` directory beside your repository, unless `--out` selects a different empty directory outside it.

## Try without Codex

```sh
rulebisect demo --scenario reduce --out ../rulebisect-demo --open
```

Open `../rulebisect-demo/report.html`. This is an explicitly labeled **deterministic simulator** that reduces five paragraph units to two interacting format rules. It tests the experiment pipeline, not real model behavior.

## Catch setup mistakes before using model quota

```sh
rulebisect doctor --offline
rulebisect doctor --offline --proposed ../proposed-rules
rulebisect doctor --config experiment.json --json
```

Doctor validates the frozen-snapshot inputs, selected instruction files, verifier/protected roles, every suite case and saved budgets. `--proposed` also validates the proposed files and requires enough calls for the whole comparison. It returns exit 2 for invalid inputs. Without a proposed directory, a comparison budget shortage is a note because the configuration may still be used for reduction.

`--offline` skips Codex installation and login checks; normal doctor checks both without making model calls. Neither mode executes setup commands or the verifier, creates experiment evidence, or establishes that your tests will run successfully. Use `check` next to exercise the environment. Missing saved model is a note: you can select it with `--model` when running.

## Commands and controls

| Command | Purpose | Model calls |
|---|---|---|
| `doctor` | Check Python, Git, Codex version, login and setup | No |
| `init --wizard` / `init` | Generate configuration and an independent check wrapper | No |
| `inspect` | Show instruction units with original file/line references | No |
| `plan` | Validate inputs and preview scope/budget | No |
| `check` / `check --all` | Check one verifier or every suite case on initial snapshots | No |
| `case add/list/remove` | Manage regression cases without editing JSON | No |
| `run` | Run baseline, reduction and fresh confirmation | Yes |
| `resume --from EVIDENCE` | Reuse matching stable search evidence in a new output directory | Yes |
| `draft --out DIRECTORY` | Make an editable instruction copy; preserve the original baseline | No |
| `compare --proposed DIRECTORY` | Repeat before/after checks across one task or a regression suite | Yes |
| `compare --proposed DIRECTORY --plan` | Validate the suite and show exact planned calls | No |
| `history` | Find previous runs without remembering paths | No |
| `report EVIDENCE` | Regenerate HTML, Markdown and a compact issue draft | No |

`doctor`, `inspect`, and `plan` support `--json`. Demo/run/resume/report/compare support `--open` to open HTML locally.

```sh
rulebisect run --repeats 2 --max-runs 30 --max-tokens 100000 --timeout 180
rulebisect inspect --unit-mode section
rulebisect run --unit-mode file
```

- `--max-runs` is a hard total execution cap.
- `--max-tokens` stops before the next call once reported input + output tokens reach the limit. A single in-flight call can exceed it; unreported usage cannot be counted. Cached input is already part of input. This is **not a dollar/billing cap**.
- `--timeout` bounds each setup, agent and verifier process.
- Repetitions default to 3; at least 2 are required.
- `--unit-mode paragraph` is the default; `section` preserves heading sections, `file` starts with whole instruction files. Fenced code stays together. Removing paragraphs/headings can change document structure.

Options can be saved as `repeats`, `max_runs`, `max_tokens`, `timeout`, `unit_mode`, `model` in `.rulebisect.json`; CLI options override them.

## Save working tasks as regression cases

```sh
rulebisect case add existing-feature \
  --task "Implement the existing feature contract." \
  --check "python -m unittest tests.test_existing_feature"
rulebisect case list
rulebisect check --all --open
```

Your original task remains in the suite. `case add` accepts either a trusted check command or `--oracle existing-verifier.py`; no command or model is executed. Configuration changes are atomic. `case remove ID` removes the entry and keeps verifier files. IDs are portable, unique names; the last case cannot be removed. Case commands accept `--repo` and `--config`.

`check --all` runs setup and each verifier on its own frozen initial snapshot, then produces a combined report. Exit 0 means all checks returned 0 or 1; **it does not mean every behavior passed**. Initial unimplemented tasks may fail as expected. Exit 2 means infrastructure trouble or interruption. Check assertions/logs: some frameworks use exit 1 for setup/import errors too. This checks the local verifier environment, not Codex's sandbox.

## Check a proposed fix before applying it

Finding a failing instruction subset is only the first step. Validate your proposed change on the original task and on tasks that already work:

```sh
rulebisect draft --out ../proposed-rules
# Edit ../proposed-rules/AGENTS.md, preserving the original repo instructions.
rulebisect compare --proposed ../proposed-rules --plan
rulebisect compare --proposed ../proposed-rules --open
```

For a quick selected comparison:

```sh
rulebisect compare --proposed ../proposed-rules --cases existing-feature --plan
rulebisect compare --proposed ../proposed-rules --cases existing-feature --open
```

The report explicitly lists omitted cases; a passing subset does not validate them. Run the full suite before applying shared rule changes. `check --all --cases ID ...` checks selected environments without Codex. See the [bilingual workflow guide](docs/QUICKSTART.md) for a complete first-task-to-regression example.

No suite configuration is required for a single task: comparison reuses the task and verifier saved by `init`. For several tasks, add a `cases` array to the same config:

```json
"cases": [
  {"id": "original-failure"},
  {"id": "working-feature", "task": "Implement the existing feature contract.", "oracle": "verify_feature.py"}
]
```

Each case inherits the top-level settings and can override task, oracle, verify and protected_files. Ids use letters, digits, underscores or dashes. All case verifiers and protected files are protected in every workspace, including untracked verifiers. `cases` applies to `compare`; `run` still reduces the top-level task.

The plan shows **cases × 2 variants × repeats** calls (one case with 2 repeats = 4 calls). If the execution cap cannot cover them, it refuses before starting. A shared reported-token cap can stop an incomplete comparison. Variant order alternates per repetition; each call starts from the same frozen code snapshot. Only selected instruction contents are replaced; other files in the proposed directory are not applied. Files must retain their selected paths; empty proposed instruction files are supported.

The report lists improvements, regressions, still-passing and still-failing tasks individually, plus each arm's reported tokens and raw evidence. A regression is stable baseline passes followed by stable proposed-instruction failures. Mixed observations, infrastructure errors or interruptions are inconclusive. Exit 0 requires every proposed task to pass every repetition with stable baselines; 2 means regression, remaining failure or uncertainty. This is a finite check, not statistical confidence or a guarantee on unseen tasks. No instructions are applied automatically.

**Reduction's `candidate/` directory is a smaller failing reproducer, not a suggested fix.** Start with `draft`, edit the copies yourself, then compare. Do not edit the original instructions before comparison, or you change the baseline. Example: [instruction-regression](examples/instruction-regression).

## Find evidence quickly

```sh
rulebisect history
rulebisect report --latest --open
rulebisect resume --latest --max-runs 100
```

History reads summaries in the default `.rulebisect-runs/<repo-name>` directory, newest first, with no model calls. Broken reports are skipped with a warning. Latest resume selects a completed/interrupted Codex reduction, excluding checks, comparisons, simulations and running experiments; snapshot/version checks still apply. Custom `--out` directories need an explicit path. Comparisons can be rerun but are not resumable in this release.

## Prepare dependencies automatically

Add `--setup "npm ci"` to `init`, or set an argv array in `.rulebisect.json`:

```json
"setup": ["{python}", "prepare_environment.py"]
```

Setup runs in every fresh workspace before Codex, and during `check`. Use it to install locked dependencies or create a local virtual environment. It uses the same process timeout; logs are saved as `setup.log`. Commands run without a shell: put multiple steps in a script. `{python}` selects RuleBisect's interpreter.

Setup must preserve snapshot files (including the selected instructions and verifier). A failure, timeout or snapshot content change stops the experiment before a model call. Existing installed dependencies are not copied, and setup does not pin network services or prevent changes to your machine. Keep generated dependencies ignored; prefer workspace-local installs. Resume also requires the same setup command.

## A precise verifier

`--check` accepts one quoted argv command with no shell operators, pipes or redirects. Exit 0 passes, 1 is a behavior failure, other codes are setup errors. **Some test frameworks also return 1 on import/setup errors.** The wrapper cannot reliably distinguish these; inspect the initial check or use a self-contained verifier:

```sh
rulebisect init --task "A concrete task" --oracle verify_behavior.py --model MODEL
```

Example configuration:

```json
{
  "task": "Implement normalize_label in labels.py following repository conventions.",
  "instructions": ["AGENTS.md"],
  "oracle": "verify_behavior.py",
  "verify": ["{python}", "{oracle}"],
  "protected_files": ["tests/test_labels.py", "verify_behavior.py"],
  "model": "YOUR_MODEL_ID",
  "repeats": 3,
  "max_runs": 60,
  "timeout": 300,
  "unit_mode": "paragraph"
}
```

`{python}` uses the interpreter running RuleBisect; `{oracle}` is an immutable verifier copy outside the agent's workspace. Arguments use exact-token substitution, not shell interpolation. Relative paths are evaluated from the copied repository root. The verifier must return 0=pass, 1=intended behavior failure, 2+=setup/runtime errors. Protect its dependencies and any tests that must remain unchanged; automatic test protection is a filename heuristic only. The verifier may be visible in the snapshot: this is not a blind benchmark and does not prevent answer leakage.

## What the reducer establishes

1. Hash and copy tracked **current working-tree contents**, including uncommitted edits, plus explicitly selected instruction/verifier/protected files.
2. Require every full-instruction baseline repetition to fail and every empty-instruction control to pass.
3. Use delta debugging to shrink the failing subset, reusing stable search evaluations.
4. Run the candidate and each single-removal control **afresh**. Only then label it `observed_1_minimal`.

This means observed single-removal minimality, **not causal attribution, semantic contradiction, statistical confidence or a globally smallest subset**. Mixed observations, agent/verifier errors or exhausted budgets are inconclusive. Search can miss alternative failure sources. Confirm leads on held-out tasks before changing shared instructions.

Empty selected files remain present, affecting instruction fallback/loading. The tool does not prove each fragment was loaded or reconstruct all external context. Requested model and CLI version are recorded; provider routing and external environment are not guaranteed fixed.

## Resume without silently reusing the wrong experiment

```sh
rulebisect resume --from /old/evidence --max-runs 100
```

The cap includes previous executions. Resume checks tool/CLI version, requested model, snapshot content and modes, task, verifier/protected roles, instruction units, repeats, timeout, setup and agent command. Changed inputs are rejected. It copies old trial logs to a **new** evidence directory and reuses only completed stable search groups. Baselines and final confirmation run afresh. Unrecorded environment changes remain possible; reuse is not proof of identical environments. Evidence from older tool versions can be rendered but cannot be resumed across a version change.

## Read and share evidence

The offline HTML report includes bilingual status/next steps, full-vs-empty control counts, searchable instruction cards, a retained-only filter, reported token usage, and per-run agent/verifier logs. Source changes survive workspace cleanup as `changes.diff`: edits, deletions and non-ignored new files are captured. Large/binary changes list filenames only. Dependency files created by setup are excluded from new-file evidence; ignored new files are excluded.

Other exports: JSON, Markdown, candidate instruction files, a **review-only** `candidate.patch`, and an `issue.md` draft that omits task text, instruction bodies and raw logs by default. No changes are automatically applied and no issue is posted. Review all exports for private content before sharing.

Statuses: `observed_1_minimal`, `not_reproduced`, `control_failed`, `inconclusive`, `interrupted`, `check_only`. CLI exits 0 for a completed reduction, valid setup/planning operations or an executable initial verifier (even if behavior failed); 2 otherwise.

## Local execution boundaries

The source repository is never modified by experiments. `init` intentionally adds configuration and, when using --check, a verifier wrapper. Other untracked/ignored files, installed dependencies and Git history are not copied. Symlinks/submodules are unsupported. Prefer small, self-contained fixtures first.

Copies are not containers or a security boundary. Codex runs with `workspace-write`, `approval_policy="never"`, `--ephemeral`, `--ignore-user-config`; verifier commands run with your local account. Use trusted repositories/checks only. Global instructions, project configuration, imports, network services and tool versions can affect behavior. POSIX timeouts terminate the process group; Windows currently terminates the direct process only. Full reports, diffs and logs may contain private code/output.

Product rationale and public sources: [demand notes](docs/DEMAND.md).

## Development and evidence

```sh
python3.11 -m unittest discover -s tests -v
```

See [VALIDATION.md](VALIDATION.md) for actual executed checks. CI is configured for Linux/macOS/Windows, Python 3.11/3.13; unexecuted platforms are not verified. The coding fixture in `examples/normalize-label` is intentionally constructed to expose outdated whitespace guidance, not a reported real-world defect.

Prior work: [Delta Debugging for LLM-integrated Systems](https://www.amazon.science/publications/delta-debugging-for-llm-integrated-systems), [skill-eval-harness](https://github.com/adewale/skill-eval-harness), [Probe-and-Refine](https://arxiv.org/abs/2606.20512). RuleBisect explores the repository-failure-to-small-instructions workflow; it does not claim a new algorithm or the first prompt debugger.

Contributions welcome: redacted reproducible failures, stronger independent verifiers, context-loading evidence and parser improvements. Attach versions, assertions and repeated observations, not one-run causal claims.

See [CONTRIBUTING.md](CONTRIBUTING.md) for a no-model development workflow and how to submit a useful reproducer.
