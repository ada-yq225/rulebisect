from __future__ import annotations

import json
import hashlib
import shutil
import sys
import difflib
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from . import __version__
from .core import StopSearch, digest, reduce_failure, split_rules
from .report import write_report
from .runner import codex_command, codex_metadata, run_process


class Experiment:
    def __init__(self, repo: Path, config: dict, out: Path, model: str | None,
                 repeats: int, max_runs: int, timeout: int, runner: list[str] | None = None, resume_from: Path | None = None, max_tokens: int | None = None):
        self.repo, self.config, self.out = repo.resolve(), config, out.resolve()
        self.model, self.repeats, self.max_runs, self.timeout = model, repeats, max_runs, timeout
        self.runner = runner
        self.resume_from = resume_from
        self.max_tokens = max_tokens
        self.cache = {}
        self.progress = None
        self.rules = []
        self.blobs = {}
        self.report = {"schema_version": 1, "version": __version__, "status": "pending", "message": "",
                       "created_at": datetime.now(timezone.utc).isoformat(), "runner": "simulation" if runner else "codex",
                       "requested_model": model, "repeats": repeats, "max_runs": max_runs, "timeout_seconds": timeout,
                       "unit_mode": config.get("unit_mode", "paragraph"), "max_tokens": max_tokens, "task": config.get("task"), "trials": [], "evaluations": [], "candidate": [],
                       "limitations": ["Finite repeated observations; no causal or statistical-confidence claim.",
                                       "1-minimal means no tested single removal preserves failure, not globally smallest.",
                                       "Only explicitly selected paragraph units are varied; external instructions remain fixed.",
                                       "Snapshot is tracked working files; setup dependencies are recreated, not pinned. No Git history or security boundary."]}

    def relative(self, value: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("File paths must be non-empty strings")
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or ".git" in path.parts:
            raise ValueError(f"Expected a repository-relative path: {value}")
        if any((self.repo / Path(*path.parts[:i])).is_symlink() for i in range(1, len(path.parts) + 1)) or not (self.repo / path).resolve().is_relative_to(self.repo):
            raise ValueError(f"Symlinks and paths outside the repository are unsupported: {value}")
        return path.as_posix()

    def prepare(self, materialize: bool = True, check_codex: bool = True, instruction_overrides: dict[str, bytes] | None = None, allow_empty: bool = False):
        self.repo, self.out = self.repo.resolve(), self.out.resolve()
        if self.out.is_relative_to(self.repo):
            raise ValueError("Output directory must be outside the target repository")
        if self.out.exists() and any(self.out.iterdir()):
            raise ValueError("Output directory must be empty; existing evidence is never overwritten")
        if any(type(value) is not int for value in (self.repeats, self.max_runs, self.timeout)):
            raise ValueError("repeats, max_runs and timeout must be integers")
        if self.model is not None and (not isinstance(self.model, str) or not self.model.strip()):
            raise ValueError("model must be a non-empty string")
        if self.repeats < 2 or self.max_runs < self.repeats * 2 or self.timeout < 1:
            raise ValueError("Use repeats >= 2, max-runs >= 2 * repeats, timeout >= 1")
        if self.max_tokens is not None and (type(self.max_tokens) is not int or self.max_tokens < 1):
            raise ValueError("max-tokens must be positive")
        if not isinstance(self.config.get("task"), str) or not self.config["task"].strip():
            raise ValueError("Config requires a non-empty task")
        instructions = self.config.get("instructions")
        if not isinstance(instructions, list) or not instructions:
            raise ValueError("Config requires an explicit instructions list")
        verify = self.config.get("verify")
        if not isinstance(verify, list) or not verify or not all(isinstance(v, str) for v in verify):
            raise ValueError("verify must be an argument array, not a shell string")
        if "{oracle}" not in verify:
            raise ValueError("verify must reference {oracle}, an immutable verifier copy")
        setup = self.config.get("setup", [])
        if not isinstance(setup, list) or any(not isinstance(v, str) or not v for v in setup):
            raise ValueError("setup must be an argument array of non-empty strings, not a shell string")
        self.report["setup"] = setup
        oracle = self.relative(self.config.get("oracle", ""))
        if not (self.repo / oracle).is_file():
            raise ValueError("oracle must be an existing file")
        protected = self.config.get("protected_files", [])
        if not isinstance(protected, list):
            raise ValueError("protected_files must be a list")
        self.protected = [self.relative(v) for v in protected]
        instruction_paths = [self.relative(v) for v in instructions]
        if len(set(instruction_paths)) != len(instruction_paths):
            raise ValueError("Duplicate instruction files are unsupported")
        if set(instruction_paths) & (set(self.protected) | {oracle}):
            raise ValueError("Instruction files cannot also be verifier/protected files")
        root = subprocess.run(["git", "-c", "core.fsmonitor=false", "rev-parse", "--show-toplevel"], cwd=self.repo,
                              capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        if Path(root).resolve() != self.repo:
            raise ValueError("repo must be a Git repository root")
        tracked = subprocess.run(["git", "-c", "core.fsmonitor=false", "ls-files", "-z"], cwd=self.repo, capture_output=True,
                                 timeout=10, check=True).stdout.decode().split("\0")
        names = set(v for v in tracked if v) | set(instruction_paths) | {oracle} | set(self.protected)
        for name in sorted(names):
            name = self.relative(name)
            path = self.repo / name
            if path.is_dir():
                raise ValueError(f"Submodules/directories are unsupported: {name}")
            if not path.exists():
                if name in instruction_paths or name == oracle or name in self.protected:
                    raise ValueError(f"Required file is missing: {name}")
                continue  # tracked working-tree deletions are part of the snapshot
            self.blobs[name] = (path.read_bytes(), path.stat().st_mode & 0o777)
        self.report["source_snapshot_sha256"] = digest(json.dumps({"files": {name: digest(data) for name, (data, _) in self.blobs.items()}, "modes": {name: mode for name, (_, mode) in self.blobs.items()}}, sort_keys=True).encode())
        for name, data in (instruction_overrides or {}).items():
            if name not in instruction_paths or not isinstance(data, bytes):
                raise ValueError("Overrides must be bytes for selected instruction files only")
            self.blobs[name] = (data, self.blobs[name][1])
        for name in instruction_paths:
            self.rules.extend(split_rules(name, self.blobs[name][0].decode("utf-8"), len(self.rules), self.report["unit_mode"]))
        if not self.rules and not allow_empty:
            raise ValueError("No non-empty instruction units found")
        self.instruction_paths = instruction_paths
        self.oracle_name = oracle
        self.report["rules"] = [r.to_dict() for r in self.rules]
        self.report["snapshot"] = {name: digest(value[0]) for name, value in self.blobs.items()}
        self.report["file_modes"] = {name: value[1] for name, value in self.blobs.items()}
        self.report["snapshot_sha256"] = digest(json.dumps({"files": self.report["snapshot"], "modes": self.report["file_modes"]}, sort_keys=True).encode())
        self.report["agent_command"] = self.runner or codex_command(self.model)
        self.report["verify"] = verify
        self.report["oracle"] = oracle
        self.report["protected_files"] = self.protected
        if self.runner is None and check_codex:
            if not self.model:
                raise ValueError("Choose --model explicitly to keep requested model fixed")
            help_result = subprocess.run(["codex", "exec", "--help"], capture_output=True, text=True, timeout=10, check=True)
            for flag in ["--ignore-user-config", "--ephemeral", "--json"]:
                if flag not in help_result.stdout:
                    raise ValueError(f"Installed Codex lacks {flag}; update your CLI")
            self.report["codex_version"] = subprocess.run(["codex", "--version"], capture_output=True,
                                                           text=True, timeout=10, check=True).stdout.strip()
        if not materialize:
            return
        self.materialize()

    def materialize(self):
        """Write evidence for an already validated, frozen snapshot."""
        oracle = self.oracle_name
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "trials").mkdir()
        (self.out / "oracle").mkdir()
        self.oracle_path = self.out / "oracle" / Path(oracle).name
        self.oracle_path.write_bytes(self.blobs[oracle][0])
        self.oracle_path.chmod(0o400)
        self.report["message"] = "Prepared snapshot; experiment has not completed."
        if self.resume_from is not None:
            self.restore_checkpoint()
        write_report(self.out, self.report)

    def restore_checkpoint(self):
        previous_root = self.resume_from.resolve()
        if previous_root == self.out or self.out.is_relative_to(previous_root):
            raise ValueError("Resume output must be a new directory outside the previous evidence")
        previous = json.loads((previous_root / "report.json").read_text(encoding="utf-8"))
        for key in ("version", "runner", "requested_model", "codex_version", "snapshot_sha256", "task", "rules", "verify", "oracle", "protected_files", "repeats", "timeout_seconds", "unit_mode", "agent_command", "setup"):
            if previous.get(key) != self.report.get(key):
                raise ValueError(f"Cannot reuse evidence: {key} changed")
        if len(previous["trials"]) >= self.max_runs:
            raise ValueError("max-runs is a total limit; increase it to resume")
        for record in previous["trials"]:
            number = record["number"]
            source = previous_root / "trials" / f"{number:04d}"
            if not source.is_dir():
                raise ValueError(f"Prior trial evidence missing: {number}")
            shutil.copytree(source, self.out / "trials" / f"{number:04d}")
        self.report["trials"] = previous["trials"]
        self.report["evaluations"] = previous["evaluations"]
        self.report["previous_candidate"] = previous["candidate"]
        self.report["resumed_from"] = str(previous_root)
        for evaluation in previous["evaluations"]:
            if evaluation["outcome"] in ("pass", "fail") and evaluation["phase"] == "search":
                self.cache[tuple(evaluation["ids"])] = evaluation["outcome"]

    def token_count(self):
        return sum(usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                   for trial in self.report["trials"] for usage in trial.get("codex", {}).get("reported_usage", [])
                   if isinstance(usage, dict))

    def check_initial(self, *, prepared=False):
        if not prepared:
            self.prepare(check_codex=False)
        with tempfile.TemporaryDirectory(prefix="rulebisect-check-") as temporary:
            workspace = Path(temporary) / "repo"
            workspace.mkdir()
            self.workspace(workspace, [r.id for r in self.rules])
            setup = self.setup_workspace(workspace, self.out / "setup.log", [r.id for r in self.rules])
            self.report["setup_check"] = setup
            result = run_process(self.verify_command(), workspace, self.out / "check.log", self.timeout) if setup.get("exit_code") == 0 else {"exit_code": 2, "reason": "Environment setup failed; see setup.log"}
        self.report.update(kind="check", runner="verifier_only", requested_model=None, status="check_only", message="Initial snapshot check completed. No Codex or model calls made; inspect setup/check results.", verifier_check=result)
        write_report(self.out, self.report)
        return result

    def verify_command(self):
        replacements = {"{oracle}": str(self.oracle_path), "{python}": sys.executable}
        return [replacements.get(v, v) for v in self.config["verify"]]

    def workspace(self, path: Path, ids: list[int]):
        selected = set(ids)
        for name, (data, mode) in self.blobs.items():
            if name in self.instruction_paths:
                data = "".join(r.text for r in self.rules if r.path == name and r.id in selected).encode("utf-8")
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(mode)
        subprocess.run(["git", "init", "-q"], cwd=path, check=True, timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def setup_workspace(self, workspace, log, ids):
        argv = self.config.get("setup", [])
        if not argv:
            return {"exit_code": 0, "skipped": True}
        argv = [sys.executable if v == "{python}" else v for v in argv]
        result = run_process(argv, workspace, log, self.timeout)
        if result.get("exit_code") == 0:
            selected = set(ids)
            changed = []
            for name, (data, _) in self.blobs.items():
                if name in self.instruction_paths:
                    data = ''.join(r.text for r in self.rules if r.path == name and r.id in selected).encode('utf-8')
                target = workspace / name
                if target.is_symlink() or not target.resolve().is_relative_to(workspace.resolve()) or not target.is_file() or target.read_bytes() != data:
                    changed.append(name)
            if changed:
                result.update(exit_code=2, reason="Setup changed snapshot files", changed_files=changed)
        return result

    def untracked_files(self, workspace):
        output = subprocess.run(['git', '-c', 'core.fsmonitor=false', 'ls-files', '--others', '--exclude-standard', '-z'],
                                cwd=workspace, capture_output=True, timeout=10, check=True).stdout
        return set(name for name in output.decode().split('\0') if name) - set(self.blobs)

    def collect_changes(self, workspace, artifact, initial_untracked):
        changes, diffs = [], []
        new_files = self.untracked_files(workspace) - initial_untracked
        for name in sorted(set(self.blobs) | new_files):
            if name in self.instruction_paths:
                continue
            target = workspace / name
            before = self.blobs.get(name, (b'', 0))[0]
            safe = not target.is_symlink() and target.resolve().is_relative_to(workspace.resolve())
            if safe and target.is_file():
                # Bound the diff read; large/binary files still appear in the manifest.
                after = target.read_bytes() if target.stat().st_size < 200000 else None
                if name in self.blobs:
                    if after is None:
                        fingerprint = hashlib.sha256()
                        with target.open('rb') as stream:
                            for chunk in iter(lambda: stream.read(65536), b''):
                                fingerprint.update(chunk)
                        if fingerprint.hexdigest() == digest(before):
                            continue
                    elif after == before:
                        continue
                kind = 'added' if name in new_files else 'modified'
            else:
                after = b''
                kind = 'deleted' if not target.exists() and not target.is_symlink() else 'unsupported'
            changes.append({'path': name, 'kind': kind})
            if kind != 'unsupported' and after is not None and len(before) + len(after) < 200000 and b'\x00' not in before + after:
                lines = difflib.unified_diff(before.decode('utf-8', errors='replace').splitlines(True), after.decode('utf-8', errors='replace').splitlines(True),
                    fromfile='/dev/null' if kind == 'added' else 'before/' + name,
                    tofile='/dev/null' if kind == 'deleted' else 'after/' + name)
                for line in lines:
                    diffs.append(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n')
        if diffs:
            (artifact / 'changes.diff').write_text(''.join(diffs), encoding='utf-8')
        return changes

    def trial(self, ids: list[int], phase: str) -> dict:
        number = len(self.report["trials"]) + 1
        artifact = self.out / "trials" / f"{number:04d}"
        artifact.mkdir()
        record = {"number": number, "ids": ids, "phase": phase, "outcome": "error",
                  "artifacts": f"trials/{number:04d}", "state": "started"}
        self.report["trials"].append(record)
        (artifact / "trial.json").write_text(json.dumps(record, indent=2) + "\n")
        write_report(self.out, self.report)
        with tempfile.TemporaryDirectory(prefix="rulebisect-") as temporary:
            workspace = Path(temporary) / "repo"
            workspace.mkdir()
            self.workspace(workspace, ids)
            record["setup"] = self.setup_workspace(workspace, artifact / "setup.log", ids)
            initial_untracked = self.untracked_files(workspace)
            argv = self.runner or codex_command(self.model)
            if record["setup"].get("exit_code") == 0:
                record["agent"] = run_process(argv, workspace, artifact / "agent.log", self.timeout,
                                              None if self.runner else self.config["task"])
            else:
                record["agent"] = {"skipped": True}
                record["reason"] = record["setup"].get("reason", "Environment setup failed or timed out")
            if self.runner is None and not record["agent"].get("skipped"):
                record["codex"] = codex_metadata(artifact / "agent.log")
            # Preserve agent output before the verifier can create its own artifacts.
            record["file_changes"] = self.collect_changes(workspace, artifact, initial_untracked)
            record["changed_files"] = [v['path'] for v in record["file_changes"]]
            if record["agent"].get("exit_code") == 0:
                changed = []
                for name in self.protected:
                    target = workspace / name
                    if target.is_symlink() or not target.resolve().is_relative_to(workspace.resolve()) or not target.is_file() or target.read_bytes() != self.blobs[name][0]:
                        changed.append(name)
                record["changed_protected_files"] = changed
                # Do not execute a verifier if the immutable source has been altered externally.
                if self.oracle_path.read_bytes() != self.blobs[self.oracle_name][0]:
                    record["reason"] = "Immutable oracle changed; verification aborted"
                elif changed:
                    record["outcome"] = "fail"
                    record["reason"] = "Protected file changed"
                else:
                    verify = self.verify_command()
                    record["verifier"] = run_process(verify, workspace, artifact / "verify.log", self.timeout)
                    code = record["verifier"].get("exit_code")
                    if code in (0, 1):
                        record["outcome"] = "pass" if code == 0 else "fail"
                    else:
                        record["reason"] = "Verifier error: use exit 0=pass, 1=behavioral failure, 2+=setup error"
            elif not record["agent"].get("skipped"):
                record["reason"] = "Agent execution failed or timed out; not classified as task failure"
        record["state"] = "completed"
        (artifact / "trial.json").write_text(json.dumps(record, indent=2) + "\n")
        write_report(self.out, self.report)
        if self.progress is not None:
            self.progress(record)
        else:
            print(f"  run {number}/{self.max_runs}: {phase}, {len(ids)} units -> {record['outcome']}", flush=True)
        return record

    def evaluate(self, ids: list[int], phase: str = "search", fresh: bool = False) -> str:
        key = tuple(ids)
        if not fresh and key in self.cache:
            return self.cache[key]
        if len(self.report["trials"]) + self.repeats > self.max_runs:
            raise StopSearch("Execution budget reached before completing the next repeated evaluation.")
        trials = []
        for _ in range(self.repeats):
            if self.max_tokens is not None and self.token_count() >= self.max_tokens:
                raise StopSearch('Reported token limit reached. In-flight calls can exceed the limit; this is not a billing cap.')
            trials.append(self.trial(list(ids), phase))
            outcomes = {trial['outcome'] for trial in trials}
            if 'error' in outcomes or {'pass', 'fail'} <= outcomes:
                break  # An error or mixed outcome cannot become an all-pass/all-fail group.
        counts = {k: sum(t["outcome"] == k for t in trials) for k in ("pass", "fail", "error")}
        outcome = "error" if counts["error"] else "fail" if counts["fail"] == self.repeats else "pass" if counts["pass"] == self.repeats else "unstable"
        self.report["evaluations"].append({"ids": list(ids), "phase": phase, **counts, "outcome": outcome})
        write_report(self.out, self.report)
        if outcome in ("error", "unstable"):
            raise StopSearch(f"{phase}: {outcome} observations. No reliable reduction conclusion.")
        self.cache[key] = outcome
        if outcome == "fail" and ids and (not self.report["candidate"] or len(ids) < len(self.report["candidate"])):
            self.report["candidate"] = list(ids)
        return outcome

    def execute(self) -> dict:
        self.prepare()
        ids = [r.id for r in self.rules]
        self.report["status"] = "running"
        try:
            if self.evaluate(ids, "full-baseline", fresh=True) != "fail":
                self.report.update(status="not_reproduced", message="Full instruction set did not reproduce failure in every baseline repetition.")
            elif self.evaluate([], "empty-control", fresh=True) != "pass":
                self.report.update(status="control_failed", message="Failure persists with no selected instruction units. Reduction would not isolate these instructions.")
            else:
                candidate = reduce_failure(ids, self.evaluate)
                self.report["candidate"] = candidate
                if self.evaluate(candidate, "confirmation", fresh=True) != "fail":
                    raise StopSearch("Candidate failed to reproduce on fresh confirmation.")
                for rule_id in candidate:
                    if self.evaluate([r for r in candidate if r != rule_id], "single-removal", fresh=True) != "pass":
                        raise StopSearch("Fresh single-removal check still failed; minimality not confirmed.")
                self.report.update(status="observed_1_minimal", message="Candidate failed in every confirmation repetition; each tested single removal passed. This is observed 1-minimality, not causation or a global minimum.")
        except StopSearch as error:
            self.report.update(status="inconclusive", message=str(error))
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self.report.update(status="inconclusive", message=f"Experiment infrastructure error: {error}")
        except KeyboardInterrupt:
            self.report.update(status="interrupted", message="Interrupted; partial evidence retained. No completed conclusion.")
        finally:
            self.export_candidate()
            write_report(self.out, self.report)
        return self.report

    def export_candidate(self):
        selected = set(self.report["candidate"])
        root = self.out / "candidate"
        patch = []
        for name in self.instruction_paths:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            content = "".join(r.text for r in self.rules if r.path == name and r.id in selected)
            target.write_bytes(content.encode("utf-8"))
            if selected:
                original = self.blobs[name][0].decode("utf-8")
                patch.extend(difflib.unified_diff(original.splitlines(True), content.splitlines(True), fromfile='a/' + name, tofile='b/' + name))
        (self.out / "candidate.patch").write_text(''.join(patch), encoding='utf-8')
