# Install and submit RuleBisect / 安装与 OpenAI 投稿

**Status: ready-for-upload; not submitted.** Developer identity verification has
not been completed. This package has not been approved or listed by OpenAI.
**状态：待上传，尚未提交。** 开发者身份验证尚未完成；不代表已获审核通过或官方收录。

The Skill/plugin package is **0.1.0** and includes the **RuleBisect 0.7.0** engine.
Use Python **3.11+** and Git. No `pip install` is needed. Real experiments additionally
need an installed Codex CLI using your existing login and quota or billing.
Skill/插件包版本为 **0.1.0**，内置引擎为 **0.7.0**；需要 Python **3.11+** 和 Git，
无需 pip 安装。真实实验另需已安装并登录的 Codex CLI，使用你的现有额度或计费。

[Download the Skill/plugin ZIPs and checksums / 下载 ZIP 与校验和](https://github.com/ada-yq225/rulebisect/releases/tag/skill-v0.1.0).
Local validation: **178 tests passed**, including extracted-package workflows;
this distribution's validation used **zero real model calls**. See [validation limits](../VALIDATION.md).
本地验证通过 **178 项测试**，包含解压后的独立运行；本次分发验证**零真实模型调用**。

## Choose one installation / 选择一种安装方式

Install the plugin **or** the standalone Skill to avoid duplicate Skill entries.
插件与独立 Skill 二选一，避免同一个 Skill 重复出现。

### A. Repository marketplace / 仓库插件源

Add the repository with the installed Codex CLI:
使用已安装的 Codex CLI 添加仓库：

```sh
codex plugin marketplace add ada-yq225/rulebisect
```

Open the Codex Plugins Directory, choose the RuleBisect repository source, select
**RuleBisect → Install**, then start a new chat/session. The repository catalog is
`.agents/plugins/marketplace.json`; its plugin is in `plugins/rulebisect/`.
打开 Codex 插件目录，选择 RuleBisect 仓库源，点击 **RuleBisect → Install**，
然后开启新会话。仓库目录清单为 `.agents/plugins/marketplace.json`，插件位于
`plugins/rulebisect/`。这是仓库安装，不表示已进入 OpenAI 官方目录。

### B. Standalone Skill / 独立 Skill

In Codex, ask the built-in installer to use the exact Skill directory:
在 Codex 中请求内置安装器安装这个确切的 Skill 路径：

```text
$skill-installer Install the rulebisect skill from https://github.com/ada-yq225/rulebisect/tree/main/plugins/rulebisect/skills/rulebisect
```

Alternatively, use `rulebisect-skill-0.1.0.zip`. It has `SKILL.md` at the archive root;
extract into a **new** `~/.codex/skills/rulebisect/` directory on macOS/Linux or
`%USERPROFILE%\.codex\skills\rulebisect\` on Windows. Stop if that directory exists.
也可使用独立 Skill ZIP；包根目录直接含 `SKILL.md`，解压到上述**新建**目标目录。
目标已存在时停止并检查已有安装，不自动覆盖。

From the directory containing the ZIP, on macOS/Linux / 在 ZIP 所在目录执行：

```sh
if [ -e "$HOME/.codex/skills/rulebisect" ] || [ -L "$HOME/.codex/skills/rulebisect" ]; then
  echo "Already installed; inspect before replacing."
else
  mkdir -p "$HOME/.codex/skills/rulebisect"
  unzip -n rulebisect-skill-0.1.0.zip -d "$HOME/.codex/skills/rulebisect"
fi
```

The final layout must be / 最终结构必须为：

```text
~/.codex/skills/rulebisect/
├── SKILL.md
├── LICENSE
├── agents/openai.yaml
├── references/
└── scripts/
    ├── rulebisect_cli.py
    └── runtime/
        ├── LICENSE
        └── rulebisect/
```

Keep the complete bundled runtime. Start a new Codex chat/session after installation.
保留完整内置运行时，安装后开启新的 Codex 会话。

## Verify and use / 验证与使用

From a complete repository checkout, check the bundled launcher directly:
在包含完整内置引擎的仓库根目录，直接检查启动器：

```sh
python3 plugins/rulebisect/skills/rulebisect/scripts/rulebisect_cli.py --version
python3 plugins/rulebisect/skills/rulebisect/scripts/rulebisect_cli.py demo --scenario regression
```

For a standalone installation, substitute the installed Skill path; on Windows
use your Python 3.11+ interpreter. The expected engine version is `0.7.0`. The demo
is a constructed simulation with **zero model calls**. `doctor --offline` and `plan`
also need no model calls; `check` runs trusted setup/verifiers without an agent.
独立安装时替换为已安装的 Skill 路径；Windows 使用你的 Python 3.11+ 解释器。
引擎版本应为 `0.7.0`。演示是**零模型调用**的构造模拟；离线诊断和计划也不调用模型，
`check` 会执行已接受的准备命令和验证器，但不运行代理。

The Skill declares `products: [CODEX]` and `allow_implicit_invocation: true`.
Explicit user instructions take priority. Before real `run`/`compare`/`resume`, agree
on task, repository, model, repeats and total execution budget. Existing session
authorization remains valid; do not ask for the same budget again.
Skill 仅声明用于 Codex，允许按任务隐式启用；明确用户指令优先。真实实验前确认任务、
仓库、模型、重复次数及总执行预算；会话已有授权继续有效，不重复询问同一预算。

## Submit to OpenAI / 向 OpenAI 投稿

Use **`rulebisect-plugin-0.1.0.zip`**, not the standalone Skill ZIP, for the public
plugin submission. It contains the plugin manifest, branding and bundled Skill;
there is no MCP server, remote authentication configuration or lifecycle hook.
官方插件投稿使用 **`rulebisect-plugin-0.1.0.zip`**，而非独立 Skill ZIP；包内含插件
清单、图标和 Skill，不含 MCP、远程认证配置或生命周期 hooks。

1. Select your organization/project and complete individual developer verification.
   Organization owners can submit; other members need **Apps Management Write**.
   / 选择组织和项目，完成个人开发者验证；组织所有者或有上述权限的成员可投稿。
2. Open [Platform Plugins](https://platform.openai.com/plugins), choose your verified
   developer identity, and upload the plugin ZIP. / 选择已验证发布身份并上传插件 ZIP。
3. Resolve package metadata and Skill scan findings, then upload corrections as
   needed. Passing upload checks does not guarantee directory eligibility.
   / 处理元数据和 Skill 扫描问题；上传检查通过不保证目录资格。
4. Review the final draft and complete the policy attestations yourself before
   **Submit for review**. / 本人确认最终稿并完成政策声明后提交审核。
5. Track the review outcome; if approved, choose **Publish plugin** when ready.
   / 查看审核结果；获批后自行选择发布时间。

Follow the [official submission flow](https://developers.openai.com/plugins/deploy/submission),
[package guide](https://developers.openai.com/plugins/build/plugins) and
[skills-only requirements](https://developers.openai.com/plugins/plugin-guidelines#skills).
The deprecated `openai/skills` repository is not the submission route; this guide
does not submit a PR or send a message to OpenAI.
以官方投稿、打包及纯 Skill 要求为准；不向已弃用的 `openai/skills` 发起投稿 PR。

Support / 支持：[GitHub Issues](https://github.com/ada-yq225/rulebisect/issues).
Privacy / 隐私：[PRIVACY.md](../PRIVACY.md).
