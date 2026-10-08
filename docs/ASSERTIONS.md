# Output checks / 输出验收条件

[English](#english) · [中文](#中文)

## English

Use these checks when success has an observable file result. They do not execute
the program being developed or judge arbitrary prose quality. For API behavior,
test suites or several program executions, use `--check` or `--oracle` instead.

Save a nonempty JSON array as `checks.json`:

```json
[
  {"type": "file_exists", "path": "result.json"},
  {"type": "json_equals", "path": "result.json", "pointer": "/format", "value": "modern"},
  {"type": "json_equals", "path": "result.json", "pointer": "/items/0", "value": "alpha"},
  {"type": "file_absent", "path": "debug.log"}
]
```

```sh
rulebisect init --task "Create the required result.json." --assertions checks.json
rulebisect doctor --offline
rulebisect check --all --open
rulebisect run --model YOUR_CODEX_MODEL_ID --open
```

Only the last command calls Codex. The initial check may fail because output does
not exist yet. A result file must be written into the trial repository: saying it
was created in the assistant's final message does not satisfy these checks.

### Supported checks

Each object accepts **exactly** the fields shown; unknown fields are rejected.
All checks run. Every check must pass for the verifier to pass.

| Type | Required fields besides `type` | Meaning |
| --- | --- | --- |
| `file_exists` | `path` | A regular output file exists. |
| `file_absent` | `path` | No file exists at the selected path. |
| `file_contains` | `path`, `text` | UTF-8 file contains the exact, case-sensitive substring. |
| `file_not_contains` | `path`, `text` | UTF-8 file exists and excludes the substring. |
| `file_matches` | `path`, `pattern` | UTF-8 file matches Python regex **search**, not full match. |
| `json_equals` | `path`, `pointer`, `value` | Valid JSON at the pointer equals the expected JSON value. |

```json
[
  {"type": "file_contains", "path": "README.md", "text": "Quick start"},
  {"type": "file_not_contains", "path": "README.md", "text": "TODO"},
  {"type": "file_matches", "path": "version.txt", "pattern": "^v[0-9]+\\.[0-9]+\\.[0-9]+\\s*$"}
]
```

JSON Pointer uses `/items/0` for an array item, `~1` for a literal slash and `~0`
for a literal tilde in a key. `"pointer": ""` checks the entire JSON document.
Objects ignore key order, arrays preserve order, booleans differ from numbers
(`true` is not `1`), and numerically equal JSON numbers such as `1` and `1.0`
compare equal. Nonfinite numbers are rejected.

### Wizard and regression cases

At the `init --wizard` check prompt, choose:

- `:exists`: enter an output path.
- `:contains`: enter a path and required exact text.
- `:json`: enter a path, JSON Pointer and a JSON literal such as `"modern"`, `true`, or `42`.
- `@checks.json`: import several checks; the JSON file path is relative to the shell's current directory.

```sh
rulebisect case add saved-output --task "Create the existing output contract." --assertions checks.json
rulebisect check --all
rulebisect draft --out ../proposed-rules
# Edit the proposed instruction copies, then validate all saved cases:
rulebisect compare --proposed ../proposed-rules --plan
rulebisect compare --proposed ../proposed-rules --model YOUR_CODEX_MODEL_ID --open
```

Choose exactly one of `--assertions`, `--check` or `--oracle` when saving a task.
The generated verifier contains a frozen copy of the checks and uses only Python's
standard library. It remains independent of the mutable workspace and does not
require RuleBisect to be installed inside it. Expected values and file contents
are not printed in assertion result logs; full reports and source diffs can still
contain private data.

**Editing `checks.json` later does not update the saved verifier.** Add a new case
for a changed contract, or deliberately edit the generated verifier and treat it
as a new experiment. Changed verifier/snapshot hashes prevent reuse of old search
evidence. The verifier can be visible to Codex; these are not blind benchmarks.

### Errors and limits

- Paths are repository-relative and use `/` on every OS. Absolute paths, `..`, `.git`, backslashes, drive letters and symlink components are rejected.
- Outputs must be regular files of at most **2 MiB**, including existence/absence checks. Directories and symlinks are infrastructure errors.
- Missing required output or a mismatched value is a behavior failure (verifier exit 1). Invalid UTF-8/JSON also fails when a text/JSON check reads the file; `file_exists` accepts binary files within the size limit.
- Permission errors, oversized outputs and unsupported output paths are infrastructure errors (exit 2). Infrastructure errors take priority if several checks fail.
- Regexes are validated before saving; their runtime is bounded by the existing verifier process timeout. Prefer simple patterns.
- Verifier exit 0 means every check passed. `check --all` command exit 0 means every verifier ran with code 0 or 1; consult the report for behavior verdicts.

Small checks only establish the properties you specify. Include regression cases
for already-working behavior before changing shared instructions. See the
[output-contract fixture](../examples/output-contract/README.md).

## 中文

输出验收条件适合“成功时应生成什么文件、包含什么文本、JSON 应是什么值”的任务。
它不会替你执行待开发程序，也不自动评估任意文字质量。函数、API 或复杂行为用已有
测试命令或自定义验证器。

把上面的非空 JSON 数组保存为 `checks.json`，然后使用 `init --assertions checks.json`。
六种类型分别检查文件存在、不存在、包含文本、不含文本、正则匹配、JSON 值。
字段必须和表格完全一致，所有条件都通过才算验证器通过。JSON 路径 `/items/0`
表示数组第一项；空字符串表示整个文档；`true` 与 `1` 不相等。

向导的检查步骤支持 `:exists`、`:contains`、`:json`；也可输入 `@checks.json` 导入多个
条件，输入文件路径相对于当前 shell 目录。新增回归案例同样支持
`case add ID --task "任务" --assertions checks.json`。先 `check --all` 验证环境，再用
`run` 定位失败规则或 `draft` + `compare` 检查修改。

条件在保存时固化到受保护的独立验证器中，**修改输入 JSON 不会更新已保存条件**。
契约变化时新增案例，或明确编辑生成的验证器；旧证据不能跨验证器变化复用。
结果日志不会打印预期值和实际文件正文，但完整报告及代码差异仍可能含私有内容。

输出路径必须相对于仓库，跨平台统一用 `/`。文件上限 2 MiB，不支持目录、符号链接、
仓库外路径或 `.git`。缺失或内容不符返回行为失败 1；文本/JSON 检查读取文件时，
无效 UTF-8/JSON 也返回 1，单纯存在检查允许大小合规的二进制文件。权限、大小、
路径等环境问题返回 2。正则是搜索匹配，可用锚点约束全文，超时受验证器进程控制。
`check --all` 自身返回 0 只说明验证器可执行，不代表行为全部通过，请看报告。
