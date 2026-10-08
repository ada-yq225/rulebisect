# Quick start / 快速上手

[English](#english) · [中文](#中文)

## English

After [installation](../README.md#install-and-run-your-own-experiment), run these commands inside the Git repository you want to investigate. Python 3.11+ and Git are required. Only real `run`, `resume` and `compare` executions use your installed Codex CLI, login and quota; the demos are deterministic simulations.

### Start with one real task

```sh
rulebisect init --wizard
rulebisect doctor --offline
rulebisect check --all --open
```

The wizard asks for a concrete task and an independent check. It can suggest commands found in project files; it does **not** run those inferred commands. Initialization makes no model calls. Review the selected instructions and protected files in `.rulebisect.json`.

You can still initialize directly and save a model:

```sh
rulebisect init --task "Implement normalize_label in labels.py." \
  --check "python -m unittest discover -s tests" --model YOUR_CODEX_MODEL_ID
```

`check --all` runs setup and every case's verifier on fresh initial snapshots without Codex. Exit 0 means each verifier completed with 0 (pass) or 1 (behavior failure); **it does not mean all behaviors passed**. A failure can be expected before the task is implemented. Exit 2 indicates infrastructure trouble. Some frameworks also use 1 for import or setup errors: inspect the report, or use a verifier that returns 0 for pass, 1 for behavior failure, and 2+ for infrastructure failure.

### Keep regression cases

```sh
rulebisect case add legacy-labels \
  --task "Implement the legacy label contract without trimming whitespace." \
  --oracle verify_legacy.py
rulebisect case add modern-labels \
  --task "Implement the modern label contract." \
  --check "python -m unittest tests.test_modern"
rulebisect case list --json
rulebisect check --all --open
```

Supply either `--check "COMMAND"` or `--oracle verifier.py`. Commands use argv parsing, without shell pipes or expansion; put multiple steps in a wrapper script. The Python oracle must be inside the repository. Case commands accept `--repo PATH` and `--config PATH` for another repository or configuration.

`rulebisect case remove modern-labels` removes the case entry and **preserves its verifier files**. Keep at least one case for an already-working behavior, alongside the original failure.

### Compare a proposed instruction change

```sh
rulebisect draft --out ../proposed-rules
# Edit the instruction copies in ../proposed-rules.
rulebisect compare --proposed ../proposed-rules --cases legacy-labels --plan
rulebisect compare --proposed ../proposed-rules --cases legacy-labels --open
```

The selected comparison omits every other case. It is a focused trial, not a full-suite result. A plan makes no model calls and shows the required calls before execution. Select a saved model, or add `--model YOUR_CODEX_MODEL_ID` to the real comparison.

Before applying the change, compare **all** cases:

```sh
rulebisect compare --proposed ../proposed-rules --plan
rulebisect compare --proposed ../proposed-rules --open
```

Inspect regressions, remaining failures and uncertainty individually. Passing these repeated checks is finite evidence about these cases; it is not a guarantee on unseen tasks. RuleBisect does not apply instruction changes automatically. Keep the original instructions unchanged while comparing so the baseline is meaningful.

### Choose the next command

| Your problem | Start here |
|---|---|
| I want to try it without Codex | `rulebisect demo --scenario regression --open` |
| I have a concrete failing task and check | `rulebisect init --wizard`, then `check --all` |
| My check cannot run reliably | Read the `check --all --open` report; fix setup or the verifier first |
| I want to locate failing instruction interactions | `rulebisect plan`, then `rulebisect run --open` |
| I want to edit a rule without losing the baseline | `draft`, selected `compare --plan`, then full `compare` |
| I want the latest saved report | `rulebisect report --latest --open` |

Reduction's `candidate/` is a smaller **failing reproducer**, not a proposed fix. Use `draft` to prepare a fix for comparison.

## 中文

完成[安装](../README.zh-CN.md)后，在要检查的 Git 仓库中运行命令。需要 Python 3.11+ 和 Git。真正的 `run`、`resume`、`compare` 执行会使用本机 Codex 登录和额度；演示是明确标注的确定性模拟。

### 从一个真实任务开始

```sh
rulebisect init --wizard
rulebisect doctor --offline
rulebisect check --all --open
```

向导需要你提供具体任务和独立的验证命令。它可以根据项目文件建议命令，但**不会执行推测出的命令**。初始化不调用模型。检查 `.rulebisect.json` 中选择的指令文件和保护文件；已有的 `init --task "..." --check "..." --model MODEL` 用法仍然可用。

`check --all` 在新的初始快照中执行每个案例的 setup 和验证器，不调用 Codex。退出 0 表示各验证器以 0（通过）或 1（行为失败）结束，**不代表全部行为通过**。任务尚未实现时，行为失败可能正是预期。退出 2 表示环境或执行故障。部分测试框架会把导入错误也归为 1，因此要看报告；必要时使用明确区分 0、1、2+ 的 Python 验证器。

### 把案例保存下来

```sh
rulebisect case add legacy-labels \
  --task "实现旧版标签契约，保留首尾空白。" --oracle verify_legacy.py
rulebisect case add modern-labels \
  --task "实现新版标签契约。" --check "python -m unittest tests.test_modern"
rulebisect case list --json
rulebisect check --all --open
```

每个案例选择 `--check "命令"` 或 `--oracle verifier.py`。命令不会经过 shell 展开，不支持管道；多步骤放进脚本。Python 验证器必须位于仓库内。案例命令支持 `--repo PATH` 和 `--config PATH`。

`rulebisect case remove modern-labels` 只删除案例配置，**保留验证器文件**。除了原始失败任务，建议保留一个当前能正常工作的任务，用来发现修改后的回归。

### 先小范围试跑，再检查全部案例

```sh
rulebisect draft --out ../proposed-rules
# 编辑 ../proposed-rules 内的指令副本。
rulebisect compare --proposed ../proposed-rules --cases legacy-labels --plan
rulebisect compare --proposed ../proposed-rules --cases legacy-labels --open
```

`--cases legacy-labels` **省略了其他所有案例**。局部通过不能当成全集通过。`--plan` 不调用模型，会显示所需调用次数；真实比较使用保存的模型，也可添加 `--model YOUR_CODEX_MODEL_ID`。

应用修改前，再运行完整比较：

```sh
rulebisect compare --proposed ../proposed-rules --plan
rulebisect compare --proposed ../proposed-rules --open
```

逐项查看改善、回归、仍然失败和不确定的结果。重复通过只支持这些案例的有限观察，不能保证其他任务。工具不会自动应用指令修改；对比期间保留仓库原始指令，确保基线有意义。

| 你遇到的问题 | 先运行什么 |
|---|---|
| 想先体验，不使用 Codex | `rulebisect demo --scenario regression --open` |
| 已有具体失败任务和验证方法 | `init --wizard`，然后 `check --all` |
| 验证器跑不起来 | 查看 `check --all --open` 报告，先修好环境或验证器 |
| 想定位触发失败的规则组合 | `plan`，然后 `run --open` |
| 修改规则，担心破坏其他任务 | `draft`，局部 `compare --plan`，最后完整 `compare` |
| 找不到刚才的报告 | `rulebisect report --latest --open` |

缩减生成的 `candidate/` 是更小的**失败复现**，不是修复建议。使用 `draft` 准备修复，再比较效果。
