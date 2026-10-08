# RuleBisect: demand and differentiation review

Research snapshot: **2026-10-08**. Scope: personal developers using Codex locally.

## Verdict

RuleBisect addresses a plausible, documented problem: repository instructions can
fail in practice, and an instruction edit can improve one task while harming another.
Its potential differentiation is a focused workflow that connects observed failure
reduction, instruction editing, and repeated checks across a user's tasks.

This is **product and workflow differentiation**, not a new algorithm. Declarative
assertions, delta debugging, paired comparisons, and evidence reports are established.
This review does not prove that RuleBisect is first, unique, or the best option.

## Method and limits

- Searched public web results and opened original repository documentation, maintainer
  reports, Codex issues, and a research paper; the comparison below describes those sources.
- Compared documented features, not a benchmark of installed competing products.
- Public issues are individual reports. They do not establish prevalence, willingness
  to use a tool, market size, or a ranking of the most requested features.
- A repository README can describe features ahead of a packaged release. Check the
  installed version before relying on a command copied from a competing project's docs.
- No exhaustive web search can establish absence of prior art. Related products and
  Codex behavior can change after this snapshot.
- Reducing setup friction and sharing friction are product hypotheses. Validate them
  with new users completing their first real case, rather than with star counts alone.

## Problems with direct evidence

1. **Loaded instructions can still be missed.** A reporter checked the initial context
   and observed intermittent omissions of repository requirements. This supports testing
   observable results; it does not prove which prompt component caused the omissions.
   [Codex issue #34189](https://github.com/openai/codex/issues/34189)
2. **A useful edit can regress other tasks.** Stet's maintainer measured AGENTS.md
   iterations and observed regressions on a separate task set. The author explicitly
   limits the evidence to one repository and a small sample, without statistical
   significance. This supports a regression-set workflow, not a performance promise.
   [Stet experiment](https://www.stet.sh/blog/how-i-used-codex-to-improve-its-own-agents-md)
3. **Diagnosis and evidence can be cumbersome.** A Codex request describes searching
   a large prompt JSON dump to understand instruction discovery, and asks for a focused
   diagnostic. Inferring that a compact evidence summary helps users is our product
   judgment; an outcome summary does not reconstruct Codex's actual loading chain.
   [Codex issue #30788](https://github.com/openai/codex/issues/30788)
4. **Reported success and logs need independent checks.** Reports describe missing
   host-observable execution records and incomplete JSON command output. These are
   bounded observations, but support checking output files rather than trusting a
   final assistant claim alone.
   [Codex issue #34152](https://github.com/openai/codex/issues/34152),
   [Codex issue #48346](https://github.com/openai/codex/issues/48346)
5. **Execution errors must not become instruction verdicts.** A report describes
   sandbox setup failure with a successful CLI exit. Test runners also distinguish
   failure, internal errors, invalid usage, and absent tests. Arbitrary verifier exit
   code 1 is not enough to diagnose every framework's failure cause.
   [Codex issue #46246](https://github.com/openai/codex/issues/46246),
   [pytest exit-code contract](https://docs.pytest.org/en/stable/reference/exit-codes.html)

## Existing coverage

| Primary source | Documented coverage | Consequence for RuleBisect |
| --- | --- | --- |
| [Agent Context Lens](https://github.com/ciceroyang/agent-context-lens) | Local context audit and bounded Codex instruction-chain explanation, with version/platform uncertainty and reports. | Static discovery inspection is already covered. RuleBisect focuses on task outcomes; it must not claim to prove instructions were loaded. |
| [Skill Sunset](https://github.com/ooocooc/open-skill-sunset) | Stale/duplicate instruction auditing, conservative retirement hypotheses, experiment templates, localized and redacted reports. | Rule cleanup and privacy-aware reporting are established. Behavioral evidence can complement this audit. |
| [Skill Eval Harness](https://github.com/adewale/skill-eval-harness) | Paired skill variants, repeated runs, ablations, split discipline, file/text/regex/JSON assertions, leakage checks, and review pages. | Assertions, comparison, and ablation are not novel. General skill evaluation is broader than RuleBisect's scope. |
| [agent-skill-eval](https://github.com/tardigrde/agent-skill-eval) | Real Codex/Claude/OpenCode CLIs, fresh workspaces, state-diff/file/JSON assertions, budget guards, targeted reruns, and skipped unverifiable grading. | This is a direct adjacent alternative. Fresh workspaces, no-code checks, and honest error handling are not exclusive differentiators. |
| [promptfoo coding-agent guide](https://github.com/promptfoo/promptfoo/blob/main/site/docs/guides/evaluate-coding-agents.md) and [assertions](https://www.promptfoo.dev/docs/configuration/expected-outputs/) | Coding-agent evaluation, structured outputs, deterministic assertions, trajectory checks, and broader eval integration. | A general evaluation platform already exists. RuleBisect should prioritize a simpler instruction-debugging journey. |
| [Stet maintainer experiment](https://www.stet.sh/blog/how-i-used-codex-to-improve-its-own-agents-md) | Real task benchmarking of AGENTS.md edits, separate-task validation, trace inspection, and quality/cost tradeoffs. | Instruction A/B testing is already practiced. RuleBisect's promise is a narrow local workflow, not the invention of behavioral benchmarking. |
| [Delta Debugging for LLM-integrated Systems](https://cdn.zhuhaonan.com/files/icse-26-ddllms.pdf) | Delta debugging applied to LLM inputs, with context markers and traces. | LLM input reduction has research prior art. RuleBisect must not claim a new delta-debugging algorithm. |

## v0.6 product choices

- **Start without writing a verifier script.** Immutable JSON acceptance checks support
  file existence, text, regex, and JSON Pointer assertions. Use `init --assertions
  checks.json` or `case add --assertions checks.json`; the wizard offers `:exists`,
  `:contains`, `:json`, and `@FILE`. Advanced behavior still needs a custom verifier.
- **Use the existing debugging loop.** The same checks work with preflight, failure
  reduction, and proposed-instruction comparisons. Check definitions stay outside
  mutable trial workspaces. This is an evaluation-integrity measure, not an OS security
  boundary. Existing `protected_files` handles forbidden changes; v0.6 does not add
  a `file_unchanged` assertion.
- **Share a deliberately small summary.** `share EVIDENCE --out summary.html` produces
  an offline summary from an explicit metadata allowlist. It omits tasks, code, case
  IDs, model names, logs, and other free-form evidence. It is a summary, not a full
  reproduction bundle or a guarantee of complete anonymization.

The proposed combination is useful because it answers a specific question:
**Which instruction subset still reproduces this failure, and does my edit break
other checked tasks?** It does not guarantee causality, global minimality, future
model behavior, or performance on untested tasks. Repeated finite observations remain
finite observations.

## 中文结论

有值得继续验证的产品价值。创新点应描述为“专注 Codex 的失败规则缩减与修复回归
工作流组合”，不能宣传“全网首创”“新算法”或“没人做过”。无代码断言和分享摘要
用于降低使用门槛；真实差异要靠用户案例、完成率和可审阅的运行证据证明。
