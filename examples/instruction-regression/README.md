# Before/after regression fixture

A deliberately constructed example: modern labels require trimming whitespace; a compatibility API requires preserving it. A blanket instruction change improves one contract and breaks the other. This is not a reported product defect.

Copy this folder outside an existing Git repository, then enter the copy:

```sh
git init
git add .gitignore AGENTS.md labels.py compatibility.py verify_modern.py verify_legacy.py
rulebisect compare --config experiment.json --proposed proposed --model YOUR_MODEL_ID --plan
rulebisect compare --config experiment.json --proposed proposed --model YOUR_MODEL_ID --open
```

Planned calls: 2 tasks × 2 instruction variants × 2 repetitions = 8. Real calls use your local Codex account. Instructions and code in the original copy remain unchanged. Model outcomes may vary; mixed/error outcomes must remain inconclusive. Neither the fixture nor finite observations establish causality or general effectiveness.

The proposed rule is intentionally broad. A more targeted proposal could scope whitespace conventions separately to the modern and compatibility APIs; use `draft` and edit a new copy, then compare again.
