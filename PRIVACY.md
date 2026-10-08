# Privacy and local data

Effective date: 2026-10-08. This describes the free, MIT-licensed RuleBisect CLI and its bundled Codex Skill. RuleBisect has no hosted application, account system, telemetry, analytics, or automatic report uploads.

## Local experiments

RuleBisect reads the Git repository, selected instructions, task descriptions, configuration and acceptance checks that you choose. It creates local repository copies to run experiments. Configuration, task text, instructions, source diffs, subprocess output, model events and reported token usage can appear in local evidence directories and reports. These files may contain private information from your project or commands.

Setup, planning, verifier checks, report generation and deterministic demos do not call a model. Verifier and setup commands are programs you select; their own network access and data handling depend on those programs and the execution environment. Local workspace copies are not containers.

## When you choose real Codex experiments

Real experiments launch your installed Codex CLI, using its existing authentication, configuration and access controls. Codex can send task and repository context to its configured service. That service's terms, privacy settings and data handling apply separately. RuleBisect does not request account credentials, provide an independent login, or run its own model service. Review your Codex configuration and the agreed execution budget before starting an experiment.

Installing this Skill in Codex also puts its use within the Codex environment: context read by the assistant is subject to that environment's data handling. "Local evidence" does not mean that an assistant can inspect repository content without any provider processing.

## Retention and sharing

You control local retention. Delete experiment output directories when you no longer need them, and remove saved RuleBisect configuration/verifiers when removing a project setup. RuleBisect does not delete your repository or automatically clean up retained evidence.

Full HTML, JSON, Markdown reports and compact issue drafts can include private project details. Review them before sharing. The `share` command writes a separate local, aggregate-only summary that omits task text, instructions, code, filenames, models, commands and logs; it does not upload that summary. Counts and outcomes can still disclose information you prefer to keep private.

Downloading releases or installing the GitHub marketplace contacts the source host through the tool used for installation. These are user-initiated installation actions, separate from experiment telemetry. OpenAI's plugin platform handles any directory installation or submission data under its own policies.

## Support

The maintainer is [ada-yq225](https://github.com/ada-yq225). Report product or privacy questions through [GitHub Issues](https://github.com/ada-yq225/rulebisect/issues). Issues are public: share a minimal reproduction or reviewed aggregate summary, and do not post credentials, private source, account logs or raw private evidence. The maintainer receives information you choose to post there, subject to GitHub's own data handling.

---

## 中文说明

RuleBisect 永久免费、MIT 开源，没有自建账户、遥测、分析服务或自动报告上传。任务、规则、代码副本、差异、命令输出和模型事件保存在你选择的本地目录，可能包含项目隐私。你可以自行删除这些输出。

初始化、计划、独立验证、报告及确定性演示不调用模型。你选择的验证或环境准备命令可能有自己的网络行为。真实实验调用本机已有登录的 Codex CLI，相关任务与仓库上下文会受所配置服务的数据处理规则约束。Skill 在 Codex 中读取的上下文也受 Codex 环境的数据处理规则约束；本地保存证据不代表模型从不接触上下文。

完整报告和 issue 草稿需要检查后再分享。`share` 只在本地生成排除任务、规则、代码、文件名、模型、命令和日志的汇总页，不上传；汇总的数量和结论也可能是敏感信息。安装下载由你使用的安装工具访问来源服务。

支持入口是上述 GitHub Issues，内容公开，请只提交最小复现或检查过的汇总，不要发布凭据、私有代码或账户原始日志。
