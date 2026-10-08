"""Check every independent verifier before committing model quota to a suite."""
from __future__ import annotations

import copy
import subprocess
from pathlib import Path

from .comparison import suite_cases
from .experiment import Experiment
from .report import write_report


class SuiteCheck:
    def __init__(self, repo: Path, config: dict, out: Path):
        self.repo, self.config, self.out = repo.resolve(), config, out.resolve()

    def execute(self):
        if self.out.is_relative_to(self.repo) or (self.out.exists() and any(self.out.iterdir())):
            raise ValueError('Check output must be a new empty directory outside the repository')
        cases = suite_cases(self.config)
        protected = set()
        for _, config in cases:
            files = config.get('protected_files', [])
            if not isinstance(files, list) or any(not isinstance(v, str) for v in files):
                raise ValueError('protected_files must be a list of paths')
            oracle = config.get('oracle')
            if not isinstance(oracle, str):
                raise ValueError('Every case requires an oracle')
            protected.update(files)
            protected.add(oracle)
        experiments = []
        for name, config in cases:
            config['protected_files'] = sorted(protected)
            exp = Experiment(self.repo, config, self.out / 'cases' / name,
                             config.get('model'), config.get('repeats', 3),
                             config.get('max_runs', 60), config.get('timeout', 300),
                             max_tokens=config.get('max_tokens'))
            exp.prepare(materialize=False, check_codex=False, allow_empty=True)
            if experiments and exp.report['snapshot_sha256'] != experiments[0][1].report['snapshot_sha256']:
                raise ValueError('Source changed while preparing checks; retry on a stable repository')
            experiments.append((name, exp))
        # No commands or artifacts until every case is valid and frozen.
        self.report = copy.deepcopy(experiments[0][1].report)
        self.report.update(kind='checks', runner='verifier_only', status='running',
                           requested_model=None, message='Checking initial snapshots; no Codex calls.',
                           cases=[{'id': name, 'outcome': 'pending', 'result': None} for name, _ in experiments],
                           case_selection=copy.deepcopy(self.config.get('_case_selection',
                               {'available': [name for name, _ in cases], 'selected': [name for name, _ in cases], 'omitted': []})))
        write_report(self.out, self.report)
        try:
            for case, (_, exp) in zip(self.report['cases'], experiments):
                exp.materialize()
                result = exp.check_initial(prepared=True)
                code = result.get('exit_code')
                case.update(result=result, outcome='pass' if code == 0 else 'fail' if code == 1 else 'error')
                print(f"  {case['id']}: {case['outcome']} (exit {code})", flush=True)
                write_report(self.out, self.report)
            failed = any(case['outcome'] == 'error' for case in self.report['cases'])
            self.report.update(status='checks_failed' if failed else 'checks_completed',
                message='At least one setup/verifier command failed to execute; inspect case logs before Codex.' if failed else
                'Every verifier executed with exit 0 or 1. Behavior failures may be expected on initial code; inspect assertions. No Codex calls.')
        except KeyboardInterrupt:
            self.report.update(status='interrupted', message='Verifier checks interrupted; partial results saved. Rerun check --all in a new directory.')
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self.report.update(status='checks_failed', message=str(error))
        finally:
            write_report(self.out, self.report)
        return self.report
