# Contributing to RuleBisect

Small, reproducible improvements are welcome. You do not need a Codex account to develop or test the tool. The project is permanently free, MIT licensed, Codex only and has no telemetry.

## Local workflow

Use Python 3.11+ and Git. From this checkout:

```sh
python3 -m venv .venv
# macOS / Linux; on Windows PowerShell use .venv\Scripts\Activate.ps1
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
rulebisect demo --scenario regression --open
rulebisect demo --scenario fix --open
```

These tests and demos do not call a model. CI also tests packaged installation on Linux, macOS and Windows, Python 3.11 and 3.13. No runtime dependencies are required beyond the standard library; the build uses setuptools.

## Useful contributions

- A small, redacted repository with a failing task and an independent verifier.
- An installation or workflow fix that makes the first experiment easier.
- A regression test for uncertainty handling, isolated snapshots or evidence preservation.
- Evidence of Codex instruction-loading behavior, with versions and clear limits.

Open an issue before a large feature so we can agree on scope. Include the concrete user problem, expected result and a minimal example. For a pull request, describe the behavior change and relevant checks. Keep English and Chinese quickstarts aligned when changing commands.

## Sharing a reproducer

Include Python, OS, RuleBisect and Codex versions; the command; verifier exit-code meanings; repetition/budget settings; and expected versus observed outcomes. Start with the compact `issue.md` generated in your evidence directory. It omits task text, instruction bodies and raw logs by default; review it before posting.

Full reports and diffs can contain private source, filenames or secrets. Remove sensitive data, or replace the repository with a minimal public fixture. Do not upload authentication files. Constructed examples and deterministic simulations must be labeled as such. One observed failure is not a causal explanation or a reliability measurement.

## Project boundaries

We prioritize understandable, local workflows: reproduce a failing Codex task, reduce selected instructions, then validate a proposed change against independent checks. A reduced failing subset is not a fix. Fresh confirmations and uncertain outcomes must stay visible. We do not add telemetry, paid tiers, silent model calls, or automatic edits to the original repository.
