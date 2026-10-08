"""Offline evidence views; experiment data never becomes executable markup."""
from __future__ import annotations

import html
import json
from pathlib import Path

from .ui import script, styles, svg_icon


def esc(value):
    return html.escape(str(value), quote=True)


def bilingual(en, zh):
    return f'<span data-lang="en">{esc(en)}</span><span data-lang="zh">{esc(zh)}</span>'


def artifact_path(out, relative):
    """Only existing local regular files, with no URL syntax or symlink hops."""
    if not isinstance(relative, str) or not relative:
        return None
    if any(c in relative for c in '\\:%?#') or any(ord(c) < 32 or ord(c) == 127 for c in relative):
        return None
    parts = relative.split('/')
    if any(part in ('', '.', '..') for part in parts) or Path(relative).is_absolute():
        return None
    try:
        root = out.resolve(strict=True)
        path = root
        for part in parts:
            path = path / part
            if path.is_symlink():
                return None
        if path.is_file() and path.resolve(strict=True).is_relative_to(root):
            return path
    except (OSError, RuntimeError):
        pass
    return None


def artifact_link(out, relative, title, css='', download=False):
    if artifact_path(out, relative) is None:
        return ''
    return f'<a class="{esc(css)}" href="{esc(relative)}"' + (' download' if download else '') + f'>{title}</a>'


def trials_for_view(report):
    result, seen = [], set()
    for trial in report.get('trials', []):
        number = trial.get('number')
        if type(number) is int and number > 0 and number not in seen:
            result.append(trial)
            seen.add(number)
    return result


def badge(value, kind='outcome'):
    tones = {'pass': 'success', 'improvement': 'success', 'unchanged_pass': 'success',
             'fail': 'danger', 'error': 'danger', 'regression': 'danger', 'unchanged_fail': 'warning'}
    labels = {'pass': ('Pass', '通过'), 'fail': ('Fail', '行为失败'), 'error': ('Error', '运行错误'),
              'pending': ('Incomplete', '未完成'), 'improvement': ('Improvement', '改善'),
              'regression': ('Regression', '回退'), 'unchanged_pass': ('Still passes', '仍通过'),
              'unchanged_fail': ('Still fails', '仍失败')}
    en, zh = labels.get(value, (value, value))
    # Preserve a bilingual accessible verdict for shared screenshots and saved reports.
    title = f'{zh} / {en}'
    return f'<span class="{kind}-badge" data-tone="{tones.get(value, "neutral")}" title="{esc(title)}">{bilingual(en, zh)}</span>'


def section_heading(title, subtitle, icon, extra=''):
    return f'<div class="section-heading"><div><h2>{svg_icon(icon)}{title}</h2><p class="section-note">{subtitle}</p></div>{extra}</div>'


def counts(value):
    if not value:
        return bilingual('Not run', '未运行')
    text = f'{value.get("pass", 0)} pass / {value.get("fail", 0)} fail / {value.get("error", 0)} error'
    return (f'<span class="count-cell"><span class="pass">{esc(value.get("pass", 0))}</span> / '
            f'<span class="fail">{esc(value.get("fail", 0))}</span> / {esc(value.get("error", 0))}</span>'
            f'<small>{bilingual("pass / fail / error", "通过 / 失败 / 错误")}</small><span class="sr-only">{text}</span>')


def comparison_html(out, report, trials):
    rows = []
    for case in report.get('cases', []):
        related = [t for t in trials if t.get('case') == case['id']]
        evidence = (f'<a href="#run-{related[0]["number"]}" class="case-evidence">{esc(case["id"])}</a>'
                    if related else esc(case['id']))
        verdict = case.get('verdict', 'pending')
        # The explicit bilingual label also works when the reader disables JavaScript.
        names = {'regression': '回退 / Regression', 'improvement': '改善 / Improvement',
                 'unchanged_pass': '仍通过 / Still passes', 'unchanged_fail': '仍失败 / Still fails', 'pending': '未完成 / Incomplete'}
        rows.append(f'<tr><td><span class="mobile-label">{bilingual("Task", "任务")}</span>{evidence}</td>'
                    f'<td><span class="mobile-label">{bilingual("Original", "原始")}</span><div>{counts(case.get("baseline"))}</div></td>'
                    f'<td><span class="mobile-label">{bilingual("Proposed", "拟议")}</span><div>{counts(case.get("candidate"))}</div></td>'
                    f'<td><span class="mobile-label">{bilingual("Verdict", "结果")}</span><div>{badge(verdict, "verdict")}<span class="sr-only">{esc(names.get(verdict, verdict))}</span></div></td></tr>')
    patch = artifact_link(out, 'proposed.patch', svg_icon('compare') + bilingual('Instruction diff', '指令差异'), 'btn btn-secondary')
    heading = section_heading(bilingual('Before & after', '修改前后'), bilingual('Each task starts from the same code. Select a task to inspect its runs.', '每个任务从相同代码开始。点击任务查看运行证据。'), 'compare', patch)
    table = ('<div class="panel table-wrap"><table class="comparison-matrix"><caption class="sr-only">Before and after case outcomes / 用例对照</caption><thead><tr>' +
             ''.join(f'<th scope="col">{bilingual(en, zh)}</th>' for en, zh in [('Task', '任务'), ('Original', '原始'), ('Proposed', '拟议'), ('Verdict', '结果')]) +
             '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')
    return '<section class="section" id="case-results">' + heading + table + '</section>'


def checks_html(out, report):
    rows = []
    cases = report.get('cases', [])
    if report.get('kind') == 'check':
        result = report.get('verifier_check') or {}
        code = result.get('exit_code')
        cases = [{'id': 'Initial snapshot / 初始快照', 'result': result,
                  'outcome': 'pass' if code == 0 else 'fail' if code == 1 else 'error'}]
    for case in cases:
        relative = 'check.log' if report.get('kind') == 'check' else f'cases/{case["id"]}/report.html'
        link = artifact_link(out, relative, bilingual('Open evidence', '查看证据')) if case.get('result') else ''
        rows.append(f'<tr><td><span class="mobile-label">{bilingual("Task", "任务")}</span>{esc(case["id"])}</td>'
                    f'<td><span class="mobile-label">{bilingual("Outcome", "结果")}</span>{badge(case.get("outcome", "pending"))}</td>'
                    f'<td><span class="mobile-label">{bilingual("Exit", "退出码")}</span>{esc((case.get("result") or {}).get("exit_code", "—"))}</td>'
                    f'<td><span class="mobile-label">{bilingual("Evidence", "证据")}</span>{link or bilingual("Not available", "尚无证据")}</td></tr>')
    heading = section_heading(bilingual('Verifier readiness', '验证器检查'), bilingual('Exit 0: passes. Exit 1: behavior fails, which may be expected on initial code. Other results: execution error.', '0：行为通过；1：行为失败，可能符合初始代码的预期；其他结果：运行错误。'), 'checks')
    table = ('<div class="panel table-wrap"><table class="comparison-matrix"><caption class="sr-only">Verifier readiness / 验证器运行结果</caption><thead><tr>' +
             ''.join(f'<th scope="col">{bilingual(en, zh)}</th>' for en, zh in [('Task', '任务'), ('Outcome', '结果'), ('Exit', '退出码'), ('Evidence', '证据')]) +
             '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')
    return '<section class="section" id="case-results">' + heading + table + '</section>'


def instructions_html(out, report):
    kept = set(report.get('candidate', []))
    cards = []
    for rule in report.get('rules', []):
        retained = rule['id'] in kept
        tag = bilingual('Retained in failing candidate', '失败候选中保留') if retained else bilingual('Outside candidate', '候选外指令')
        if not kept:
            tag = bilingual('No confirmed candidate', '尚无确认候选')
        cards.append(f'<article class="rule-card {"kept" if retained else "removed"}" data-kept="{str(retained).lower()}">'
                     f'<div class="rule-label"><code>{esc(rule["path"])}:{esc(rule["line"])}</code><span>#{esc(rule["id"])}</span></div>'
                     f'<p class="section-note">{tag}</p><pre>{esc(rule["text"])}</pre></article>')
    patch = artifact_link(out, 'candidate.patch', svg_icon('download') + bilingual('Candidate diff', '候选差异'), 'btn btn-secondary')
    heading = section_heading(bilingual('Instruction map', '指令地图'), bilingual('A retained failing reproducer helps you investigate; it is not a validated fix.', '保留的失败复现候选用于调查，不代表已验证的修复。'), 'rules', patch)
    controls = ('<div class="toolbar js-control" hidden><div class="segmented"><button id="all" aria-pressed="true">' + bilingual('All units', '全部指令') +
                '</button><button id="kept" aria-pressed="false">' + bilingual('Retained', '只看保留') +
                '</button></div><input class="search-field" id="search" type="search" placeholder="Search instructions / 搜索指令" aria-label="Search instructions / 搜索指令"></div>')
    content = '<div class="rule-grid">' + ''.join(cards) + '</div>' if cards else '<div class="empty-state">' + bilingual('No instruction units recorded.', '没有已记录的指令。') + '</div>'
    return '<section class="section" id="instructions">' + heading + controls + '<p id="visible-rules" class="section-note" aria-live="polite">' + esc(len(cards)) + ' units / 条指令</p>' + content + '<p class="empty-state" id="no-rules" hidden>' + bilingual('No matching instructions. Clear the search or show all units.', '没有匹配的指令。清空搜索或显示全部指令。') + '</p></section>'


def ledger_html(report):
    rows = ''.join('<tr><td>' + esc(ev['phase']) + '</td><td><code>' + esc(str(ev['ids'])) + '</code></td>' +
                   ''.join(f'<td>{esc(ev[key])}</td>' for key in ('pass', 'fail', 'error')) + '<td>' + badge(ev['outcome']) + '</td></tr>' for ev in report.get('evaluations', []))
    heading = section_heading(bilingual('Evaluation ledger', '实验对照'), bilingual('Repeated controls and candidate checks, in execution order.', '按执行顺序列出重复对照与候选验证。'), 'flask')
    if rows:
        content = ('<div class="panel table-wrap"><table class="comparison-matrix ledger-table"><caption class="sr-only">Repeated evaluations / 重复验证</caption><thead><tr>' +
                   ''.join(f'<th scope="col">{bilingual(en, zh)}</th>' for en, zh in [('Phase', '阶段'), ('Units', '指令'), ('Pass', '通过'), ('Fail', '失败'), ('Error', '错误'), ('Outcome', '结果')]) +
                   '</tr></thead><tbody>' + rows + '</tbody></table></div>')
    else:
        content = '<div class="panel empty-state">' + bilingual('No evaluations recorded yet.', '尚无实验对照记录。') + '</div>'
    return '<section class="section" id="ledger">' + heading + content + '</section>'


def diff_html(path):
    if path is None:
        return ''
    try:
        with path.open('rb') as handle:
            raw = handle.read(256 * 1024 + 1)
    except OSError:
        return ''
    truncated = len(raw) > 256 * 1024
    lines = []
    for line in raw[:256 * 1024].decode('utf-8', errors='replace').splitlines(keepends=True):
        css = 'diff-meta' if line.startswith(('+++', '---', '@@', 'diff ', 'index ')) else 'diff-add' if line.startswith('+') else 'diff-del' if line.startswith('-') else ''
        lines.append(f'<span class="{css}">{esc(line)}</span>')
    note = '<p class="section-note">' + bilingual('Preview truncated at 256 KiB. Download the code diff for the complete file.', '预览截取前 256 KiB。下载代码差异查看完整文件。') + '</p>' if truncated else ''
    return '<details class="disclosure"><summary>' + bilingual('Code diff', '代码差异') + '</summary><pre class="code-block">' + ''.join(lines) + '</pre>' + note + '</details>'


def runs_html(out, report, trials):
    def options(key):
        values = sorted({str(t.get(key, '')) for t in trials if t.get(key)})
        return ''.join(f'<option value="{esc(value)}">{esc(value)}</option>' for value in values)
    controls = '<div class="toolbar filter-row js-control" hidden><input id="run-search" class="search-field" type="search" placeholder="Search evidence / 搜索证据" aria-label="Search evidence / 搜索证据">'
    for key, en, zh in [('outcome', 'All outcomes', '全部结果'), ('phase', 'All phases', '全部阶段'), ('case', 'All tasks', '全部任务')]:
        controls += f'<label class="sr-only" for="{key}-filter">{en} / {zh}</label><select id="{key}-filter"><option value="">{en} / {zh}</option>{options(key)}</select>'
    controls += '<button class="btn btn-secondary" id="reset-filters">' + bilingual('Reset', '重置') + '</button></div>'
    cards = []
    for trial in trials:
        prefix = trial.get('artifacts', f'trials/{trial["number"]:04d}')
        links = []
        for name, en, zh in [('trial.json', 'Trial JSON', '运行 JSON'), ('agent.log', 'Agent log', 'Agent 日志'), ('setup.log', 'Setup log', '环境日志'), ('verify.log', 'Verifier log', '验证日志'), ('changes.diff', 'Code diff', '代码差异')]:
            link = artifact_link(out, f'{prefix}/{name}', svg_icon('file') + bilingual(en, zh)) if isinstance(prefix, str) else ''
            if link:
                links.append(link)
        changed = trial.get('changed_files', [])
        files = '<ul class="changed-files">' + ''.join(f'<li><code>{esc(path)}</code></li>' for path in changed) + '</ul>' if changed else '<p class="section-note">' + bilingual('No agent file changes recorded.', '未记录到 Agent 文件变化。') + '</p>'
        reason = '<p>' + esc(trial['reason']) + '</p>' if trial.get('reason') else ''
        diff_path = artifact_path(out, f'{prefix}/changes.diff') if isinstance(prefix, str) else None
        phase, case, outcome = (str(trial.get(key, '')) for key in ('phase', 'case', 'outcome'))
        meta = (esc(case) + ' · ' if case else '') + esc(phase)
        details = bilingual(f'{len(changed)} changed files', f'{len(changed)} 个变化文件')
        if trial.get('arm'):
            details += ' · ' + esc(trial['arm'])
        body = '<div class="artifact-links">' + ''.join(links) + '</div>' if links else '<p>' + bilingual('Artifact files are unavailable in this copy.', '此副本中没有可用的证据文件。') + '</p>'
        cards.append(f'<details class="evidence-card" id="run-{trial["number"]}" data-outcome="{esc(outcome)}" data-phase="{esc(phase)}" data-case="{esc(case)}">'
                     f'<summary class="evidence-summary"><span class="run-number">{trial["number"]:02d}</span><span class="summary-meta">{meta}<small>{details}</small></span>{badge(outcome)}{svg_icon("chevron")}</summary>'
                     '<div class="evidence-body">' + reason + body + files + diff_html(diff_path) + '</div></details>')
    heading = section_heading(bilingual('Run evidence', '运行证据'), bilingual('Filter observations, then expand a run for logs and code changes.', '筛选观测结果，展开运行查看日志与代码变化。'), 'activity')
    return '<section class="section" id="runs">' + heading + controls + f'<p class="section-note" id="visible-runs" aria-live="polite">{len(cards)} / {len(cards)} runs / 次运行</p><div class="evidence-list">' + ''.join(cards) + '</div><p class="empty-state" id="no-runs" hidden>' + bilingual('No matching runs. Reset filters to see all evidence.', '没有匹配的运行。重置筛选以查看全部证据。') + '</p>' + ('' if cards else '<div class="panel empty-state">' + bilingual('No model run evidence. Verifier-only reports link their check logs above.', '尚无模型运行证据。仅验证器报告可从上方查看检查日志。') + '</div>') + '</section>'


NEXT_EN = {
    'checks_completed': 'Review each behavior outcome and your acceptance checks before running Codex. A verifier exit of 1 may be expected on initial code.',
    'checks_failed': 'Open the failing setup or verifier logs. Fix the execution environment before using model quota.',
    'no_regressions_observed': 'Review the proposed diff before applying it. Passing selected cases does not cover other tasks or environments.',
    'regressions_observed': 'Inspect the regressed task and its verifier logs. Revise the proposed instructions before applying them.',
    'candidate_failed': 'Inspect the tasks that still fail. The candidate is not a verified repair.',
    'pending': 'The experiment has not started yet.',
    'running': 'Wait for completion before drawing conclusions from the current candidate.',
    'observed_1_minimal': 'Inspect the retained failing candidate, test other tasks, then revise the instructions manually.',
    'not_reproduced': 'Check that the task and acceptance conditions reproduce a specific failure under the full instructions.',
    'control_failed': 'Check the code, task, verifier, and configuration outside the selected instructions.',
    'inconclusive': 'Inspect errors and variability. For a reduction stopped by its budget, increase the budget and use rulebisect resume.',
    'interrupted': 'Use rulebisect resume for this reduction with the same snapshot and settings.',
    'check_only': 'Only the verifier ran on the initial snapshot. Codex was not invoked.',
}


def report_tone(report):
    status = report['status']
    if status in ('regressions_observed', 'candidate_failed', 'checks_failed', 'control_failed'):
        return 'danger'
    if status == 'no_regressions_observed':
        return 'success'
    if status in ('observed_1_minimal', 'inconclusive', 'interrupted', 'not_reproduced'):
        return 'warning'
    return 'neutral'


def render_report(out, report, label, action):
    kind = report.get('kind', 'reduction')
    checks = kind in ('check', 'checks')
    source = 'verifier_only' if checks else report.get('runner', 'unknown')
    source_names = {'simulation': ('Simulation · 0 model calls', '模拟 · 0 次模型调用'), 'verifier_only': ('Verifier only · 0 model calls', '仅验证器 · 0 次模型调用'), 'codex': ('Codex', 'Codex')}
    source_en, source_zh = source_names.get(source, (source, source))
    title_en, title_zh = ('Instruction comparison', '指令修改对照') if kind == 'comparison' else ('Verifier checks', '验证器检查') if checks else ('Instruction investigation', '指令问题调查')
    zh_label, en_label = label.split(' / ', 1) if ' / ' in label else (label, label)
    action_en = NEXT_EN.get(report['status'], 'Review the recorded evidence.')
    if kind == 'comparison' and report['status'] in ('inconclusive', 'interrupted'):
        action_en = 'Inspect case logs, adjust the verifier or budget, and rerun compare in a new directory. Comparisons cannot be resumed.'
    if kind == 'checks' and report['status'] == 'interrupted':
        action_en = 'Rerun check --all in a new directory. Verifier checks cannot be resumed.'
    tone = report_tone(report)
    trials = trials_for_view(report)
    totals = report['usage_totals']
    kept, rules = report.get('candidate', []), report.get('rules', [])
    model = report.get('requested_model') or ('not invoked' if checks else 'simulation' if source == 'simulation' else 'CLI default')
    nav = [('overview', 'Overview', '结果概览', 'flask')]
    nav += [('case-results', 'Case results', '用例结果', 'compare' if not checks else 'checks')] if kind in ('comparison', 'checks', 'check') else [('instructions', 'Instructions', '指令地图', 'rules'), ('ledger', 'Evaluations', '实验对照', 'checks')]
    nav += [('runs', 'Run evidence', '运行证据', 'activity'), ('settings', 'Settings & exports', '设置与导出', 'file')]
    navigation = ''.join(f'<a class="nav-link" href="#{anchor}"' + (' aria-current="true"' if anchor == 'overview' else '') + f'>{svg_icon(icon)}{bilingual(en, zh)}</a>' for anchor, en, zh, icon in nav)
    downloads = ''.join(artifact_link(out, filename, svg_icon('download') + bilingual(en, zh), 'btn btn-secondary', True) for filename, en, zh in [('report.json', 'JSON', 'JSON'), ('report.md', 'Markdown', 'Markdown'), ('issue.md', 'Issue draft', 'Issue 草稿')])
    def metric(en, zh, value, detail, icon):
        return f'<div class="metric"><div class="metric-label">{svg_icon(icon)}{bilingual(en, zh)}</div><div class="metric-value">{value}</div><div class="metric-detail">{detail}</div></div>'
    cases = report.get('cases', [])
    if kind == 'check':
        code = (report.get('verifier_check') or {}).get('exit_code')
        cases = [{'outcome': 'pass' if code == 0 else 'fail' if code == 1 else 'error'}]
    if kind in ('comparison', 'checks', 'check'):
        completed = sum(c.get('verdict' if kind == 'comparison' else 'outcome') != 'pending' for c in cases)
        first = metric('Cases checked', '已检查用例', f'{completed} <span class="metric-denominator">/ {len(cases)}</span>', bilingual('Selected cases only', '仅所选用例'), 'checks')
    else:
        first = metric('Candidate units', '候选指令', f'{len(kept)} <span class="metric-denominator">/ {len(rules)}</span>', bilingual('Failing reproducer, not a fix', '失败复现候选，不代表修复'), 'rules')
    second = metric('Model calls' if checks else 'Recorded runs', '模型调用' if checks else '已记录运行', '0' if checks else f'{len(report["trials"])} <span class="metric-denominator">/ {report["max_runs"]}</span>', bilingual('No model invoked', '未调用模型') if checks else bilingual('Execution budget', '总执行预算'), 'activity')
    if kind == 'comparison':
        bad = sum(c.get('verdict') == 'regression' for c in cases)
        third = metric('Regressed cases', '回退用例', esc(bad), bilingual(f'{sum(c.get("verdict") == "improvement" for c in cases)} improved cases', f'{sum(c.get("verdict") == "improvement" for c in cases)} 个改善用例'), 'compare')
    else:
        bad = sum(c.get('outcome') == 'error' for c in cases) if checks else sum(t.get('outcome') == 'fail' for t in trials)
        third = metric('Execution errors' if checks else 'Failing observations', '运行错误' if checks else '失败观测', esc(bad), bilingual(f'{sum(c.get("outcome") == "fail" for c in cases)} behavior failures; may be expected', f'{sum(c.get("outcome") == "fail" for c in cases)} 个行为失败，可能符合预期') if checks else bilingual('Includes controls and search', '包括对照与搜索'), 'warning')
    fourth = metric('Reported tokens', '已上报 Token', f'{totals["input_tokens"] + totals["output_tokens"]:,}' if totals['reported_runs'] else '—', bilingual(f'{totals["reported_runs"]} runs reported usage', f'{totals["reported_runs"]} 次运行上报用量') if totals['reported_runs'] else bilingual('Not reported · cost unknown', '未上报 · 费用未知'), 'activity')
    omitted = report.get('case_selection', {}).get('omitted', [])
    notice = '<div class="notice notice-warning">' + svg_icon('warning') + '<p>' + bilingual('Partial suite. Omitted cases were not checked: ', '仅检查所选用例。以下用例未检查：') + esc(', '.join(omitted)) + '</p></div>' if omitted else ''
    hero = f'<div class="hero" data-tone="{tone}"><div class="hero-icon">{svg_icon("warning" if tone in ("danger", "warning") else "checks")}</div><div class="hero-copy"><h2>' + bilingual(en_label, zh_label) + '</h2><p>' + esc(report.get('message', '')) + '</p><div class="next-step"><strong>' + bilingual('Next step · ', '下一步 · ') + '</strong>' + bilingual(action_en, action) + '</div></div></div>'
    overview = '<section class="section" id="overview"><div class="page-heading"><div><p class="eyebrow">' + bilingual('LOCAL EVIDENCE WORKSPACE', '本地实验工作台') + '</p><h1>' + bilingual(title_en, title_zh) + '</h1><p class="subtitle">' + bilingual('Understand the outcome. Follow the evidence. Decide what to change.', '看懂结果，追溯证据，再决定如何修改。') + '</p></div><span class="status-badge" data-tone="' + tone + '">' + esc(report['status'].replace('_', ' ')) + '</span></div>' + hero + notice + '<div class="stats-grid">' + first + second + third + fourth + '</div></section>'
    middle = comparison_html(out, report, trials) if kind == 'comparison' else checks_html(out, report) if checks else instructions_html(out, report) + ledger_html(report)
    experiment = {key: report.get(key) for key in ('task', 'requested_model', 'codex_version', 'snapshot_sha256', 'repeats', 'max_runs', 'max_tokens', 'timeout_seconds', 'protected_files', 'unit_mode', 'setup', 'cases')}
    facts = [('Runner / 执行来源', source), ('Model / 模型', model), ('Version / 版本', report.get('version', 'unknown')), ('Repeats / 重复次数', report.get('repeats')), ('Task / 任务', report.get('task', ''))]
    settings = '<section class="section" id="settings">' + section_heading(bilingual('Settings & exports', '设置与导出'), bilingual('Original task, configuration and complete machine-readable evidence.', '原始任务、配置与完整的机器可读证据。'), 'file') + '<div class="panel"><details class="disclosure settings-disclosure"><summary>' + bilingual('Experiment configuration', '实验设置') + '</summary><dl class="fact-list">' + ''.join(f'<dt>{esc(key)}</dt><dd>{esc(value)}</dd>' for key, value in facts) + '</dl><details class="disclosure"><summary>' + bilingual('Complete configuration JSON', '完整设置 JSON') + '</summary><pre class="code-block">' + esc(json.dumps(experiment, ensure_ascii=False, indent=2)) + '</pre></details></details><details class="disclosure settings-disclosure"><summary>' + bilingual('Reported token breakdown', '已上报 Token 明细') + '</summary><pre class="code-block">' + esc(json.dumps(totals, indent=2)) + '</pre><p>' + bilingual('Input includes cached input. Missing usage is unknown, and token counts do not imply a currency cost.', '输入包含缓存输入。缺失用量表示未知，Token 数不能推算货币费用。') + '</p></details></div><div class="artifact-links">' + downloads
    for filename, en, zh in [('check.log', 'Check log', '检查日志'), ('setup.log', 'Setup log', '环境日志')]:
        settings += artifact_link(out, filename, svg_icon('file') + bilingual(en, zh))
    settings += '</div></section>'
    footer = '<footer class="footer"><span>RuleBisect · ' + esc(report.get('version', 'unknown')) + ' · ' + bilingual('Offline report', '离线报告') + '</span><span>' + bilingual('Finite observations. No causal, confidence or global-minimum claim.', '有限观测，不证明因果关系、统计置信度或全局最小。') + '</span></footer>'
    header_controls = ('<div class="topbar-actions"><span class="source-pill">' + svg_icon('flask' if source == 'simulation' else 'checks') + bilingual(source_en, source_zh) + '</span><div class="js-control" hidden><label class="sr-only" for="language-select">Language / 语言</label><select id="language-select" aria-label="Language / 语言"><option value="en">English</option><option value="zh">中文</option></select></div><button id="theme-toggle" class="icon-button js-control" hidden aria-label="Toggle theme / 切换主题" aria-pressed="false">' + svg_icon('moon') + svg_icon('sun') + '</button></div>')
    return ('<!doctype html><html lang="en" data-language="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>RuleBisect · Evidence workspace</title><style>' + styles() + '</style></head><body><a class="skip-link" href="#main-content">Skip to evidence / 跳转到内容</a><div class="app-shell"><aside class="sidebar"><a class="brand" href="#overview"><span class="brand-mark">' + svg_icon('mark') + '</span>RuleBisect</a><p class="nav-label">' + bilingual('EXPERIMENT', '实验') + '</p><nav aria-label="Report sections / 报告章节">' + navigation + '</nav><div class="sidebar-note"><strong>' + bilingual('Your evidence stays local', '证据保留在本地') + '</strong>' + bilingual('Open source. Offline HTML. No external assets.', '开源。离线 HTML。无外部资源。') + '</div></aside><div class="workspace"><header class="topbar"><div class="breadcrumb">RuleBisect ' + svg_icon('chevron') + '<strong>' + bilingual(title_en, title_zh) + '</strong></div>' + header_controls + '</header><main class="page-content" id="main-content" tabindex="-1">' + overview + middle + runs_html(out, report, trials) + settings + footer + '</main></div></div><script>' + script() + '</script></body></html>\n')
