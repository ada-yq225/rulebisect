# Demand notes — 2026-10-08

These are qualitative signals from public developer reports, not a representative market survey, a ranked demand list or proof of willingness to pay. RuleBisect remains free, MIT licensed and Codex-only.

## The v0.5 problem to solve

For a personal developer, a useful rule experiment starts with one concrete task and a check they can run independently. A successful first experiment is not enough: they need to keep that case, add an already-working task, and repeat the comparison when instructions change.

The product judgment for v0.5 is to make that workflow easier to configure and cheaper to diagnose before a model call. This is an inference from the reports and existing tools below, not a measured claim about adoption or a promise of savings.

| Pain point | Public evidence | Product response |
|---|---|---|
| Instructions are present but a required behavior is still omitted | [Codex issue 34189](https://github.com/openai/codex/issues/34189) reports loaded repository instructions being applied inconsistently; [issue 25884](https://github.com/openai/codex/issues/25884) describes rules being missed later in the same session | Keep behavioral checks independent. Preserve repeated outcomes and uncertainty rather than infer adherence from a file scan |
| Loading and behavior failures are easily confused | [Issue 30788](https://github.com/openai/codex/issues/30788) asks for focused instruction-discovery diagnostics without starting a session. In [issue 8759](https://github.com/openai/codex/issues/8759), a maintainer distinguishes model self-report from evidence in the actual session record | Show the files selected for an experiment, while keeping the limit explicit: selection does not prove runtime loading or compliance |
| A rule improvement on one task can hide regressions elsewhere | [RFC 40575](https://github.com/openai/codex/issues/40575) and its discussion propose repeated golden-set evaluation for behavioral rules | Make regression cases easy to add, list and remove. Support a small selected comparison, visibly disclose omitted cases, and recommend the full suite before applying changes |
| Automated runs are hard to budget and attribute | [Issue 29272](https://github.com/openai/codex/issues/29272) requests finer token reporting for exec; [issue 33668](https://github.com/openai/codex/issues/33668) reports an automated usage-monitoring gap | Preview required calls and expose reported usage. A token stop checked between calls is not a hard in-flight limit or a billing guarantee |
| Execution trouble can resemble an instruction failure | [Issue 46246](https://github.com/openai/codex/issues/46246) reports a sandbox execution failure with an apparently successful exec exit; [issue 44696](https://github.com/openai/codex/issues/44696) reports Windows sandbox-helper failures | Check every case's setup and verifier in fresh snapshots without Codex. Keep infrastructure errors separate from observed behavior failures; do not rely on the agent process exit alone |

These are reporter observations tied to particular versions and environments. The RFC is a participant proposal, not an adopted Codex contract. The environment issues motivate diagnostics; they do not show that RuleBisect can detect every sandbox problem, nor that local verifier checks reproduce the Codex sandbox itself.

## Existing tools and the narrower opportunity

- [Agent Context Lens](https://github.com/ciceroyang/agent-context-lens) already performs local context audits and explicitly modeled Codex instruction-chain explanations without model calls. RuleBisect should not claim to have invented static instruction auditing or loading diagnostics.
- [Skill Sunset](https://github.com/ooocooc/open-skill-sunset) audits stale references, duplicates and possible instruction-retirement hypotheses. It separates a hypothesis needing a test from evidence supporting retirement, and includes a gated command experiment harness. Its documented automatic session-usage and task-quality adapters remain future evidence layers.
- [skill-eval-harness](https://github.com/adewale/skill-eval-harness) provides paired variants, prepared task sets, trace artifacts, runner adapters and grading. Paired comparison and regression evaluation are established capabilities, not a novelty claim for this project.

RuleBisect's intended distinction is a focused Codex repository workflow: configure an independent check, locate a smaller failing instruction reproducer when possible, edit a separate draft, then compare behavior across retained regression cases. It uses the installed CLI and records local evidence. It does not need a second model to judge a task that already has an executable check.

## v0.5 workflow decisions

1. Add an optional guided `init --wizard`. Suggest possible check commands from project files, but require the developer to supply or confirm a concrete task and check. Do not execute an inferred command during initialization.
2. Add `case add`, `case list` and `case remove` so ordinary suite maintenance does not require editing JSON by hand. Removing a case preserves its verifier files.
3. Add `check --all` to exercise every selected suite verifier and setup on fresh initial snapshots, without model calls. An initial behavior failure can be expected before the requested implementation; infrastructure failure remains actionable.
4. Add `compare --cases` to permit a focused trial. The plan and report must name omitted cases; a passing subset must not be presented as a passing full suite.
5. Keep the first-use guide centered on the developer's decision: configure, check, investigate a failure, or compare a proposed change. Preserve explicit plans and local reports at each stage.

The onboarding priority is a product inference. We have not run a representative usability study, measured time to first success, or established that these commands will generate stars. Evaluate that hypothesis through redacted real cases and feedback on the setup steps.

## Earlier evidence and the v0.4 baseline

- [Codex issue 34189](https://github.com/openai/codex/issues/34189) reports repository instructions being loaded yet applied inconsistently. Discovery evidence and behavioral evidence answer different questions; a local static check cannot demonstrate adherence.
- [Codex issue 30788](https://github.com/openai/codex/issues/30788) requests a focused way to inspect instruction discovery instead of searching a large prompt dump. [Agent Context Lens](https://github.com/ciceroyang/agent-context-lens) already supplies local context auditing and explicitly modeled Codex instruction chains; this is an existing product category.
- [Codex RFC 40575](https://github.com/openai/codex/issues/40575) proposes testing behavioral instruction changes with multiple runs and regression suites. This is a proposal by participants, not an adopted Codex guarantee.
- [Codex issue 41450](https://github.com/openai/codex/issues/41450) describes an instruction A/B experiment that preserves task coverage while comparing reported token usage. Its numerical results are the author's report, not a general effect reproduced by RuleBisect.

### v0.4 product judgment

The most useful next step for this project is to close the loop between locating a smaller failing instruction subset and reviewing a proposed fix. One improved task can hide a regression in another; averaging them into a score would make the evidence less useful.

Implemented in v0.4:

1. Create an editable draft outside the repository so the baseline stays intact.
2. Compare original and proposed instructions against independent per-task verifiers, with repeated fresh workspaces and alternating arm order.
3. Preview exact planned calls before invoking Codex; share the reported-token cap across the suite and show per-arm usage without estimating money.
4. Show each regression, improvement, remaining failure or uncertainty. Provide a nonzero exit for regressions, failures and incomplete evidence.
5. Find old evidence and open the latest report without remembering timestamped paths.

This is not a new evaluation algorithm. It does not enforce arbitrary natural-language instructions, prove which instructions loaded, reproduce long-session compaction, or replace a full agent evaluation framework. Demand for those broader features remains unvalidated here.
