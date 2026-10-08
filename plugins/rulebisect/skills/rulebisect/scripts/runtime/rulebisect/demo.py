"""A deterministic simulator for testing the reducer, not a model benchmark."""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from .experiment import Experiment
from .comparison import Comparison

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


COMPARE_SIMULATOR = '''from pathlib import Path
import json
rules = Path("AGENTS.md").read_text(encoding="utf-8")
strip_all = "Strip whitespace for all labels." in rules
strip_modern = strip_all or "Strip whitespace for modern labels only." in rules
Path("result.json").write_text(json.dumps({
    "modern": "sample" if strip_modern else " sample ",
    "legacy": "sample" if strip_all else " sample "
}), encoding="utf-8")
print("SIMULATOR: deterministic fixture, no Codex/model call")
'''


def run_comparison_demo(out: Path, *, fixed: bool = False) -> dict:
    """Demonstrate a caught regression or a scoped fix, without an installed Codex."""
    with tempfile.TemporaryDirectory(prefix="rulebisect-comparison-demo-") as directory:
        root = Path(directory)
        repo, proposed = root / "repo", root / "proposed"
        repo.mkdir()
        proposed.mkdir()
        (repo / "AGENTS.md").write_text("Preserve whitespace for all labels.\n", encoding="utf-8")
        (proposed / "AGENTS.md").write_text(
            "Strip whitespace for modern labels only.\nPreserve legacy label whitespace.\n" if fixed
            else "Strip whitespace for all labels.\n", encoding="utf-8")
        (repo / "simulator.py").write_text(COMPARE_SIMULATOR, encoding="utf-8")
        for name, expected in (("modern", "sample"), ("legacy", " sample ")):
            oracle = ("import json\nfrom pathlib import Path\n"
                      f"value = json.loads(Path('result.json').read_text(encoding='utf-8'))[{name!r}]\n"
                      f"raise SystemExit(0 if value == {expected!r} else 1)\n")
            (repo / f"verify_{name}.py").write_text(oracle, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        config = {"task": "SIMULATION ONLY: implement modern and legacy label contracts",
                  "instructions": ["AGENTS.md"], "oracle": "verify_modern.py",
                  "verify": [sys.executable, "{oracle}"], "protected_files": ["simulator.py"],
                  "cases": [{"id": "modern"}, {"id": "legacy", "oracle": "verify_legacy.py"}]}
        return Comparison(repo, config, out, None, 2, 8, 15, proposed,
                          runner=[sys.executable, "simulator.py"]).execute()
