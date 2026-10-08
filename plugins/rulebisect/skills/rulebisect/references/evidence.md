# Read the result before recommending a change

Use saved JSON for counts and status, then open the relevant verifier/setup logs and captured code diff. A table improvement is not a reason to overlook another task's regression. Report omitted cases and uncertainties explicitly.

| Status | Supported interpretation | Useful next action |
|---|---|---|
| observed_1_minimal | Repeated failing candidate; each tested single removal passed | Inspect candidate units, draft a scoped change, compare cases |
| not_reproduced | Full baseline did not consistently fail | Improve the task/check or gather a reproducible case |
| control_failed | Failure remained without selected instructions | Investigate code, checks and configuration outside selected scope |
| regressions_observed | A previously passing task failed under the proposal | Inspect that task's evidence; revise the proposal |
| candidate_failed | Proposal still failed a case | Inspect remaining failures before calling it a fix |
| no_regressions_observed | Selected proposal cases passed stable repeated checks | Review the diff; describe only the tested coverage |
| inconclusive | Errors, variation or a stopping cap prevented confirmation | Resolve execution trouble or redesign/re-budget with authorization |
| interrupted | Recorded observations are incomplete | Resume a matching reduction or rerun compare/check |
| checks_completed | Verifiers executed with pass/fail outcomes | Read individual behavior outcomes; no model ran |
| checks_failed | Setup/verifier could not execute reliably | Fix the environment before model calls |

The report's source badge describes saved data; it is not independent authentication. Deterministic demos are simulations, not Codex performance evidence. A candidate directory contains a reduced failing reproducer. `draft` produces copied instructions for a proposed fix.

Token values are reported usage, not a cost estimate. Cached input is included in input tokens. Missing/partial reports are unknown, not zero cost. Repeats give finite observations, not statistical confidence, causation or a globally minimal subset.

`report EVIDENCE` regenerates HTML/Markdown/issue drafts without new experiments. Full evidence includes private repository context. `issue.md` is smaller but still needs review. `share EVIDENCE --out NEW.html` writes a standalone allowlisted count/status summary, without task text, rules, code, names, models, commands or logs, and without uploading it. Sharing with a person or public service is a separate action requiring the user's request.
