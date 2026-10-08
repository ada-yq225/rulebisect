# Output-contract fixture / 输出契约案例

A small, deliberately constructed fixture with two label export contracts. The
original repository rules favor legacy output. A proposed scoped rule describes
both contracts. This is an example for learning the workflow, not a reported
Codex defect or a guarantee that any particular model will fail.

Copy this folder **outside any existing Git repository**, then enter the copy.
Install RuleBisect first; Python 3.11+ and Git are enough for the initial steps.

```sh
git init
git add .gitignore AGENTS.md checks.json checks-legacy.json
rulebisect init --task 'Export the modern label "  Alpha  " to result.json using repository conventions.' --assertions checks.json
rulebisect case add legacy --task 'Export the legacy label "  Alpha  " to result.json using repository conventions.' --assertions checks-legacy.json
rulebisect doctor --offline
rulebisect check --all --out ../output-contract-checks
rulebisect share ../output-contract-checks --out ../output-contract-summary.html
```

No model calls above. Both initial verifiers should report behavior failure because
`result.json` does not exist yet. `check --all` exits 0 when those verifiers execute
successfully; read the individual behavior results. The summary should show two
failed checks, source `verifier_only`, and zero recorded model trials.

Below, `run` and `compare` without `--plan` use your local Codex account and quota;
both planning commands make zero model calls. Choose a model available to you,
inspect the plan and keep the original rules unchanged.

```sh
rulebisect plan
rulebisect run --model YOUR_CODEX_MODEL_ID --open
rulebisect compare --proposed proposed --plan
rulebisect compare --proposed proposed --model YOUR_CODEX_MODEL_ID --open
```

Reduction investigates the original modern task. Comparison uses both saved
contracts: 2 cases × 2 variants × 3 repeats = **12 planned calls**. If original
observations fluctuate, execution fails or the budget is exhausted, the result
must remain inconclusive. The proposed file is an editable example; finite checks
do not validate unseen tasks. A reduction candidate is a failing reproducer, not
a fix to apply.

The checks are frozen into protected, standalone Python verifiers when saved.
Changing `checks.json` later does not change those criteria. The contract files
validate only the stated output properties, not a general label-exporting API.
See [all assertion types](../../docs/ASSERTIONS.md).

## 中文

把本目录复制到已有 Git 仓库之外，在副本中运行上面的初始化、案例保存、离线检查
和分享命令。上述初始化、检查和分享步骤不调用模型。初始文件不存在，两个案例行为失败符合预期；
`check --all` 返回 0 只说明验证器可执行，摘要会区分检查结果和模型试验次数。

后面的 `run` / `compare` 会使用本机 Codex 账户。原始规则偏向旧版标签契约，拟议
规则按现代/旧版分别限定；完整比较预计 12 次调用。真实模型结果可能不同，波动
不能宣称定位成功。此案例为构造示例，不是实际缺陷或效果保证。
