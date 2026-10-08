# Set up, reduce, compare

All commands below follow `python3 "<skill-directory>/scripts/rulebisect_cli.py"`; replace placeholders and quote paths. Choose a Python 3.11+ interpreter. Use `--repo REPO` explicitly. Custom `--config CONFIG` is supported by doctor, plan, check, run, compare, resume and case commands; consult the command's `--help` for its options. Next-step messages from the engine may show a bare `rulebisect` command: use the same bundled launcher prefix instead.

## New failure

```text
init --repo REPO --task "Concrete task" --check "python -m unittest tests.test_contract"
doctor --offline --repo REPO
inspect --repo REPO --json
plan --repo REPO --json
check --all --repo REPO
```

Use exactly one of `--check COMMAND`, `--oracle verifier.py`, or `--assertions checks.json` at init. An oracle is repository-relative Python and returns 0/1/2+ for pass/behavior failure/infrastructure failure. A test command is wrapped into a protected Python oracle. Existing instructions are discovered from tracked AGENTS.md/AGENTS.override.md and untracked root instructions; review the selection. Skill files and untracked nested instructions require explicit `--instructions` selection.

Init writes configuration and, when needed, a generated verifier. It does not execute setup, checks or a model. Setup commands are optional and saved with `--setup "COMMAND"`. Accept the actual command before executing `check` or a model experiment. Protect other acceptance files that must remain fixed.

After checking the verifier and obtaining authorization for the selected model and budget:

```text
run --repo REPO --model MODEL --repeats REPEATS --max-runs APPROVED_CAP --out NEW_EVIDENCE
```

Reduction controls include full instructions, no selected instructions, a shrinking search, and fresh candidate/single-removal confirmation. The search may stop without confirmation when its cap is insufficient. Do not claim exact reduction call counts from the cap, or describe one observed result as causal proof.

## Preserve working behaviors

Save a case using one independent check choice:

```text
case add legacy --repo REPO --task "Preserve the legacy contract" --oracle verify_legacy.py
case list --repo REPO --json
check --all --repo REPO
```

Case changes update configuration. `case remove` preserves the verifier files. Assertions compile into frozen criteria; editing their input JSON later does not update the saved oracle.

## Proposed instructions

```text
draft --repo REPO --out NEW_PROPOSAL
compare --repo REPO --proposed NEW_PROPOSAL --plan
```

Edit only copied instruction paths in the proposal. Keep the original instructions and task checks unchanged. A comparison alternates arm order, starts each arm from the same current code snapshot, and protects the suite's verifier union in both arms.

After the user authorizes the planned calls/model/budget:

```text
compare --repo REPO --proposed NEW_PROPOSAL --model MODEL --repeats REPEATS --max-runs APPROVED_CAP --out NEW_EVIDENCE
```

A focused comparison accepts `--cases CASE_ID ...`; the report explicitly lists omitted cases. Check the full suite before recommending a change meant to preserve all saved behavior. Do not increase the case scope or budget beyond authorization. Applying a proposal is a separate user-requested action; compare does not apply it.

## Saved evidence and interrupted reductions

```text
history --repo REPO --json
report EVIDENCE
share EVIDENCE --out NEW_SUMMARY.html
resume --repo REPO --from EVIDENCE --model MODEL --repeats REPEATS --max-runs APPROVED_TOTAL_CAP --out NEW_EVIDENCE
```

Resume uses matching tool version, settings and snapshot, reuses stable search evidence and performs fresh controls. Supply the same model, repeats and other overridden settings (such as timeout and unit mode) as the original run; it does not automatically import those options from the report. Its cap includes previous runs. Simulations, comparisons and verifier checks do not support resume; rerun them in a new directory when needed. Rendering old reports is supported and does not change the original recorded tool version or trial results.

Real run/compare exits 0 for `observed_1_minimal` or `no_regressions_observed`, and 2 for other reported statuses, including `not_reproduced`. Inspect the report rather than treating every exit 2 as an installation failure. A demo that correctly catches its constructed regression exits 0. Check --all exits 0 when verifiers execute with 0/1 outcomes and 2 for execution trouble, regardless of expected initial behavioral failures.
