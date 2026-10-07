# Demand notes — 2026-10-07

These are qualitative signals from public developer reports, not a representative market survey, a ranked demand list or proof of willingness to pay. RuleBisect remains free, MIT licensed and Codex-only.

## Public signals

- [Codex issue 34189](https://github.com/openai/codex/issues/34189) reports repository instructions being loaded yet applied inconsistently. Discovery evidence and behavioral evidence answer different questions; a local static check cannot demonstrate adherence.
- [Codex issue 30788](https://github.com/openai/codex/issues/30788) requests a focused way to inspect instruction discovery instead of searching a large prompt dump. [Agent Context Lens](https://github.com/ciceroyang/agent-context-lens) already supplies local context auditing and explicitly modeled Codex instruction chains; this is an existing product category.
- [Codex RFC 40575](https://github.com/openai/codex/issues/40575) proposes testing behavioral instruction changes with multiple runs and regression suites. This is a proposal by participants, not an adopted Codex guarantee.
- [Codex issue 41450](https://github.com/openai/codex/issues/41450) describes an instruction A/B experiment that preserves task coverage while comparing reported token usage. Its numerical results are the author's report, not a general effect reproduced by RuleBisect.

## Product judgment

The most useful next step for this project is to close the loop between locating a smaller failing instruction subset and reviewing a proposed fix. One improved task can hide a regression in another; averaging them into a score would make the evidence less useful.

Implemented in v0.4:

1. Create an editable draft outside the repository so the baseline stays intact.
2. Compare original and proposed instructions against independent per-task verifiers, with repeated fresh workspaces and alternating arm order.
3. Preview exact planned calls before invoking Codex; share the reported-token cap across the suite and show per-arm usage without estimating money.
4. Show each regression, improvement, remaining failure or uncertainty. Provide a nonzero exit for regressions, failures and incomplete evidence.
5. Find old evidence and open the latest report without remembering timestamped paths.

This is not a new evaluation algorithm. It does not enforce arbitrary natural-language instructions, prove which instructions loaded, reproduce long-session compaction, or replace a full agent evaluation framework. Demand for those broader features remains unvalidated here.
