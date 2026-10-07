"""User-facing onboarding works without Codex and does not overwrite evidence."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rulebisect.cli import main


class DemoTests(unittest.TestCase):
    def test_comparison_scenarios_without_codex(self):
        with tempfile.TemporaryDirectory() as directory:
            for scenario, status, verdicts in (
                ('regression', 'regressions_observed', ['improvement', 'regression']),
                ('fix', 'no_regressions_observed', ['improvement', 'unchanged_pass']),
            ):
                out = Path(directory) / scenario
                with contextlib.redirect_stdout(io.StringIO()), patch('rulebisect.cli.webbrowser.open') as browser:
                    self.assertEqual(main(['demo', '--scenario', scenario, '--out', str(out), '--open']), 0)
                browser.assert_called_once_with((out.resolve() / 'report.html').as_uri())
                report = json.loads((out / 'report.json').read_text(encoding='utf-8'))
                self.assertEqual(report['status'], status)
                self.assertEqual([c['verdict'] for c in report['cases']], verdicts)
                self.assertEqual(report['runner'], 'simulation')
                self.assertEqual(len(report['trials']), 8)
                self.assertTrue(all(t['agent']['status'] == 'completed' for t in report['trials']))
                original = (out / 'report.json').read_bytes()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(['demo', '--scenario', scenario, '--out', str(out)]), 2)
                self.assertEqual((out / 'report.json').read_bytes(), original)

    def test_unexpected_demo_result_is_not_success(self):
        with patch('rulebisect.cli.run_comparison_demo', return_value={'status': 'inconclusive'}), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['demo', '--scenario', 'regression']), 2)

    def test_default_outputs_are_unique(self):
        outputs = []
        def fake_demo(out):
            outputs.append(out)
            return {'status': 'observed_1_minimal', 'message': 'simulation'}
        with patch('rulebisect.cli.run_demo', side_effect=fake_demo), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['demo']), 0)
            self.assertEqual(main(['demo']), 0)
        self.assertNotEqual(outputs[0], outputs[1])


if __name__ == '__main__':
    unittest.main()
