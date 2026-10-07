"""A deterministic simulator for testing the reducer, not a model benchmark."""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from .experiment import Experiment

DEMO_RULES = '''Use UTF-8 when writing output files.

Select the legacy output format when a compatibility switch is enabled.

Keep diagnostic messages concise.

Enable the compatibility switch for this repository.

Use descriptive variable names.
'''
SIMULATOR = '''from pathlib import Path
import json
rules = Path("AGENTS.md").read_text()
legacy = "Select the legacy output format" in rules and "Enable the compatibility switch" in rules
Path("result.json").write_text(json.dumps({"format": "legacy" if legacy else "modern"}))
print("SIMULATOR: deterministic fixture, no Codex/model call")
'''
ORACLE = '''from pathlib import Path
import json
import sys
try:
    result = json.loads(Path("result.json").read_text())
except (FileNotFoundError, json.JSONDecodeError):
    sys.exit(1)
sys.exit(0 if result.get("format") == "modern" else 1)
'''


def run_demo(out: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="rulebisect-demo-") as directory:
        repo = Path(directory)
        (repo / "AGENTS.md").write_text(DEMO_RULES)
        (repo / "simulator.py").write_text(SIMULATOR)
        (repo / "verify.py").write_text(ORACLE)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        config = {"task": "SIMULATION ONLY: produce modern-format result.json",
                  "instructions": ["AGENTS.md"], "oracle": "verify.py",
                  "verify": [sys.executable, "{oracle}"], "protected_files": ["simulator.py"]}
        return Experiment(repo, config, out, None, 3, 90, 15,
                          [sys.executable, "simulator.py"]).execute()
