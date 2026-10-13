# Quick start / 快速上手

[English](#english) · [中文](#中文)

## English

After [installation](../README.md#install-and-run-your-own-experiment), run these commands inside the Git repository you want to investigate. Python 3.11+ and Git are required. Only real `run`, `resume` and `compare` executions use your installed Codex CLI, login and quota; the demos are deterministic simulations.

### Start with one real task

Run `rulebisect` for the entry points, or `rulebisect status` inside your repository for offline readiness and exact next steps. Status checks inputs without running setup, verifiers, Codex or login commands. Its exit 2 means inputs need attention; exit 0 means configuration is valid, not that tests pass. Custom configuration is supported with `status --config FILE`.

```sh
rulebisect init --wizard
rulebisect doctor --offline
rulebisect check --all --open
```

The wizard asks for a concrete task and an independent check. Choose `:exists`, `:contains`, or `:json` for a guided output check, `@checks.json` to import several checks, or your test command. It can suggest commands found in project files; it does **not** run those inferred commands. Initialization makes no model calls. Review the selected instructions and protected files in `.rulebisect.json`.

Python suggestions require evidence of pytest or unittest in project configuration or test source. Unknown frameworks get no guessed command. Confirm that your chosen command actually collects the intended checks.

Already using a custom instruction or Skill file? Use `rulebisect init --wizard --instructions rules.md`. Explicit files are validated before prompts or writes. JSON configuration errors name the selected file and the syntax error's line/column.

For an output-based task, [JSON assertions](ASSERTIONS.md) let you start without writing a verifier. Try the [complete output-contract fixture](../examples/output-contract/README.md). Saved checks are frozen; editing the input JSON later does not alter the verifier.

You can still initialize directly and save a model:

```sh
rulebisect init --task "Implement normalize_label in labels.py." \
  --check "python -m unittest discover -s tests" --model YOUR_CODEX_MODEL_ID
```

`check --all` runs setup and every case's verifier on fresh initial snapshots without Codex. Exit 0 means each verifier completed with 0 (pass) or 1 (behavior failure); **it does not mean all behaviors passed**. A failure can be expected before the task is implemented. Exit 2 indicates infrastructure trouble. Some frameworks also use 1 for import or setup errors: inspect the report, or use a verifier that returns 0 for pass, 1 for behavior failure, and 2+ for infrastructure failure.

For an automation gate, use `rulebisect check --all --require-pass`: selected passing behaviors exit 0, behavior failures exit 1, and execution problems exit 2. With `--cases`, omitted cases remain explicitly untested. A single `check` supports the same option.

### Include new source files and preview the snapshot

Snapshots contain Git-tracked current working files, including uncommitted edits, plus selected instructions, oracles, protected files and explicit `include_files`. For existing untracked source files, list their exact repository-relative paths when initializing:

```sh
rulebisect init --wizard --include labels.py src/new_helper.py
rulebisect status
rulebisect doctor --offline
rulebisect plan --json
```

`--include FILE ...` also works with direct `init` options and `--instructions`. Existing configs can add `"include_files": ["labels.py", "src/new_helper.py"]`. Entries must be existing files inside the repository; directories and symlinks are rejected, with no recursive selection or glob expansion. Git staging is unchanged.

`status` and `doctor` summarize inputs and warn about nonignored untracked omissions. View the full `snapshot_inputs` inventory with `status --json`, `doctor --offline --json`, `plan --json` or `compare --plan`; JSON includes omission counts and a bounded filename preview. Non-UTF-8 filename bytes are escaped for display, with counts based on the original names.

Included source files can still be edited by the task; put acceptance tests or verifier dependencies in `protected_files` to keep them unchanged. Review the inventory before `check` or a real experiment. Output the task has yet to generate may be expected to fail its initial check.

### Keep a custom configuration consistent

For an existing `experiment.json`, use the same config when checking, inspecting, drafting and comparing:

```sh
rulebisect status --config experiment.json
rulebisect check --config experiment.json --all --open
rulebisect inspect --config experiment.json
rulebisect draft --config experiment.json --out ../proposed-rules
rulebisect compare --config experiment.json --proposed ../proposed-rules --plan
```

With no `--config`, `inspect` and `draft` use the instruction selection in `.rulebisect.json` when present. Positional files explicitly select what `inspect` reads, for example `rulebisect inspect rules.md skills/review/SKILL.md`.

### Verifier paths and Git metadata

An `--oracle` verifier runs as an immutable copy outside the workspace, so direct sibling imports may fail. For a verifier that imports repository helpers, use `--check "python verify.py"` and add `verify.py` and those helpers to `protected_files`.

The source Git index and history are not copied. A verifier using `git ls-files` for discovery can see no files in the snapshot; give that check explicit file paths.

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

Supply exactly one of `--check "COMMAND"`, `--oracle verifier.py`, or `--assertions checks.json`. Commands use argv parsing, without shell pipes or expansion; put multiple steps in a wrapper script. The Python oracle must be inside the repository. Case commands accept `--repo PATH` and `--config PATH` for another repository or configuration.

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
| I do not know which step is next | `rulebisect status` |
| I want to try it without Codex | `rulebisect demo --scenario regression --open` |
| I have a concrete failing task and check | `rulebisect init --wizard`, then `check --all` |
| My untracked source is missing from checks | Review `status`; set `include_files` or use `init --include FILE ...` |
| My check cannot run reliably | Read the `check --all --open` report; fix setup or the verifier first |
| I want to locate failing instruction interactions | `rulebisect plan`, then `rulebisect run --open` |
| I want to edit a rule without losing the baseline | `draft`, selected `compare --plan`, then full `compare` |
| I want the latest saved report | `rulebisect report --latest --open` |
| I want an outcome summary without code or logs | `rulebisect share EVIDENCE --out summary.html` |

Reduction's `candidate/` is a smaller **failing reproducer**, not a proposed fix. Use `draft` to prepare a fix for comparison.

## 中文

完成[安装](../README.zh-CN.md)后，在要检查的 Git 仓库中运行命令。需要 Python 3.11+ 和 Git。真正的 `run`、`resume`、`compare` 执行会使用本机 Codex 登录和额度；演示是明确标注的确定性模拟。

### 从一个真实任务开始

直接运行 `rulebisect` 查看入口，或在目标仓库运行 `rulebisect status` 获取离线就绪状态和可复制的下一步命令。状态检查不运行准备命令、验证器、Codex 或登录命令；退出 2 表示输入需要处理，退出 0 只表示配置有效，不代表测试通过。自定义配置可使用 `status --config FILE`。

```sh
rulebisect init --wizard
rulebisect doctor --offline
rulebisect check --all --open
```

向导需要具体任务和独立检查。检查步骤可选 `:exists`、`:contains` 或 `:json`，`@checks.json` 导入多个条件，也可以填已有测试命令。它可以根据项目文件建议命令，但**不会执行推测出的命令**。初始化不调用模型。检查 `.rulebisect.json` 中选择的指令文件和保护文件；已有的 `init --task "..." --check "..." --model MODEL` 用法仍然可用。

Python 命令建议需要项目配置或测试源码中的 pytest / unittest 依据；框架不明时不会猜测命令。请确认所选命令确实收集到了要检查的测试。

已有自定义规则或 Skill 文件时，可运行 `rulebisect init --wizard --instructions rules.md`。显式文件在提示和写入前检查；配置 JSON 错误会指出实际文件及语法错误的行列。

文件输出任务可用 [JSON 断言](ASSERTIONS.md)，无需编写验证脚本；可直接跟做[完整案例](../examples/output-contract/README.md)。条件保存后会固化，修改输入 JSON 不会更新已保存验证器。

`check --all` 在新的初始快照中执行每个案例的 setup 和验证器，不调用 Codex。退出 0 表示各验证器以 0（通过）或 1（行为失败）结束，**不代表全部行为通过**。任务尚未实现时，行为失败可能正是预期。退出 2 表示环境或执行故障。部分测试框架会把导入错误也归为 1，因此要看报告；必要时使用明确区分 0、1、2+ 的 Python 验证器。

自动化需要要求行为通过时，使用 `rulebisect check --all --require-pass`：选中检查通过退出 0，行为失败退出 1，执行故障退出 2。搭配 `--cases` 时其余案例仍会明确显示未测试；单个 `check` 同样支持这个选项。

### 加入新写的源码，先预览快照

快照包含 Git 已跟踪文件的当前内容（包括未提交修改），以及选中的指令、验证器、保护文件和 `include_files`。已有未跟踪源码时，初始化可以明确选择仓库相对路径：

```sh
rulebisect init --wizard --include labels.py src/new_helper.py
rulebisect status
rulebisect doctor --offline
rulebisect plan --json
```

直接配置的 `init` 也支持 `--include 文件 ...`，并可与 `--instructions` 合用。已有配置可加入 `"include_files": ["labels.py", "src/new_helper.py"]`。每项须为仓库内已存在的普通文件；目录和符号链接会被拒绝，不递归选择，也不展开通配符，不自动暂存。

`status`、`doctor` 显示输入概要和遗漏提醒。完整 `snapshot_inputs` 清单可通过 `status --json`、`doctor --offline --json`、`plan --json` 或 `compare --plan` 查看；JSON 含遗漏数量和有限的文件名预览。非 UTF-8 文件名字节会转义显示，数量按原始名称统计。

加入快照的源码仍可修改；需要固定的验收测试或验证器依赖应放进 `protected_files`。先核对清单，再执行 `check` 或真实实验。任务尚未生成输出时，初始行为失败可能正是预期。

### 自定义配置贯穿同一流程

已有 `experiment.json` 时，检查、查看指令、准备草案、对照都使用同一个配置：

```sh
rulebisect status --config experiment.json
rulebisect check --config experiment.json --all --open
rulebisect inspect --config experiment.json
rulebisect draft --config experiment.json --out ../proposed-rules
rulebisect compare --config experiment.json --proposed ../proposed-rules --plan
```

未传 `--config` 时，有 `.rulebisect.json` 的仓库会让 `inspect` 和 `draft` 使用保存的指令选择。`inspect` 的位置参数明确选择要查看的文件，例如 `rulebisect inspect rules.md skills/review/SKILL.md`。

### 验证器路径与 Git 元数据

`--oracle` 验证器以不可变副本在工作区外执行，直接导入同目录模块可能失败。验证器需要仓库内辅助模块时，可使用 `--check "python verify.py"`，并把 `verify.py` 和所需模块加入 `protected_files`。

源 Git 索引和历史不会复制。依赖 `git ls-files` 发现文件的检查可能在快照中得到空列表，应改为明确指定要检查的文件路径。

### 把案例保存下来

```sh
rulebisect case add legacy-labels \
  --task "实现旧版标签契约，保留首尾空白。" --oracle verify_legacy.py
rulebisect case add modern-labels \
  --task "实现新版标签契约。" --check "python -m unittest tests.test_modern"
rulebisect case list --json
rulebisect check --all --open
```

每个案例在 `--check "命令"`、`--oracle verifier.py`、`--assertions checks.json` 中选一项。命令不会经过 shell 展开，不支持管道；多步骤放进脚本。Python 验证器必须位于仓库内。案例命令支持 `--repo PATH` 和 `--config PATH`。

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
| 不知道当前该做哪一步 | `rulebisect status` |
| 想先体验，不使用 Codex | `rulebisect demo --scenario regression --open` |
| 已有具体失败任务和验证方法 | `init --wizard`，然后 `check --all` |
| 新写的未跟踪源码没有进入检查 | 查看 `status`；配置 `include_files` 或初始化时使用 `--include 文件 ...` |
| 验证器跑不起来 | 查看 `check --all --open` 报告，先修好环境或验证器 |
| 想定位触发失败的规则组合 | `plan`，然后 `run --open` |
| 修改规则，担心破坏其他任务 | `draft`，局部 `compare --plan`，最后完整 `compare` |
| 找不到刚才的报告 | `rulebisect report --latest --open` |
| 只想分享结果，不带代码或日志 | `rulebisect share 证据目录 --out summary.html` |

缩减生成的 `candidate/` 是更小的**失败复现**，不是修复建议。使用 `draft` 准备修复，再比较效果。
