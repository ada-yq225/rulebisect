from __future__ import annotations
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from rulebisect.core import reduce_failure, split_rules
from rulebisect.demo import DEMO_RULES, ORACLE, SIMULATOR
from rulebisect.experiment import Experiment
from rulebisect.runner import codex_command, run_process

class ReductionTests(unittest.TestCase):
    def test_interacting_units(self):
        result = reduce_failure(list(range(8)), lambda ids: "fail" if {2, 6} <= set(ids) else "pass")
        self.assertEqual(result, [2, 6])

    def test_non_monotonic_alternative_failures(self):
        def check(ids):
            selected = set(ids)
            return "fail" if ({0, 1} <= selected and 3 not in selected) or {2, 3} <= selected else "pass"
        result = reduce_failure([0, 1, 2, 3], check)
        self.assertEqual(check(result), "fail")
        for item in result:
            self.assertEqual(check([v for v in result if v != item]), "pass")

    def test_preserves_fences_and_bytes(self):
        text = "\nIntro\r\n\r\n```python\nprint(1)\n\nprint(2)\n```\n\nEnd\n\n\n"
        units = split_rules("AGENTS.md", text)
        self.assertEqual("".join(u.text for u in units), text)
        self.assertEqual(len(units), 3)
        self.assertIn("print(1)\n\nprint(2)", units[1].text)

    def test_codex_never_uses_bypass(self):
        command = codex_command("example-model")
        self.assertIn("workspace-write", command)
        self.assertIn("--ignore-user-config", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertEqual(command[-1], "-")

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        for name, text in {"AGENTS.md": DEMO_RULES, "simulator.py": SIMULATOR, "verify.py": ORACLE}.items():
            (self.repo / name).write_text(text)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        self.config = {"task": "simulation", "instructions": ["AGENTS.md"], "oracle": "verify.py",
                       "verify": [sys.executable, "{oracle}"], "protected_files": ["verify.py"]}

    def tearDown(self):
        self.temporary.cleanup()

    def experiment(self, max_runs=90, code=None):
        runner = [sys.executable, "simulator.py"] if code is None else [sys.executable, "-c", code]
        return Experiment(self.repo, self.config, self.root / "evidence", None, 2, max_runs, 10, runner)

    def test_pipeline_confirmation_and_originals(self):
        original = {p.name: p.read_bytes() for p in self.repo.iterdir() if p.is_file()}
        report = self.experiment().execute()
        self.assertEqual(report["status"], "observed_1_minimal")
        self.assertEqual(report["candidate"], [1, 3])
        for name, data in original.items():
            self.assertEqual((self.repo / name).read_bytes(), data)
        evaluations = report["evaluations"]
        self.assertEqual(sum(e["phase"] == "confirmation" for e in evaluations), 1)
        self.assertEqual(sum(e["phase"] == "single-removal" for e in evaluations), 2)
        self.assertTrue((self.root / "evidence/report.html").is_file())
        self.assertEqual(json.loads((self.root / "evidence/report.json").read_text())["status"], report["status"])

    def test_budget_incomplete_not_success(self):
        report = self.experiment(max_runs=4).execute()
        self.assertEqual(report["status"], "inconclusive")
        self.assertEqual(len(report["trials"]), 4)

    def test_setup_failure_not_behavior_failure(self):
        report = self.experiment(code="raise SystemExit(2)").execute()
        self.assertEqual(report["status"], "inconclusive")
        self.assertEqual(report["evaluations"][0]["error"], 1)
        self.assertEqual(report["evaluations"][0]["fail"], 0)

    def test_verifier_setup_failure_not_behavior_failure(self):
        (self.repo / "verify.py").write_text("raise SystemExit(2)")
        report = self.experiment().execute()
        self.assertEqual(report["status"], "inconclusive")
        self.assertEqual(report["evaluations"][0]["error"], 1)

    def test_removed_rules_still_failing(self):
        report = self.experiment(code='from pathlib import Path; Path("result.json").write_text(\'{"format":"legacy"}\')').execute()
        self.assertEqual(report["status"], "control_failed")

    def test_full_set_passing(self):
        report = self.experiment(code='from pathlib import Path; Path("result.json").write_text(\'{"format":"modern"}\')').execute()
        self.assertEqual(report["status"], "not_reproduced")

    def test_noise_stops_search(self):
        exp = self.experiment()
        def trial(ids, phase):
            record = {"outcome": "pass" if len(exp.report["trials"]) % 2 else "fail"}
            exp.report["trials"].append(record)
            return record
        exp.trial = trial
        self.assertEqual(exp.execute()["status"], "inconclusive")
        self.assertEqual(exp.report["evaluations"][0]["outcome"], "unstable")

    def test_agent_cannot_make_modified_verifier_pass(self):
        code = 'from pathlib import Path; Path("verify.py").write_text("raise SystemExit(0)")'
        report = self.experiment(code=code).execute()
        self.assertEqual(report["status"], "control_failed")
        self.assertTrue(all(t["reason"] == "Protected file changed" for t in report["trials"]))

    def test_oracle_outside_workspace(self):
        self.config["protected_files"] = []
        code = 'from pathlib import Path; Path("verify.py").write_text("raise SystemExit(0)"); Path("result.json").write_text(\'{"format":"legacy"}\')'
        report = self.experiment(code=code).execute()
        self.assertEqual(report["status"], "control_failed")
        self.assertTrue(all(t["verifier"]["exit_code"] == 1 for t in report["trials"]))

    def test_reject_path_traversal_and_nested_output(self):
        self.config["instructions"] = ["../outside.md"]
        with self.assertRaises(ValueError):
            self.experiment().prepare()
        self.config["instructions"] = ["AGENTS.md"]
        exp = self.experiment()
        exp.out = self.repo / "out"
        with self.assertRaises(ValueError):
            exp.prepare()

    @unittest.skipIf(sys.platform == "win32", "Symlink creation requires elevated Windows privilege")
    def test_reject_symlink_snapshot(self):
        target = self.root / "outside.txt"
        target.write_text("outside")
        (self.repo / "link.txt").symlink_to(target)
        subprocess.run(["git", "add", "link.txt"], cwd=self.repo, check=True)
        with self.assertRaises(ValueError):
            self.experiment().prepare()

    def test_cli_demo(self):
        result = subprocess.run([sys.executable, "-m", "rulebisect", "demo", "--out", str(self.root / "demo")],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SIMULATION", result.stdout)
        self.assertEqual(json.loads((self.root / "demo/report.json").read_text())["candidate"], [1, 3])

    def test_timeout_not_behavior_failure(self):
        result = run_process([sys.executable, "-c", "import time; time.sleep(5)"], self.repo, self.root / "timeout.log", 1)
        self.assertEqual(result["status"], "timeout")

if __name__ == "__main__":
    unittest.main()
