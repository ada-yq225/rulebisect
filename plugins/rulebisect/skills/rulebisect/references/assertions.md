# Frozen output checks

Use deterministic file checks when success can be established from repository output. Prefer an existing independent test or custom oracle for program semantics that these checks cannot establish.

Save a JSON list inside a suitable task/config location:

```json
[
  {"type": "file_exists", "path": "result.json"},
  {"type": "json_equals", "path": "result.json", "pointer": "/format", "value": "modern"},
  {"type": "file_absent", "path": "debug.log"}
]
```

Initialize with the bundled launcher:

```text
init --repo REPO --task "Create modern result.json without debug.log" --assertions checks.json
```

Supported shapes:

| Type | Required fields | Meaning |
|---|---|---|
| file_exists | path | Existing regular file |
| file_absent | path | No file at the path |
| file_contains | path, text | UTF-8 text includes the literal |
| file_not_contains | path, text | UTF-8 text excludes the literal |
| file_matches | path, pattern | Python regex search matches UTF-8 text |
| json_equals | path, pointer, value | Exact JSON value/type at JSON Pointer |

JSON Pointer uses `/` segments and `~0`/`~1` for escaped tilde/slash; an empty pointer checks the entire document. Booleans are distinct from numbers. Regex uses Python search semantics, not full match; anchor it when the entire output matters. Review untrusted patterns before running them.

Paths must be safe repository-relative paths. Outputs may not follow symlink components. Verifiers limit file reads to 2 MiB; missing/invalid output is normally behavior failure, while read/symlink/size problems are execution errors. The initializer validates the schema and compiles checks into a standalone protected verifier. Keep that generated verifier fixed across reduction and both comparison arms. Missing output on initial code may be the intended initial failure.

For a second case, use `case add CASE --repo REPO --task "TASK" --assertions checks.json`. The input JSON is not reread after compilation; to change saved criteria, deliberately create/update the configuration with new reviewed criteria rather than editing the input file and assuming it changed the experiment.
