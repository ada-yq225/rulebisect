from __future__ import annotations

import json
from pathlib import Path

from .report_ui import artifact_path, render_report

STATUS = {
    'checks_completed': ('验证器已运行 / Checks completed', '验证器均返回 0 或 1；初始代码的行为失败可能符合预期。检查断言后再运行 Codex。'),
    'checks_failed': ('验证环境有问题 / Checks failed', '检查各用例的 setup/check 日志，修复运行环境后再调用 Codex。'),
    'no_regressions_observed': ('未观察到回退 / No regressions observed', '候选修改在所选任务中反复通过。审查差异后再应用；其他任务仍可能失败。'),
    'regressions_observed': ('发现任务回退 / Regressions observed', '候选修改使原本通过的任务失败。检查回退行的验证日志，暂缓应用。'),
    'candidate_failed': ('候选仍失败 / Candidate failed', '候选修改未通过全部任务，查看仍失败的任务；不要把它当成已验证修复。'),
    'pending': ('准备中 / Preparing', '尚未启动实验。'),
    'running': ('运行中 / Running', '实验尚未完成，当前候选仅供查看。'),
    'observed_1_minimal': ('已定位候选 / Candidate confirmed', '检查保留的指令组合，在其他任务上再次验证，然后手动调整规则。'),
    'not_reproduced': ('未复现 / Not reproduced', '完整指令下没有稳定失败。检查任务是否具体、验证条件是否准确。'),
    'control_failed': ('对照也失败 / Control failed', '移除所选指令后仍失败。检查代码、任务、验证器或未纳入实验的其他配置。'),
    'inconclusive': ('暂无法判断 / Inconclusive', '查看异常日志；若预算不足，可增加总次数后使用 resume。波动结果需要重新设计实验。'),
    'interrupted': ('已中断 / Interrupted', '保留了已有证据。使用 resume 继续，同一仓库快照和实验设置必须匹配。'),
    'check_only': ('验证器检查 / Check only', '仅在初始仓库副本中运行了验证命令，没有调用 Codex。'),
}


def token_totals(report):
    result = {'input_tokens': 0, 'output_tokens': 0, 'cached_input_tokens': 0, 'reported_runs': 0}
    for trial in report['trials']:
        values = trial.get('codex', {}).get('reported_usage', [])
        if values:
            result['reported_runs'] += 1
        for usage in values:
            if isinstance(usage, dict):
                for key in ('input_tokens', 'output_tokens', 'cached_input_tokens'):
                    if isinstance(usage.get(key), int):
                        result[key] += usage[key]
    return result


def atomic_text(path, text):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def latest_evaluation(report, phase):
    return next((v for v in reversed(report.get('evaluations', [])) if v['phase'] == phase), None)


def case_summary(value):
    if not value:
        return '未运行 / Not run'
    usage = f" · {value['reported_tokens']:,} reported tokens" if value.get('usage_reported_runs') else ""
    return f"{value['pass']} pass / {value['fail']} fail / {value['error']} error · {value['outcome']}" + usage


def selection_text(report):
    selection = report.get('case_selection', {})
    omitted = selection.get('omitted', [])
    return ('仅检查所选用例 / Partial suite. Omitted: ' + ', '.join(omitted) +
            '. These tasks were not checked; passing results do not cover them.') if omitted else ''


def write_report(out: Path, report: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    report['usage_totals'] = token_totals(report)
    atomic_text(out / 'report.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    kept = set(report.get('candidate', []))
    rules = report.get('rules', [])
    label, action = STATUS.get(report['status'], (report['status'], 'Review the evidence.'))
    if report.get('kind') == 'comparison' and report['status'] in ('inconclusive', 'interrupted'):
        action = '查看用例日志，调整验证器或预算后，在新目录重新执行 compare。本版对照实验不能续跑。'
    if report.get('kind') == 'checks' and report['status'] == 'interrupted':
        action = '在新目录重新执行 check --all；验证器检查不能续跑。'
    model_label = report.get('requested_model') or ('not invoked' if report.get('kind') in ('check', 'checks') else 'simulation')
    md = ['# RuleBisect experimental report', '', f"Status: **{report['status']}**", '', report['message'], '',
          f"Runner: {report['runner']} | Executions: {len(report['trials'])}/{report['max_runs']}", '',
          f"Requested model: {model_label}", '', '## Next step', '', action, '',
          '## Task', '', report.get('task', ''), '',
          'These are finite observations, not proof of causation, statistical confidence or a globally smallest subset.', '',
          '## Retained instruction units', '']
    for rule in rules:
        if rule['id'] in kept:
            fence = '`' * max(3, max((len(word) for word in rule['text'].split() if set(word) == {'`'}), default=0) + 1)
            md += [f"### {rule['path']}:{rule['line']} (unit {rule['id']})", '', fence + 'text', rule['text'], fence, '']
    if report.get('kind') == 'comparison':
        md = md[:-2]
        md += ['## Before / after tasks', '', '| Task | Before | After | Verdict |', '|---|---|---|---|']
        for case in report['cases']:
            md.append(f"| {case['id']} | {case_summary(case.get('baseline'))} | {case_summary(case.get('candidate'))} | {case['verdict']} |")
    if report.get('kind') == 'checks':
        md = md[:-2]
        md += ['## Verifier checks', '', '| Task | Outcome | Exit | Evidence |', '|---|---|---|---|']
        for case in report['cases']:
            relative = f"cases/{case['id']}/report.html"
            evidence = f"[report]({relative})" if case.get('result') and artifact_path(out, relative) else 'Not available'
            md.append(f"| {case['id']} | {case['outcome']} | {(case.get('result') or {}).get('exit_code')} | {evidence} |")
    if selection_text(report):
        md += ['', selection_text(report), '']
    if report.get('kind') not in ('comparison', 'checks'):
        md += ['## Evaluations', '', '| Phase | Units | Pass | Fail | Error | Outcome |', '|---|---|---:|---:|---:|---|']
        for ev in report.get('evaluations', []):
            md.append(f"| {ev['phase']} | {ev['ids']} | {ev['pass']} | {ev['fail']} | {ev['error']} | {ev['outcome']} |")
    atomic_text(out / 'report.md', '\n'.join(md) + '\n')
    # Compact issue draft excludes private task text, instruction bodies and raw logs by default.
    issue = ['# RuleBisect finding', '', f"Tool: {report.get('version')}; Codex: {report.get('codex_version', 'simulation')}",
             f"Requested model: {report.get('requested_model')}", f"Status: {report['status']}",
             f"Runs: {len(report['trials'])}; retained units: {len(kept)}/{len(rules)}", '', report['message'], '',
             'Finite observations only. Not a causal or statistical-confidence claim.', '',
             'Add a redacted task, instructions and verifier before publishing. Review model/tool versions for privacy.']
    if report.get('kind') == 'comparison':
        issue[5] = f"Runs: {len(report['trials'])}; tasks: {len(report['cases'])}"
        issue += ['', '## Task outcomes', ''] + [f"- {case['id']}: {case['verdict']}" for case in report['cases']]
    if selection_text(report):
        issue += ['', selection_text(report)]
    atomic_text(out / 'issue.md', '\n'.join(issue) + '\n')
    atomic_text(out / 'report.html', render_report(out, report, label, action))
