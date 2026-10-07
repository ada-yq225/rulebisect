# RuleBisect

**Codex 任务反复失败时，用实验找出值得检查的指令组合。**

永久免费、MIT 开源、只支持 Codex、无服务端和遥测。真实运行使用**你本机 Codex CLI 的登录身份和账户额度**；项目免费，模型调用仍可能产生费用。当前为实验性工具。

## 最简单的开始方式

需要 Python 3.11+ 和 Git。安装并登录 Codex CLI，在源码目录安装：

```sh
git clone https://github.com/ada-yq225/rulebisect.git
cd rulebisect
python3 -m pip install .
```

进入你要调查的 Git 仓库：

```sh
rulebisect init \
  --task "在 labels.py 中实现 normalize_label，遵循仓库约定" \
  --check "python -m unittest discover -s tests" \
  --model 你可用的Codex模型ID
rulebisect plan
rulebisect check
rulebisect run
```

`init` 自动发现已跟踪的 `AGENTS.md` 和 `AGENTS.override.md`，同目录存在 override 时优先选它；自动生成配置与验证器包装脚本，并把常见命名的测试文件加入保护列表。请检查这些选择是否符合你的任务。未跟踪的根目录指令也会纳入；未跟踪的嵌套指令、Skill 请用 `--instructions` 显式指定。

`plan` 检查快照和配置、显示指令数量与运行上限；`check` 在初始仓库副本里运行验证器。**这两个命令不调用模型。** 初始代码尚未实现时，验证失败可以是预期结果；先查看 `check.log` 确认不是依赖或测试配置错误。

`run` 每次从同一份初始快照开始，输出证据目录，默认放在仓库旁的 `.rulebisect-runs` 里，不会修改原仓库。模型与默认选项保存在 `.rulebisect.json`，之后通常只需 `rulebisect run`。

只想看效果、不想调用模型：

```sh
rulebisect demo --out ../rulebisect-demo
```

这是明确标注的**确定性模拟案例**，不是实际 Codex 效果的证明。

## 常用功能

| 命令 / 选项 | 用途 | 调用模型 |
|---|---|---|
| `doctor` | 检查 Python、Git、Codex 版本、登录和配置 | 否 |
| `init` | 自动生成配置和可信验证器包装脚本 | 否 |
| `inspect` | 阅读拆分后的指令及源文件行号 | 否 |
| `plan` | 检查配置、快照和运行预算 | 否 |
| `check` | 检查验证命令是否可执行 | 否 |
| `run` | 重复运行、删减指令、重新确认 | 是 |
| `resume --from 旧报告目录` | 复用匹配快照的稳定搜索结果，重新运行基线与最终确认 | 是 |
| `report 报告目录` | 从 JSON 重新生成 HTML / Markdown | 否 |
| `--unit-mode section` | 保留标题与段落结构，按标题节缩减 | 随所属命令 |
| `--unit-mode file` | 先定位哪个指令文件值得检查 | 随所属命令 |
| `--max-runs 30` | 限制总调用次数 | 随所属命令 |
| `--max-tokens 100000` | 已上报 Token 达上限后，不再启动下一次调用 | 随所属命令 |

Token 上限不是费用上限；单次调用可能越过它，缺失的用量无法计入。缓存输入已包含在输入 Token 里，不重复相加。不会自动估算金额。

默认每组重复 3 次；允许 `--repeats 2` 做较小实验。预算不足时输出“暂无法判断”，不会省略最终确认而宣称定位成功。

## 继续中断的实验

保持原仓库内容、配置角色、模型、Codex CLI 版本、工具版本、拆分方式、重复次数与超时一致：

```sh
rulebisect resume --from /旧证据目录 --max-runs 100
```

`max-runs` 是**包含旧运行的总次数上限**。续跑生成新的证据目录，保留旧日志；只复用已完成且稳定的搜索组，基线和最终确认会重新执行。快照或关键设置变化时拒绝复用。其他外部环境变化仍可能影响结果，因此复用不能证明整个环境完全一致。

## 报告里有什么

- 中文与英文标注的状态、下一步操作、完整指令与空指令的对照计数。
- 可搜索的指令地图，可只看候选保留的片段。
- 已上报 Token 用量、每次 Agent / 验证器日志和新增、修改和删除文件的代码差异。
- HTML、JSON、Markdown、精简 Issue 草稿、候选指令文件与差异补丁。

补丁只是调查建议，**不会自动应用**。先审查，再在其他任务上验证。代码差异覆盖已快照的非指令文件和未被 Git 忽略的新文件；准备依赖时产生的文件不算新文件证据，较大文件和二进制文件仅记录名称。精简 Issue 草稿默认不包含任务内容、指令正文或原始日志，分享前仍需检查版本等信息。

## 自动准备依赖

初始化时加上 `--setup "npm ci"`，或在 `.rulebisect.json` 中设置：

```json
"setup": ["{python}", "prepare_environment.py"]
```

每次新建仓库副本后、调用 Codex 前会执行准备命令；`check` 也会执行，因此能先排查环境。支持安装锁定依赖、创建本地虚拟环境等，日志保存在 `setup.log`，超时沿用 `timeout`。命令不通过 shell 执行；多步骤请写进脚本，`{python}` 使用运行 RuleBisect 的解释器。

准备命令失败、超时，或改动了快照文件的内容（包括指令和验证器）时，会在调用模型前停止。生成的依赖建议加入 Git 忽略并安装在副本中。原仓库的已安装依赖仍不会复制，外部服务或依赖版本也不保证固定；续跑要求准备命令一致。工具版本升级后，旧证据可阅读，不能跨版本续跑。

## 准确的验证器

`--check` 接受一条带引号的命令，不支持 shell 管道、重定向或多个命令。它把返回码 0 当作通过、1 当作行为失败、其他返回码当作环境错误。**有些测试框架的导入错误也会返回 1，工具无法自动区分**；需要精确归因时使用独立验证脚本：

```sh
rulebisect init --task "明确的任务" --oracle verify_behavior.py --model 模型ID
```

脚本退出码：**0 通过，1 目标行为失败，2+ 环境或验证器错误**。相对路径基于实验仓库根目录。验证器复制到副本外，修改受保护文件会判为失败；任意导入代码和外部依赖仍需要你信任。测试文件自动保护是命名启发式，请检查并补齐 `protected_files`。

## 结果的边界

完整指令必须反复失败，移除所选指令后必须反复通过，才开始缩减。最终候选再次反复失败，每个逐条移除的对照反复通过，才标为 `observed_1_minimal`。

这是有限次数的观察，不保证全局最小、不证明语义冲突或因果关系、不声称统计显著。遇到波动或执行异常会停止。默认按段落拆分；删除标题可能改变文档结构，必要时先用 `section` / `file` 模式。工具不确认每个片段是否实际加载，不复现全部外部上下文。

快照包含已跟踪文件的当前内容（包括未提交修改），以及显式指定的指令、验证器和保护文件。其他未跟踪/忽略文件、Git 历史、安装的依赖不复制；暂不支持符号链接、子模块。仓库副本不是容器或安全边界，仅运行可信仓库和验证命令。原始日志、代码差异和完整报告可能含私有代码，分享前检查。

## 开发与贡献

```sh
python3.11 -m unittest discover -s tests -v
```

当前已测试实际 Python 函数修改、确定性缩减、断点续跑、快照变化拒绝、Token 停止和无模型配置流程。准确结果见 [VALIDATION.md](VALIDATION.md)。v0.2 已通过 Linux/macOS/Windows 的 Python 3.11/3.13 六组 GitHub CI；新版验证记录见上述文档。

最有价值的贡献是可脱敏、可独立验证的真实失败案例。附模型和工具版本、任务、指令、验证条件与重复运行次数。

相关方法已有 [LLM Delta Debugging](https://www.amazon.science/publications/delta-debugging-for-llm-integrated-systems) 和 [skill-eval-harness](https://github.com/adewale/skill-eval-harness)。本项目探索从仓库失败任务得到更小指令组合和本地证据的工作流，不宣称全球首创。
