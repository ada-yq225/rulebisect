"""Export aggregate-only evidence without copying any report text or identifiers."""
from __future__ import annotations

import html
import json
import os
import re
import tempfile
from pathlib import Path

from .ui import styles, svg_icon

# Only finite counts and fixed enums cross this boundary. Never reuse report.message,
# report paths, case IDs, tasks, or generated HTML from the full evidence report.
MAX_COUNT = 2**53 - 1
MAX_REPORT_BYTES = 10 * 1024 * 1024
KINDS = frozenset({'reduction', 'comparison', 'checks', 'check'})
SOURCES = frozenset({'codex', 'simulation', 'verifier_only'})
OUTCOMES = ('pass', 'fail', 'error', 'pending', 'unknown')
VERDICTS = ('regression', 'improvement', 'unchanged_pass', 'unchanged_fail', 'pending', 'unknown')
STATUS = {
    'pending': 'The experiment has not started.',
    'running': 'The experiment has not completed; no final conclusion is available.',
    'observed_1_minimal': 'The candidate repeatedly failed and each tested single removal passed. This is an observed failing reproducer, not a validated fix or global minimum.',
    'not_reproduced': 'The full instruction set did not fail consistently in the baseline repetitions.',
    'control_failed': 'Failure persisted after removing the selected instruction units.',
    'inconclusive': 'The available observations do not support a completed conclusion.',
    'interrupted': 'The experiment was interrupted; these observations are incomplete.',
    'regressions_observed': 'At least one previously passing case failed with the proposed instructions.',
    'candidate_failed': 'The proposed instructions still failed at least one case.',
    'no_regressions_observed': 'Every proposed case passed the selected repetitions. Other cases and environments are not covered.',
    'checks_completed': 'The selected verifiers executed. Behavioral failures may be expected on initial code; no model calls were made.',
    'checks_failed': 'At least one selected setup or verifier failed to execute.',
    'check_only': 'A verifier was run on the initial snapshot. No model calls were made.',
    'unknown': 'The saved report has an unrecognized status; no conclusion is inferred.',
}


def _count(value, fallback=0):
    return value if type(value) is int and 0 <= value <= MAX_COUNT else fallback


def _enum(value, allowed):
    return value if isinstance(value, str) and value in allowed else 'unknown'


def _list(report, key):
    value = report.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f'Report {key} must be an array')
    return value


def _totals(values, key):
    result = {name: 0 for name in OUTCOMES}
    for value in values:
        outcome = _enum(value.get(key), OUTCOMES) if isinstance(value, dict) else 'unknown'
        result[outcome] += 1
    return result


def _usage(trials):
    result = {name: 0 for name in ('input_tokens', 'output_tokens', 'cached_input_tokens')}
    result.update(reported_runs=0, missing_runs=0, partial_usage_runs=0, invalid_usage_runs=0)
    for trial in trials:
        codex = trial.get('codex') if isinstance(trial, dict) else None
        values = codex.get('reported_usage', []) if isinstance(codex, dict) else []
        valid, invalid = False, not isinstance(values, list)
        present = set()
        for value in values if isinstance(values, list) else []:
            if not isinstance(value, dict):
                invalid = True
                continue
            for name in ('input_tokens', 'output_tokens', 'cached_input_tokens'):
                if name not in value:
                    continue
                count = _count(value[name], None)
                if count is None or result[name] + count > MAX_COUNT:
                    invalid = True
                else:
                    result[name] += count
                    present.add(name)
                    valid = True
        result['reported_runs' if valid else 'missing_runs'] += 1
        result['partial_usage_runs'] += int(valid and not {'input_tokens', 'output_tokens'} <= present)
        result['invalid_usage_runs'] += int(invalid)
    return result


def _summary(report):
    if not isinstance(report, dict):
        raise ValueError('Report JSON must contain an object')
    trials = _list(report, 'trials')
    cases = _list(report, 'cases')
    kind = _enum(report.get('kind', 'reduction'), KINDS)
    version = report.get('version')
    version = version if isinstance(version, str) and re.fullmatch(r'[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}', version) else 'unknown'
    selection = report.get('case_selection')
    omitted = selection.get('omitted', []) if isinstance(selection, dict) else []
    result = {
        'format': 'rulebisect-public-summary-v1',
        'version': version,
        'kind': kind,
        'status': _enum(report.get('status'), STATUS),
        'source': _enum(report.get('runner'), SOURCES),
        'executions': len(trials),
        'max_runs': _count(report.get('max_runs'), None),
        'repeats': _count(report.get('repeats'), None),
        'observations': _totals(trials, 'outcome'),
        'usage': _usage(trials),
        'omitted_cases': len(omitted) if isinstance(omitted, list) else 0,
    }
    if kind == 'reduction':
        result['instruction_units'] = len(_list(report, 'rules'))
        result['candidate_units'] = len(_list(report, 'candidate'))
    elif kind == 'comparison':
        verdicts = {name: 0 for name in VERDICTS}
        arms = {name: {key: 0 for key in ('pass', 'fail', 'error')} for name in ('baseline', 'candidate')}
        for case in cases:
            verdict = _enum(case.get('verdict'), VERDICTS) if isinstance(case, dict) else 'unknown'
            verdicts[verdict] += 1
            for arm, totals in arms.items():
                value = case.get(arm) if isinstance(case, dict) else None
                for key in totals:
                    count = _count(value.get(key)) if isinstance(value, dict) else 0
                    totals[key] = min(MAX_COUNT, totals[key] + count)
        result['cases'] = len(cases)
        result['verdicts'] = verdicts
        result['variants'] = arms
    elif kind == 'checks':
        result['cases'] = len(cases)
        result['checks'] = _totals(cases, 'outcome')
    elif kind == 'check':
        check = report.get('verifier_check')
        code = check.get('exit_code') if isinstance(check, dict) else None
        outcome = 'pass' if type(code) is int and code == 0 else 'fail' if type(code) is int and code == 1 else 'error'
        result['checks'] = {key: int(key == outcome) for key in OUTCOMES}
    return result


def _render(summary):
    esc = html.escape
    def display(value):
        return 'unknown / 未知' if value is None else f'{value:,}' if type(value) is int else esc(value)
    def table(title, values):
        rows = ''.join(f'<tr><th scope="row">{esc(key.replace("_", " "))}</th><td>{display(value)}</td></tr>' for key, value in values.items())
        return (f'<section class="section"><div class="section-heading"><h2>{title}</h2></div><div class="panel table-wrap">'
                f'<table class="comparison-matrix summary-table"><caption class="sr-only">{title}</caption>'
                '<thead><tr><th scope="col">Measure / 指标</th><th scope="col">Count / 数量</th></tr></thead>' + rows + '</table></div></section>')
    def metric(label, value, detail):
        return f'<div class="mini-stat"><div class="metric-label">{label}</div><div class="metric-value">{display(value)}</div><div class="metric-detail">{detail}</div></div>'
    usage = summary['usage']
    sections = table('Observation counts / 观测次数', summary['observations'])
    if 'verdicts' in summary:
        sections += table('Case verdicts / 用例结论', summary['verdicts'])
        sections += table('Original observations / 原始规则', summary['variants']['baseline'])
        sections += table('Proposed observations / 拟议规则', summary['variants']['candidate'])
    if 'checks' in summary:
        sections += table('Verifier checks / 验证器检查', summary['checks'])
    if 'instruction_units' in summary:
        sections += table('Instruction counts / 指令数量', {'instruction units': summary['instruction_units'], 'failing candidate units': summary['candidate_units']})
    sections += table('Reported token usage / 已报告 Token', usage)
    encoded = json.dumps(summary, sort_keys=True, indent=2).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    status = summary['status']
    tone = 'danger' if status in ('regressions_observed', 'candidate_failed', 'checks_failed', 'control_failed') else 'success' if status == 'no_regressions_observed' else 'warning' if status in ('observed_1_minimal', 'inconclusive', 'interrupted', 'not_reproduced') else 'neutral'
    sources = {'simulation': 'Simulation · 0 model calls / 模拟 · 0 次模型调用', 'verifier_only': 'Verifier only · 0 model calls / 仅验证器 · 0 次模型调用', 'codex': 'Codex', 'unknown': 'Unknown source / 来源未知'}
    stats = metric('Recorded trials / 试验次数', summary['executions'], 'Saved observations / 已保存观测')
    stats += metric('Omitted cases / 未检查用例', summary['omitted_cases'], 'Outside the tested scope / 不在测试范围')
    stats += metric('Version / 版本', summary['version'], 'Report tool version / 报告工具版本')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><title>RuleBisect · Public summary</title>
<style>{styles()}
.share-sections{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 22px}}.summary-table td{{text-align:right;font-variant-numeric:tabular-nums}}.summary-table th[scope=row]{{background:transparent;font-size:12px;font-weight:500;white-space:normal}}.summary-table th,.summary-table td{{padding:11px 16px}}@media(max-width:620px){{.share-sections{{display:block}}.summary-table,.summary-table tbody{{display:table;width:100%}}.summary-table thead{{display:table-header-group}}.summary-table tr{{display:table-row}}.summary-table th,.summary-table td{{display:table-cell;border-top:1px solid var(--border)}}}}
</style></head><body><main class="share-shell" id="main-content">
<header class="summary-header"><div class="brand"><span class="brand-mark">{svg_icon('mark')}</span>RuleBisect</div><span class="source-pill">{svg_icon('flask')}{sources[summary['source']]}</span></header>
<div class="page-heading"><div><p class="eyebrow">AGGREGATE-ONLY EVIDENCE / 仅含汇总数据</p><h1>Public summary / 公开摘要</h1><p class="subtitle">A compact view of the recorded outcome / 已记录结果的简洁视图</p></div></div>
<div class="hero" data-tone="{tone}"><div class="hero-icon">{svg_icon('warning' if tone in ('danger', 'warning') else 'checks')}</div><div class="hero-copy"><h2>{esc(status.replace('_', ' '))}</h2><p>{STATUS[status]}</p><p class="section-note">Summary of a saved report; not independently authenticated evidence. / 来自已保存报告，未经独立认证。</p></div></div>
<div class="summary-grid">{stats}</div>
<div class="privacy-banner">{svg_icon('shield')}<p><strong>Counts stay. Private context stays out. / 保留计数，排除私有上下文。</strong><br>Tasks, instructions, filenames, case identifiers, models, commands, logs, timestamps and repository paths are omitted. Full evidence stays in the original report. / 不包含任务、指令、文件名、用例 ID、模型、命令、日志、时间戳和仓库路径；完整证据保留在原报告。</p></div>
<p class="section-note">Kind: {esc(summary['kind'])} · Repeats: {display(summary['repeats'])} · Execution budget: {display(summary['max_runs'])}</p>
<div class="share-sections">{sections}</div>
<div class="notice">{svg_icon('activity')}<p>Missing or partial usage is unknown, not zero cost. Cached input is included in input tokens; no currency cost is inferred. / 缺失或部分用量表示未知，不代表免费；缓存输入包含在输入 Token 中，不能推算货币费用。</p></div>
<footer class="footer"><span>RuleBisect · Offline summary / 离线摘要</span><span>Finite observations do not prove causation, statistical confidence, or a globally smallest subset. Review aggregates before publishing. / 有限观测不证明因果、统计置信度或全局最小；发布前请检查汇总数据。</span></footer>
<script type="application/json" id="rulebisect-summary">{encoded}</script></main></body></html>\n'''


def export_summary(report_path: Path, out: Path) -> Path:
    """Write one self-contained aggregate HTML file, atomically without overwriting.

    Accept an evidence directory or its report.json. The destination parent must
    exist, and the destination must be outside the evidence directory. Paths are
    resolved to check aliases; a symlink report or destination is never followed.
    """
    source = Path(report_path)
    if source.is_dir():
        source = source / 'report.json'
    if source.is_symlink():
        raise ValueError('The source report must be a regular JSON file, not a symlink')
    try:
        source = source.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError('Saved report not found; pass report.json or its evidence directory') from error
    if not source.is_file():
        raise ValueError('The source report must be a regular JSON file')
    if source.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError('Saved report exceeds the 10 MiB summary input limit')
    try:
        report = json.loads(source.read_text(encoding='utf-8'))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('Saved report must contain valid UTF-8 JSON') from error
    summary = _summary(report)
    output = Path(out)
    if output.suffix.lower() != '.html':
        raise ValueError('Summary output must be a new .html file')
    if output.is_symlink() or output.exists():
        raise ValueError('Summary output already exists; choose a new .html file')
    try:
        parent = output.parent.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError('Summary output parent must be an existing directory') from error
    if not parent.is_dir():
        raise ValueError('Summary output parent must be an existing directory')
    target = parent / output.name
    if target.is_relative_to(source.parent):
        raise ValueError('Summary output must be outside the saved evidence directory')
    # Hard-linking a fully written temporary file publishes atomically and fails
    # exclusively if another process creates the output first. No replace() race.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=parent, prefix='.rulebisect-summary-', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(_render(summary))
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, target)
    except FileExistsError as error:
        raise ValueError('Summary output already exists; choose a new .html file') from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target
