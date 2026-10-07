# RuleBisect

[中文说明](README.zh-CN.md)

**Investigate which repository instructions change a failing Codex task's outcome.**

Provide a task and an independent check. RuleBisect runs local Codex in fresh repository copies, shrinks failing instruction sets, and leaves an inspectable evidence bundle. It reports uncertainty instead of inventing a conflict.

MIT licensed, permanently free, local-first, no telemetry or hosted service. Codex only. Alpha software. **Actual runs use your installed Codex CLI, authentication and account quota or billing.** No model calls are made by setup, planning or verifier checks.

## Start in three steps

Python 3.11+, Git, and an authenticated [Codex CLI](https://learn.chatgpt.com/docs/non-interactive-mode) are required for real experiments. Install from this source checkout (not published on PyPI yet):

```sh
git clone https://github.com/ada-yq225/rulebisect.git
cd rulebisect
python3 -m pip install .
```

Inside the Git repository you want to investigate:

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
rulebisect demo --out ../rulebisect-demo
```

Open `../rulebisect-demo/report.html`. This is an explicitly labeled **deterministic simulator** that reduces five paragraph units to two interacting format rules. It tests the experiment pipeline, not real model behavior.

## Commands and controls

| Command | Purpose | Model calls |
|---|---|---|
| `doctor` | Check Python, Git, Codex version, login and setup | No |
| `init` | Generate configuration and an independent check wrapper | No |
| `inspect` | Show instruction units with original file/line references | No |
| `plan` | Validate inputs and preview scope/budget | No |
| `check` | Run the verifier on the initial snapshot | No |
| `run` | Run baseline, reduction and fresh confirmation | Yes |
| `resume --from EVIDENCE` | Reuse matching stable search evidence in a new output directory | Yes |
| `report EVIDENCE` | Regenerate HTML, Markdown and a compact issue draft | No |

`doctor`, `inspect`, and `plan` support `--json`. Run/resume/report support `--open` to open HTML locally.

```sh
rulebisect run --repeats 2 --max-runs 30 --max-tokens 100000 --timeout 180
rulebisect inspect --unit-mode section
rulebisect run --unit-mode file
```

- `--max-runs` is a hard total execution cap.
- `--max-tokens` stops before the next call once reported input + output tokens reach the limit. A single in-flight call can exceed it; unreported usage cannot be counted. Cached input is already part of input. This is **not a dollar/billing cap**.
- `--timeout` bounds each agent/verifier process.
- Repetitions default to 3; at least 2 are required.
- `--unit-mode paragraph` is the default; `section` preserves heading sections, `file` starts with whole instruction files. Fenced code stays together. Removing paragraphs/headings can change document structure.

Options can be saved as `repeats`, `max_runs`, `max_tokens`, `timeout`, `unit_mode`, `model` in `.rulebisect.json`; CLI options override them.

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

The cap includes previous executions. Resume checks tool/CLI version, requested model, snapshot content and modes, task, verifier/protected roles, instruction units, repeats, timeout and agent command. Changed inputs are rejected. It copies old trial logs to a **new** evidence directory and reuses only completed stable search groups. Baselines and final confirmation run afresh. Unrecorded environment changes remain possible; reuse is not proof of identical environments. Old v0.1 evidence can be rendered but cannot be resumed as a v0.2 experiment.

## Read and share evidence

The offline HTML report includes bilingual status/next steps, full-vs-empty control counts, searchable instruction cards, a retained-only filter, reported token usage, and per-run agent/verifier logs. Source changes survive workspace cleanup as `changes.diff` for snapshotted non-instruction files; new files are not captured and large/binary changes list filenames only.

Other exports: JSON, Markdown, candidate instruction files, a **review-only** `candidate.patch`, and an `issue.md` draft that omits task text, instruction bodies and raw logs by default. No changes are automatically applied and no issue is posted. Review all exports for private content before sharing.

Statuses: `observed_1_minimal`, `not_reproduced`, `control_failed`, `inconclusive`, `interrupted`, `check_only`. CLI exits 0 for a completed reduction, valid setup/planning operations or an executable initial verifier (even if behavior failed); 2 otherwise.

## Local execution boundaries

The source repository is never modified by experiments. Setup intentionally adds its two configuration files. Other untracked/ignored files, installed dependencies and Git history are not copied. Symlinks/submodules are unsupported. Prefer small, self-contained fixtures first.

Copies are not containers or a security boundary. Codex runs with `workspace-write`, `approval_policy="never"`, `--ephemeral`, `--ignore-user-config`; verifier commands run with your local account. Use trusted repositories/checks only. Global instructions, project configuration, imports, network services and tool versions can affect behavior. POSIX timeouts terminate the process group; Windows currently terminates the direct process only. Full reports, diffs and logs may contain private code/output.

## Development and evidence

```sh
python3.11 -m unittest discover -s tests -v
```

See [VALIDATION.md](VALIDATION.md) for actual executed checks. CI is configured for Linux/macOS/Windows, Python 3.11/3.13; unexecuted platforms are not verified. The coding fixture in `examples/normalize-label` is intentionally constructed to expose outdated whitespace guidance, not a reported real-world defect.

Prior work: [Delta Debugging for LLM-integrated Systems](https://www.amazon.science/publications/delta-debugging-for-llm-integrated-systems), [skill-eval-harness](https://github.com/adewale/skill-eval-harness), [Probe-and-Refine](https://arxiv.org/abs/2606.20512). RuleBisect explores the repository-failure-to-small-instructions workflow; it does not claim a new algorithm or the first prompt debugger.

Contributions welcome: redacted reproducible failures, stronger independent verifiers, context-loading evidence and parser improvements. Attach versions, assertions and repeated observations, not one-run causal claims.
