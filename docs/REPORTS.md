# Read an evidence report / 读懂证据报告

RuleBisect reports help answer three questions: **what happened, what to do next, and which observations support it**. They are local HTML documents with inline styling, icons and interaction scripts; no remote assets are needed.

报告首先回答三个问题：**结果是什么、下一步做什么、哪些观察支持这个结果**。HTML 内置样式、图标与交互脚本，无需远程资源即可离线打开。

## Open or refresh / 打开或更新

```sh
rulebisect report ../experiment-evidence --open
# The saved report.json is also accepted:
rulebisect report ../experiment-evidence/report.json --open
# Find the latest evidence in a repository's default history:
rulebisect report --latest --repo /path/to/repository --open
```

`report` reads saved JSON and regenerates the HTML, Markdown and compact Issue draft in the same evidence directory. It does not call Codex, run the verifier or create new trial observations. After upgrading RuleBisect, use it to refresh older reports. Keep the evidence directory together so local logs and diffs remain available. Rendering older evidence is supported; resuming an experiment across tool versions is not.

`report` 从已保存的 JSON 重新生成同一证据目录中的 HTML、Markdown 和精简 Issue 草稿，不调用 Codex、不运行验证器，也不产生新试验结果。升级后可用它更新旧报告。请保留完整证据目录，确保日志与差异文件仍可访问；旧报告可以重新展示，但实验不能跨工具版本续跑。

Pass a report directory or its `report.json`, **or** use `--latest`; do not combine both. `--latest` searches the selected repository's default `.rulebisect-runs/<repo-name>` history, not arbitrary custom output locations. Omit `--open` when you only want to regenerate files.

指定报告目录或 `report.json`，也可以使用 `--latest`，两种方式不要同时提供。`--latest` 只检索指定仓库的默认历史目录；自定义输出位置需显式指定。只想生成文件时不加 `--open`。

## Follow the evidence / 从结果找到证据

| View / 视图 | What to inspect / 查看什么 |
|---|---|
| Overview / 概览 | Status, next action, source and scope / 状态、下一步、来源与覆盖范围 |
| Case results / 任务结果 | Original/proposed pass and failure counts; select a task to jump to its runs / 原始与拟议规则的通过失败次数，点击任务直达运行证据 |
| Instructions / 指令 | Retained and excluded instruction units; search or show only the candidate / 搜索指令片段，或仅查看候选保留部分 |
| Ledger / 对照记录 | Repeated full baseline, empty control and reduction observations / 完整指令、空指令与缩减过程的重复观察 |
| Runs / 逐次证据 | Outcome, phase, task, reason, original logs and captured code diffs / 结果、阶段、任务、原因、原始日志与代码差异 |
| Settings / 实验设置 | Saved task, model request, CLI/snapshot metadata, scope and budgets / 已保存的任务、模型请求、CLI 与快照信息、范围和预算 |

Only sections relevant to the report kind appear in navigation. Comparisons show task results; reductions show instruction units and the ledger. Verifier-only checks show their check results and clearly report zero model calls.

导航只展示当前报告适用的区块：对照实验展示任务结果，缩减实验展示指令与对照记录，仅验证器检查展示检查结果并明确标注模型调用为零。

In **Runs**, text search and the outcome, phase and task selectors work together. The live count reports how many recorded runs match. Reset restores the complete list. Task-result links target the corresponding run evidence; they do not start an experiment.

在逐次证据中，搜索与结果、阶段、任务筛选会联合生效，实时计数显示匹配的记录数。重置后恢复全部记录。点击任务结果只是定位对应证据，不会启动新实验。

The theme control switches light/dark appearance. English/中文 selection changes interface labels. User tasks, rule text, filenames, code and logs remain in their original language. With JavaScript disabled, the report still shows its result, tables, instruction cards and evidence; interactive controls are progressively enabled when scripts initialize.

主题控件切换明暗界面，English/中文选择器切换界面文字。用户任务、规则正文、文件名、代码和日志保留原文。关闭 JavaScript 后，结果、表格、指令与证据仍然可读；交互控件在脚本初始化后启用。

Diff colors distinguish additions, removals and headers; unchanged context stays readable. The patch and raw logs remain available for review when their local files exist. No proposed instructions are applied by viewing the report.

差异中的新增、删除与文件头分别标色，上下文仍可阅读。对应本地文件存在时，可继续打开补丁与原始日志。阅读报告不会应用拟议规则。

## Interpret the result / 理解结论

- **Observed 1-minimal:** a smaller candidate reproduced the failure, and each tested single removal passed fresh repeated checks. It is a failing reproducer; prepare and compare a fix separately.
- **Regression observed:** at least one originally passing task failed with the proposal. Improvements on other tasks do not erase that regression.
- **No regressions observed:** the proposal passed every selected repetition with stable baselines. Unselected tasks and other environments are not covered.
- **Inconclusive or interrupted:** the evidence is incomplete or inconsistent; do not treat a partial candidate as a confirmed result. Comparisons are rerun in a new output directory rather than resumed.
- **Verifier checks:** exit 0 is a current-code pass, 1 is a behavioral failure that may be expected before implementation, and other results indicate setup or runtime problems. Executable verifiers do not establish that model behavior passed.

缩减成功意味着找到更小的失败复现，仍需单独准备并验证修复。某项改善不会抵消其他任务的回退。通过只覆盖本次选定的任务与重复次数；中断、波动或预算不足不能当作已经确认的结果。验证器初始返回 1 可能符合预期，它与运行环境错误不同，也不意味着已经验证模型行为。

Source badges distinguish recorded Codex runs, deterministic simulations and verifier-only checks. Simulated executions are not model calls. These labels describe saved evidence; they are not independent authentication of a report's provenance.

来源标记区分已记录的 Codex 运行、确定性模拟和仅验证器检查；模拟执行不是模型调用。标记说明保存的证据类型，不是对报告来源的独立认证。

Reported usage may be missing or partial. Cached input is already included in input tokens, not an additional total. The report makes no monetary estimate, causal proof, statistical-confidence claim or guarantee on unseen tasks.

用量可能缺失或不完整；缓存输入已包含在输入 Token 中，不额外相加。报告不推算金额，也不证明因果关系、统计置信度或未测试任务的表现。

## Keep full evidence private; share aggregates / 完整证据与汇总分享

The **full report** includes task text, instruction bodies, settings, filenames, original logs and code diffs. It may contain private repository data. The compact Issue draft omits several of those fields, but it still needs review before publishing.

**完整报告**包含任务、指令、设置、文件名、原始日志和代码差异，可能含有私有仓库数据。精简 Issue 草稿会省略部分内容，发布前仍需审查。

```sh
rulebisect share ../experiment-evidence --out ../summary.html
```

The **aggregate summary** matches the report's visual style but contains no executable JavaScript, hyperlinks or remote assets. It is constructed from recognized status/source values and bounded counts, including reported usage and omitted-case counts. It excludes tasks, instructions, code, filenames, case IDs, models, commands, logs, timestamps and repository paths. Nothing is uploaded. Choose a new `.html` file outside the evidence directory and review the remaining statistics before sharing. See [the exact sharing boundary](SHARING.md).

**汇总摘要**采用相同视觉风格，没有可执行 JavaScript、超链接或远程资源。它只从已识别的状态、来源和有限数值构造，包含用量与未检查用例计数；不包含任务、指令、代码、文件名、用例 ID、模型、命令、日志、时间戳和仓库路径。命令不会上传。输出须是证据目录外的新 HTML，分享前仍需审查汇总数字。[完整分享边界](SHARING.md)。

Evidence downloads and inline diffs use validated relative paths. Only existing local files are linked; symlink components, traversal, URL schemes and unsafe URL delimiters are rejected. Moving or deleting artifacts can make them unavailable, without creating new model observations.

证据下载与内联差异只使用校验过的相对路径，链接仅指向确实存在的本地文件；符号链接、目录穿越、URL 协议和不安全分隔符路径会被拒绝。移动或删除文件会影响可用性，不会产生新的模型观察。

## Validation scope / 验证范围

This UI update uses static HTML/DOM regression checks for semantics, accessible controls, escaping, evidence paths and truthful source/status labels. Automated browser visual QA was not completed: the tool policy rejected localhost access. This release's new GIFs are edited, constructed model-free examples; they do not claim a fresh real-model run or actual account screen capture. See [validation records](../VALIDATION.md) and [media reproduction](MEDIA.md).

本次界面更新通过静态 HTML/DOM 回归检查验证语义、控件名称、转义、证据路径及来源与状态标注。浏览器工具策略拒绝 localhost，自动浏览器视觉验收尚未完成。新增 GIF 是经过剪辑的构造零模型示例，不代表新的真实模型运行或账号屏幕录制。详见[验证记录](../VALIDATION.md)与[动图生成说明](MEDIA.md)。
