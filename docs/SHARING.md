# Share an outcome / 分享结果

```sh
rulebisect share ../experiment-evidence --out ../summary.html
```

Pass an evidence directory or its `report.json`. This command reads a saved report,
makes no model calls and performs no upload. The output is one standalone HTML
file with no external assets or executable JavaScript. It works for reductions,
comparisons, verifier checks and labeled simulations, including older reports.

The output must be a **new `.html` file outside the evidence directory**, in an
existing parent directory. Existing files and symlink outputs are rejected. The
complete file is published atomically without overwriting; filesystems without
hard-link support return an error. Source JSON is limited to 10 MiB.

## What crosses the boundary

The exporter constructs a new document from fixed enums and bounded numbers. It
does not copy arbitrary text and attempt to scrub secrets afterward.

| Included | Excluded |
| --- | --- |
| Recognized status and a fixed explanation | Original report messages and arbitrary text |
| Report kind, tool version and source type | Model names, account/session identifiers |
| Trial, instruction and case counts | Instruction bodies, tasks and case IDs |
| Aggregate behavior outcomes and comparison verdicts | Code, patches, filenames and repository paths |
| Reported input/output/cached token totals | Commands, logs and timestamps |
| Omitted-case count and missing/partial-usage counts | Names or contents of omitted cases |

Malformed enum values become `unknown`. Usage that is missing stays marked
unknown; it is not zero cost. Cached input is already included in input tokens.
No monetary estimate or statistically significant conclusion is inferred.

The embedded `rulebisect-summary` JSON uses the same allowlist. Counts and recognized
metadata can still be sensitive. Review the exported file before publishing it.
It summarizes a report provided by the caller; it is **not authenticated evidence**,
an anonymity guarantee or a full reproduction bundle.

Full HTML, JSON, Markdown, issue drafts and source diffs stay in the original
evidence directory and may contain private information. For a maintainer to
reproduce a bug, prepare a separate minimal fixture and review its contents.
`share` does not post issues or publish to any service.

## 中文

给 `share` 传入证据目录或 `report.json`，再用 `--out` 指定一个证据目录外的新 HTML
文件。命令不会调用模型、上传或发布，只导出一页可离线打开的摘要。

导出采用固定字段白名单：状态、来源、数量、验证结论计数与已上报 Token。
不复制任务、指令正文、代码、文件名、仓库路径、用例 ID、模型、命令、日志或时间戳。
摘要中的 JSON 采用同一白名单。缺失用量不会当成零费用，缓存输入不重复相加。

已有文件不会覆盖，符号链接输出会拒绝；文件系统不支持原子硬链接发布时返回错误。
输入上限 10 MiB，输出父目录必须已经存在。摘要也需审查后再分享：汇总数字可能敏感，
它不是认证证据、匿名性保证或完整复现材料。完整报告仍留在原处，可能包含私有内容。
