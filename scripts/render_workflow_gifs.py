"""Create edited workflow illustrations from verified, model-free CLI fixtures.

Optional development dependency: Pillow. This script never invokes Codex.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT, SCALE = 1000, 620, 2
COLORS = {
    'bg': '#f8f9f6', 'panel': '#ffffff', 'terminal': '#ffffff',
    'border': '#dfe6dd', 'text': '#182b3a', 'muted': '#64746b',
    'dim': '#87948b', 'mint': '#087c68', 'blue': '#245b78',
    'red': '#b23e4b', 'amber': '#966112', 'white': '#ffffff',
    'soft': '#e7f4ed', 'soft-blue': '#edf3f6', 'soft-red': '#fff0f1',
    'soft-amber': '#fff6e5', 'surface-muted': '#f1f4ef', 'shadow': '#edf0e9',
}


def cli(arguments, *, cwd=ROOT, answers=None):
    result = subprocess.run([sys.executable, '-m', 'rulebisect', *arguments],
                            cwd=cwd, input=answers, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f'Fixture command failed: {arguments}\n{result.stdout}\n{result.stderr}')
    return result.stdout


def record_facts():
    """Verify every number before rendering; retain no paths, timestamps or logs."""
    with tempfile.TemporaryDirectory(prefix='rulebisect-media-') as directory:
        root = Path(directory).resolve()
        reports = {}
        for scenario in ('reduce', 'regression', 'fix'):
            out = root / scenario
            cli(['demo', '--scenario', scenario, '--out', str(out)])
            reports[scenario] = json.loads((out / 'report.json').read_text(encoding='utf-8'))
        reduction = reports['reduce']
        assert reduction['runner'] == 'simulation'
        assert len(reduction['rules']) == 5 and reduction['candidate'] == [1, 3]
        assert len(reduction['trials']) == 48 and reduction['repeats'] == 3
        assert reduction['status'] == 'observed_1_minimal'
        assert reports['regression']['status'] == 'regressions_observed'
        assert reports['fix']['status'] == 'no_regressions_observed'
        for scenario in ('regression', 'fix'):
            report = reports[scenario]
            assert report['runner'] == 'simulation' and report['repeats'] == 2
            assert len(report['trials']) == 8 and len(report['cases']) == 2
        regression_cases = reports['regression']['cases']
        fix_cases = reports['fix']['cases']
        assert [case['verdict'] for case in regression_cases] == ['improvement', 'regression']
        assert [case['verdict'] for case in fix_cases] == ['improvement', 'unchanged_pass']
        summary_path = root / 'summary.html'
        cli(['share', str(root / 'fix'), '--out', str(summary_path)])
        summary_html = summary_path.read_text(encoding='utf-8')
        assert 'rulebisect-public-summary-v1' in summary_html

        # Capture a real no-code initialization/check workflow, without an agent.
        repo = root / 'repo'
        shutil.copytree(ROOT / 'examples' / 'output-contract', repo)
        subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
        subprocess.run(['git', 'add', '.gitignore', 'AGENTS.md', 'checks.json', 'checks-legacy.json'], cwd=repo, check=True)
        wizard = cli(['init', '--wizard', '--repo', str(repo)],
                     answers='Create result.json with the modern format.\n:json\nresult.json\n/format\n"modern"\n\n\n')
        assert '1 built-in output assertions' in wizard and 'Assertions are frozen' in wizard
        doctor = json.loads(cli(['doctor', '--repo', str(repo), '--offline', '--json']))
        assert doctor['ok'] and doctor['model_calls'] == 0
        out = root / 'first-check'
        cli(['check', '--repo', str(repo), '--all', '--out', str(out)])
        initial = json.loads((out / 'report.json').read_text(encoding='utf-8'))
        assert initial['status'] == 'checks_completed'
        assert len(initial['cases']) == 1 and initial['cases'][0]['outcome'] == 'fail'
        assert not initial['trials'] and initial['runner'] == 'verifier_only'
        cli(['case', 'add', 'legacy', '--repo', str(repo), '--task', 'Export the legacy label.',
             '--assertions', str(repo / 'checks-legacy.json')])
        cases = json.loads(cli(['case', 'list', '--repo', str(repo), '--json']))
        assert [case['id'] for case in cases] == ['task', 'legacy']
        return {
            'format': 'rulebisect-media-facts-v1', 'version': reduction['version'],
            'presentation': 'Edited workflow illustrations; not screen recordings.',
            'actual_codex_calls': 0,
            'onboarding': {'initial_cases': 1, 'initial_outcome': 'fail', 'saved_cases': 2,
                           'runner': 'verifier_only'},
            'reduction': {'units': 5, 'candidate': [1, 3], 'repeats': 3,
                          'executions': 48, 'status': reduction['status']},
            'regression': {'executions': 8, 'repeats': 2,
                           'verdicts': [case['verdict'] for case in regression_cases]},
            'fix': {'executions': 8, 'repeats': 2,
                    'verdicts': [case['verdict'] for case in fix_cases]},
        }


def find_font(explicit, mono=False):
    if explicit:
        return str(Path(explicit).resolve())
    candidates = (
        ['/System/Library/Fonts/Menlo.ttc', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
         'C:/Windows/Fonts/consola.ttf'] if mono else
        ['/System/Library/Fonts/Supplemental/Arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
         'C:/Windows/Fonts/arial.ttf']
    )
    for path in candidates:
        if Path(path).is_file():
            return path
    raise RuntimeError('No suitable font found; provide --font-sans and --font-mono')


class Canvas:
    def __init__(self, sans, mono):
        self.image = Image.new('RGB', (WIDTH * SCALE, HEIGHT * SCALE), COLORS['bg'])
        self.draw = ImageDraw.Draw(self.image)
        self.sans, self.mono = sans, mono
        self.fonts = {}

    def font(self, size, mono=False):
        key = (size, mono)
        if key not in self.fonts:
            self.fonts[key] = ImageFont.truetype(self.mono if mono else self.sans, size * SCALE)
        return self.fonts[key]

    def text(self, x, y, value, size=18, color='text', mono=False, bold=False):
        font = self.font(size, mono)
        # Check against the actual rasterized font, including every command line.
        if self.draw.textlength(value, font=font) > (WIDTH - x - 24) * SCALE:
            raise ValueError(f'Text overflows canvas: {value}')
        self.draw.text((x * SCALE, y * SCALE), value, font=font, fill=COLORS[color],
                       stroke_width=1 if bold else 0, stroke_fill=COLORS[color])

    def box(self, bounds, color='panel', outline='border', radius=12, shadow=False):
        if shadow:
            x0, y0, x1, y1 = bounds
            self.draw.rounded_rectangle((x0 * SCALE, (y0 + 4) * SCALE,
                                         x1 * SCALE, (y1 + 4) * SCALE),
                                        radius=radius * SCALE, fill=COLORS['shadow'])
        self.draw.rounded_rectangle(tuple(int(value * SCALE) for value in bounds),
                                    radius=radius * SCALE, fill=COLORS[color],
                                    outline=COLORS[outline] if outline else None, width=SCALE)

    def line(self, bounds, color='border', width=1):
        self.draw.line(tuple(int(value * SCALE) for value in bounds), fill=COLORS[color], width=width * SCALE)

    def finished(self):
        return self.image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def header(canvas, name, title, caption, labels, stage, progress, simulation):
    # Product chrome stays restrained; the evidence identity is visible on every frame.
    canvas.box((0, 0, WIDTH, 58), 'panel', outline=None, radius=0)
    canvas.line((0, 58, WIDTH, 58))
    canvas.box((34, 15, 62, 43), 'soft', 'border', 8)
    canvas.line((41, 23, 48, 29, 41, 35), 'mint', 2)
    canvas.line((49, 35, 56, 35), 'mint', 2)
    canvas.text(73, 19, 'RuleBisect', 18, bold=True)
    canvas.text(181, 22, '/', 15, 'dim')
    canvas.text(199, 21, name, 15, 'muted')
    badge = 'DETERMINISTIC SIMULATION' if simulation else 'VERIFIER-ONLY WORKFLOW'
    canvas.box((706, 16, 966, 42), 'soft-amber' if simulation else 'soft-blue', outline=None, radius=6)
    canvas.text(718, 23, badge, 12, 'amber' if simulation else 'blue', bold=True)
    canvas.text(34, 79, title, 31, bold=True)
    canvas.text(34, 121, caption, 17, 'muted')
    for index, label in enumerate(labels):
        x = 34 + index * 239
        active = index == stage
        canvas.box((x, 159, x + 222, 194), 'soft' if active else 'bg',
                   'border' if active else None, 8)
        canvas.box((x + 10, 166, x + 31, 187), 'mint' if active else 'panel',
                   None if active else 'border', 6)
        canvas.text(x + 17, 171, str(index + 1), 11, 'white' if active else 'muted', bold=active)
        canvas.text(x + 41, 168, label, 15, 'mint' if active else 'muted', bold=active)
    canvas.box((34, 214, 620, 540), 'terminal', radius=14, shadow=True)
    canvas.text(54, 232, 'COMMANDS & SELECTED OUTPUT', 11, 'muted', bold=True)
    canvas.box((551, 226, 603, 246), 'surface-muted', outline=None, radius=5)
    canvas.text(562, 231, 'LOCAL', 10, 'muted')
    canvas.line((34, 256, 620, 256))
    canvas.box((642, 214, 966, 540), radius=14, shadow=True)
    canvas.text(34, 573, 'Edited walkthrough  /  constructed fixture', 13, 'muted')
    canvas.box((794, 565, 966, 592), 'soft', outline=None, radius=7)
    canvas.text(806, 573, '0 Codex/model calls', 13, 'mint', bold=True)
    canvas.box((34, 603, 966, 606), 'border', outline=None, radius=1)
    canvas.box((34, 603, 34 + max(1, 932 * progress), 606), 'mint', outline=None, radius=1)


def terminal(canvas, lines, reveal=1):
    count = min(len(lines), max(1, int(len(lines) * reveal + 0.6)))
    for index, item in enumerate(lines[:count]):
        text, color = item if isinstance(item, tuple) else (item, 'text')
        # Terminal content has a stricter boundary than the full canvas.
        if canvas.draw.textlength(text, font=canvas.font(19, True)) > 546 * SCALE:
            raise ValueError(f'Terminal line too long: {text}')
        y = 279 + index * 33
        if text.startswith('$'):
            canvas.box((48, y - 4, 606, y + 27), 'soft-blue', outline=None, radius=6)
        canvas.text(54, y, text, 19, color, mono=True)


def side_text(canvas, kicker, title, lines, color='mint'):
    canvas.text(662, 233, kicker.upper(), 11, 'muted', bold=True)
    canvas.text(662, 270, title, 23, color, bold=True)
    canvas.line((662, 309, 946, 309))
    for index, line in enumerate(lines):
        canvas.text(662, 329 + index * 29, line, 17, 'muted')


def rule_cards(canvas, retained=False):
    canvas.text(662, 233, 'SELECTED INSTRUCTION UNITS', 11, 'muted', bold=True)
    rows = ('UTF-8 output', 'Select legacy format', 'Concise diagnostics',
            'Enable compatibility', 'Descriptive names')
    for index, value in enumerate(rows):
        y = 271 + index * 40
        active = not retained or index in (1, 3)
        color = 'red' if retained and active else 'muted' if active else 'dim'
        canvas.box((660, y, 947, y + 33), 'soft-red' if retained and active else 'surface-muted',
                   'border' if active else None, 6)
        canvas.text(673, y + 9, str(index), 12, color, mono=True)
        canvas.text(699, y + 7, value, 15, color, bold=retained and active)
    canvas.line((662, 479, 946, 479))
    canvas.text(662, 494, '2 units retain the failure' if retained else '5 paragraph units',
                16, 'red' if retained else 'blue', bold=True)


def comparison_cards(canvas, fixed=False):
    canvas.text(662, 233, 'PASS COUNTS / TWO REPEATS', 11, 'muted', bold=True)
    for index, (name, before, after, verdict, color) in enumerate((
        ('Modern labels', '0/2', '2/2', 'improvement', 'mint'),
        ('Legacy labels', '2/2', '2/2' if fixed else '0/2',
         'unchanged pass' if fixed else 'regression', 'mint' if fixed else 'red'),
    )):
        y = 273 + index * 103
        canvas.box((660, y, 947, y + 90), 'soft-red' if color == 'red' else 'soft', 'border', 9)
        canvas.text(676, y + 10, name, 16, bold=True)
        canvas.text(676, y + 36, before, 24, 'mint' if before == '2/2' else 'red', mono=True)
        canvas.text(751, y + 43, 'to', 13, 'muted')
        canvas.text(799, y + 36, after, 24, color, mono=True)
        canvas.text(676, y + 69, f'Original -> proposed  /  {verdict}', 11, color)
    canvas.line((662, 479, 946, 479))
    canvas.text(662, 495, '8 simulation executions', 15, 'muted')


def scenes():
    onboarding = [
        {'title': 'Define the result. Skip writing a verifier.',
         'caption': 'Start in a Git repository with AGENTS.md. Choose an output contract.',
         'lines': [('$ rulebisect init --wizard', 'blue'), 'Task: Create modern result.json.',
                   'Check: :json', 'Output file: result.json', 'JSON pointer: /format',
                   'Expected JSON: "modern"'],
         'side': lambda c: side_text(c, 'guided JSON check', 'Observable success',
                                    ['result.json', '/format == "modern"', '', 'Check the file,', 'not a completion claim.'])},
        {'title': 'Save the contract once.',
         'caption': 'The generated verifier keeps the same criteria across fresh workspaces.',
         'lines': [('Created .rulebisect.json', 'mint'), 'Check: 1 built-in output assertion',
                   'Assertions are frozen.', 'Input JSON edits do not change criteria.',
                   ('No model calls or check execution.', 'muted')],
         'side': lambda c: side_text(c, 'independent verifier', 'Criteria stay fixed',
                                    ['Self-contained Python', 'Standard library only', 'Protected from trial edits', '', 'Works with run + compare'])},
        {'title': 'Check the environment before using quota.',
         'caption': 'Missing output is an expected behavior failure on the initial code.',
         'lines': [('$ rulebisect doctor --offline', 'blue'), ('OK  Experiment inputs', 'mint'),
                   ('$ rulebisect check --all', 'blue'), ('FAIL  required output is missing', 'amber'),
                   'checks_completed', ('Verifier executed; behavior failed.', 'muted')],
         'side': lambda c: side_text(c, 'initial snapshot', 'Check ran correctly',
                                    ['1 initial task', 'Output is missing', 'Behavior verdict: fail', '', '0 model calls'], 'amber')},
        {'title': 'Save another contract as a regression case.',
         'caption': 'Save another task, then use the same checks to validate proposed rules.',
         'lines': [('$ rulebisect case add legacy \\', 'blue'), '  --task "Export the legacy label" \\',
                   '  --assertions checks-legacy.json', ('Saved case legacy.', 'mint'),
                   ('$ rulebisect case list', 'blue'), 'task + legacy: 2 saved cases'],
         'side': lambda c: side_text(c, 'regression suite', 'Ready for comparison',
                                    ['Original task preserved', '2 independent verifiers', '', 'Next: draft + edit', 'Then: compare --plan'])},
    ]
    reduction = [
        {'title': 'Which rules still reproduce the failure?',
         'caption': 'Establish repeated full and empty controls before shrinking anything.',
         'lines': [('$ rulebisect demo --scenario reduce', 'blue'), ('DETERMINISTIC SIMULATION', 'amber'),
                   '5 paragraph units', ('Full instructions: FAIL 3/3', 'red'),
                   ('Empty instructions: PASS 3/3', 'mint')], 'side': lambda c: rule_cards(c)},
        {'title': 'Shrink the observed failing subset.',
         'caption': 'Retain a smaller instruction set that still reproduces this fixture\'s failure.',
         'lines': ['Stable search evaluations', 'Drop units not needed in this fixture',
                   ('Retained units: 1 + 3', 'red'), ('5 paragraphs -> 2 paragraphs', 'mint'),
                   'Failure still reproduces'], 'side': lambda c: rule_cards(c, True)},
        {'title': 'Confirm the result with fresh executions.',
         'caption': 'The candidate fails again; each single removal passes in this fixture.',
         'lines': [('Candidate {1, 3}: FAIL 3/3', 'red'), ('Remove unit 1:    PASS 3/3', 'mint'),
                   ('Remove unit 3:    PASS 3/3', 'mint'), '', ('status: observed_1_minimal', 'blue')],
         'side': lambda c: side_text(c, 'observed minimality', '5 units -> 2',
                                    ['3 fresh candidate failures', '3 passes per removal', '', 'Finite repeated observations', 'Global minimum not proven'])},
        {'title': 'Inspect the failing reproducer. Then propose a fix.',
         'caption': 'The retained candidate reproduces failure; use draft to prepare a change.',
         'lines': [('48 simulation executions', 'mint'), '0 Codex/model calls', 'candidate/ + report.html',
                   '', ('Next: draft -> edit -> compare', 'blue')],
         'side': lambda c: side_text(c, 'evidence bundle', 'Failure reproduced',
                                    ['Retained units 1 + 3', 'Original source preserved', 'Logs + reviewable diffs', '', 'Validate a fix on other tasks'])},
    ]
    regression = [
        {'title': 'A broad rule edit can change two contracts.',
         'caption': 'Compare the same tasks on fresh snapshots with original and proposed rules.',
         'lines': [('$ rulebisect demo --scenario regression \\', 'blue'), '  --out regression-evidence',
                   ('DETERMINISTIC SIMULATION', 'amber'), '2 cases x 2 variants x 2 repeats',
                   'Original: preserve whitespace', 'Proposal: strip for all labels'],
         'side': lambda c: side_text(c, 'proposed instruction', 'Scope matters',
                                    ['Modern: trimming required', 'Legacy: whitespace required', '', 'One shared rule', 'Two observable contracts'], 'blue')},
        {'title': 'One task improves. Another regresses.',
         'caption': 'A successful current task can hide a failure in an existing behavior.',
         'lines': [('Modern: 0/2 -> 2/2 passes', 'mint'), ('Legacy: 2/2 -> 0/2 passes', 'red'),
                   '', ('status: regressions_observed', 'red'), 'Review before applying the edit'],
         'side': lambda c: comparison_cards(c)},
        {'title': 'Scope the rule and check both tasks again.',
         'caption': 'The scoped proposal passes both constructed cases in the repeated checks.',
         'lines': [('$ rulebisect demo --scenario fix \\', 'blue'), '  --out fix-evidence',
                   'Strip modern labels only.', 'Preserve legacy label whitespace.',
                   ('status: no_regressions_observed', 'mint')],
         'side': lambda c: comparison_cards(c, True)},
        {'title': 'Share the outcome counts.',
         'caption': 'Full evidence stays local. The summary omits tasks, code, IDs and logs.',
         'lines': [('$ rulebisect share fix-evidence \\', 'blue'), '  --out summary.html',
                   ('Summary saved: summary.html', 'mint'), 'Standalone offline HTML',
                   'No upload or model calls.', 'Review aggregates before publishing.'],
         'side': lambda c: side_text(c, 'aggregate-only summary', 'Source: simulation',
                                    ['8 recorded trials', '1 improvement', '1 unchanged passing case', '', 'Finite evidence about 2 cases'])},
    ]
    return {
        'onboarding': ('No-code setup', ['Define', 'Freeze', 'Check', 'Save case'], onboarding, False),
        'reduction': ('Failure reduction', ['Controls', 'Shrink', 'Confirm', 'Inspect'], reduction, True),
        'regression': ('Fix + regression + share', ['Compare', 'Catch', 'Scope', 'Share'], regression, True),
    }


def render(name, specification, out, preview, sans, mono):
    title, labels, story, simulation = specification
    frames, durations, posters = [], [], []
    for stage, scene in enumerate(story):
        # Seven progressive reveals followed by a readable pause; no rapid flashing.
        for tick in range(8):
            fraction = min(1, (tick + 1) / 6)
            canvas = Canvas(sans, mono)
            overall = (stage + (tick + 1) / 8) / len(story)
            header(canvas, title, scene['title'], scene['caption'], labels, stage, overall, simulation)
            terminal(canvas, scene['lines'], fraction)
            scene['side'](canvas)
            frame = canvas.finished()
            frames.append(frame)
            durations.append(220 if tick < 7 else 3500)
        posters.append(frames[-1])
    # One shared palette avoids palette flicker between scenes and antialiased text.
    sample = Image.new('RGB', (250 * len(posters), 155))
    for index, poster in enumerate(posters):
        sample.paste(poster.resize((250, 155)), (index * 250, 0))
    palette = sample.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    encoded = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    path = out / f'{name}.gif'
    encoded[0].save(path, save_all=True, append_images=encoded[1:], duration=durations,
                    loop=0, disposal=1, optimize=True)
    # Verify optimized delta frames reconstruct exactly, including scene changes.
    with Image.open(path) as saved:
        assert saved.n_frames == len(encoded)
        for index, expected in enumerate(encoded):
            saved.seek(index)
            assert ImageChops.difference(saved.convert('RGB'), expected.convert('RGB')).getbbox() is None
    # Each poster emphasizes the workflow's main outcome for static viewing.
    posters[1 if name == 'regression' else 2].save(out / f'{name}.png')
    if preview:
        preview.mkdir(parents=True, exist_ok=True)
        contact = Image.new('RGB', (WIDTH, HEIGHT), COLORS['bg'])
        for index, poster in enumerate(posters):
            contact.paste(poster.resize((WIDTH // 2, HEIGHT // 2)),
                          ((index % 2) * WIDTH // 2, (index // 2) * HEIGHT // 2))
        contact.save(preview / f'{name}-contact.png')
        for index, poster in enumerate(posters):
            poster.save(preview / f'{name}-{index + 1}.png')
    print(f'{path.name}: {path.stat().st_size / 1024:.0f} KiB, {sum(durations) / 1000:.2f}s')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'docs' / 'media')
    parser.add_argument('--preview', type=Path)
    parser.add_argument('--font-sans', type=Path)
    parser.add_argument('--font-mono', type=Path)
    args = parser.parse_args()
    sans, mono = find_font(args.font_sans), find_font(args.font_mono, mono=True)
    facts = record_facts()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'facts.json').write_text(json.dumps(facts, indent=2) + '\n', encoding='utf-8')
    for name, specification in scenes().items():
        render(name, specification, args.out, args.preview, sans, mono)
    print('Verified model-free fixtures; no Codex calls. Fonts are rasterized, not redistributed.')


if __name__ == '__main__':
    main()
