from __future__ import annotations

import html
import json
from pathlib import Path

STATUS = {
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


def write_report(out: Path, report: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    report['usage_totals'] = token_totals(report)
    atomic_text(out / 'report.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    kept = set(report.get('candidate', []))
    rules = report.get('rules', [])
    label, action = STATUS.get(report['status'], (report['status'], 'Review the evidence.'))
    md = ['# RuleBisect experimental report', '', f"Status: **{report['status']}**", '', report['message'], '',
          f"Runner: {report['runner']} | Executions: {len(report['trials'])}/{report['max_runs']}", '',
          f"Requested model: {report.get('requested_model') or 'simulation'}", '', '## Next step', '', action, '',
          '## Task', '', report.get('task', ''), '',
          'These are finite observations, not proof of causation, statistical confidence or a globally smallest subset.', '',
          '## Retained instruction units', '']
    for rule in rules:
        if rule['id'] in kept:
            fence = '`' * max(3, max((len(word) for word in rule['text'].split() if set(word) == {'`'}), default=0) + 1)
            md += [f"### {rule['path']}:{rule['line']} (unit {rule['id']})", '', fence + 'text', rule['text'], fence, '']
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
    atomic_text(out / 'issue.md', '\n'.join(issue) + '\n')
    e = html.escape
    cards = ''.join(f'<article class="rule {"kept" if r["id"] in kept else "removed"}" data-kept="{str(r["id"] in kept).lower()}">'
                    f'<div class="label">{("候选保留 / Retained" if r["id"] in kept else "候选移除 / Outside candidate") if kept else "尚无候选 / No candidate"} · {e(r["path"])}:{r["line"]} · #{r["id"]}</div>'
                    f'<pre>{e(r["text"])}</pre></article>' for r in rules)
    rows = ''.join(f'<tr><td>{e(v["phase"])}</td><td>{e(str(v["ids"]))}</td><td>{v["pass"]}</td>'
                   f'<td>{v["fail"]}</td><td>{v["error"]}</td><td>{e(v["outcome"])}</td></tr>'
                   for v in report.get('evaluations', []))
    trials = []
    for trial in report['trials']:
        if 'number' not in trial:
            continue
        prefix = f"trials/{trial['number']:04d}"
        links = [f'<a href="{prefix}/agent.log">Agent log</a>', f'<a href="{prefix}/trial.json">JSON</a>']
        for name, title in [('verify.log', 'Verifier log'), ('changes.diff', 'Code diff')]:
            if (out / prefix / name).exists():
                links.append(f'<a href="{prefix}/{name}">{title}</a>')
        reason = trial.get('reason', '')
        diff_file = out / prefix / 'changes.diff'
        inline_diff = '<details><summary>查看代码差异 / View diff</summary><pre>' + e(diff_file.read_text(encoding='utf-8', errors='replace')) + '</pre></details>' if diff_file.is_file() else ''
        trials.append(f'<details><summary>#{trial["number"]} · {e(trial["phase"])} · {e(trial["outcome"])} · {e(reason)}</summary>'
                      f'<p>{" · ".join(links)}</p><pre>{e(str(trial.get("changed_files", [])))}</pre>' + inline_diff + '</details>')
    experiment = {key: report.get(key) for key in ('task', 'requested_model', 'codex_version', 'snapshot_sha256',
                  'repeats', 'max_runs', 'max_tokens', 'timeout_seconds', 'protected_files', 'unit_mode')}
    totals = report['usage_totals']
    total_tokens = totals['input_tokens'] + totals['output_tokens']
    token_label = f'{total_tokens:,}' if totals['reported_runs'] else '未上报 / —'
    baseline = latest_evaluation(report, 'full-baseline')
    control = latest_evaluation(report, 'empty-control')
    comparisons = ''
    for name, value in [('完整指令 / Full baseline', baseline), ('无所选指令 / Empty control', control)]:
        if value:
            comparisons += f'<div class="stat">{name}<strong>{value["pass"]} pass / {value["fail"]} fail</strong></div>'
    check = ''
    if report.get('verifier_check'):
        check = '<p>Verifier result: ' + e(str(report['verifier_check'])) + ' · <a href="check.log">Check log</a></p>'
    document = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>RuleBisect · 实验报告</title>
<style>body{background:#101419;color:#e8edf3;font:16px system-ui;margin:0}main{max-width:1050px;margin:auto;padding:44px 24px}
a{color:#82e5bc}.eyebrow,.label{color:#82e5bc;font-size:13px}h1{font-size:clamp(30px,5vw,48px);letter-spacing:-1px;margin:12px 0}
p{line-height:1.7;color:#b9c4ce}.stats{display:flex;gap:16px;flex-wrap:wrap;margin:24px 0}.stat,article,details{background:#1b222b;border:1px solid #344150;border-radius:12px;padding:18px}.stat strong{display:block;font-size:22px;margin-top:10px}
article,details{margin:14px 0}.kept{border-left:4px solid #82e5bc}.removed{opacity:.65}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 monospace}table{width:100%;border-collapse:collapse;font:14px monospace}td,th{text-align:left;padding:12px;border-bottom:1px solid #344150}.table{overflow:auto}.notice{border-left:3px solid #e5be82;padding-left:16px}button,input{font:inherit;border:1px solid #344150;background:#1b222b;color:#e8edf3;padding:10px 14px;border-radius:8px;margin:4px}button{cursor:pointer}button[aria-pressed=true]{border-color:#82e5bc;color:#82e5bc}summary{cursor:pointer}[hidden]{display:none!important}</style>
<main><div class="eyebrow">RULEBISECT / EVIDENCE FIRST</div><h1>哪组指令改变了任务结果？</h1>'''
    document += f'<p class="notice">{e(label)} · {e(report["message"])}</p><p><strong>下一步：</strong>{e(action)}</p>'
    document += f'<div class="stats"><div class="stat">保留指令 / Units<strong>{len(kept)} / {len(rules)}</strong></div>'
    document += f'<div class="stat">运行次数 / Executions<strong>{len(report["trials"])} / {report["max_runs"]}</strong></div><div class="stat">已上报 Token / Reported<strong>{token_label}</strong></div></div>'
    document += '<div class="stats">' + comparisons + '</div>' + check
    document += '<details><summary>Token 明细 / Usage breakdown</summary><pre>' + e(json.dumps(totals, indent=2)) + '</pre></details>'
    document += f'<p>Runner: {e(report["runner"])} · Model: {e(report.get("requested_model") or "simulation")}. '
    document += '结果是有限重复运行的观察，不代表因果关系、统计置信度或全局最小。Token 包括输入与输出，缓存输入已包含在输入中；未上报用量不计入，不能推算费用。</p>'
    document += '<details><summary>任务与实验设置 / Experiment settings</summary><pre>' + e(json.dumps(experiment, ensure_ascii=False, indent=2)) + '</pre></details>'
    patch_link = ' · <a href="candidate.patch">候选指令差异</a>' if (out / 'candidate.patch').is_file() else ''
    document += '<p><a href="report.json">JSON</a> · <a href="report.md">Markdown</a> · <a href="issue.md">精简 Issue 草稿</a>' + patch_link + '</p><h2>指令地图 / Instruction map</h2>' 
    document += '<div><button id="all" aria-pressed="true">全部</button><button id="kept" aria-pressed="false">只看保留</button><input id="search" type="search" placeholder="搜索指令 / Search" aria-label="搜索指令"></div>' + cards
    document += '<h2>实验对照 / Evaluation ledger</h2><div class="table"><table><tr><th>Phase</th><th>Units</th><th>Pass</th><th>Fail</th><th>Error</th><th>Outcome</th></tr>' + rows + '</table></div>'
    document += '<h2>逐次日志与代码差异 / Run evidence</h2>' + ''.join(trials)
    document += '''</main><script>let onlyKept=false;function filter(){const q=document.getElementById('search').value.toLowerCase();document.querySelectorAll('.rule').forEach(el=>{el.hidden=(onlyKept&&el.dataset.kept!=='true')||!el.textContent.toLowerCase().includes(q)});document.getElementById('all').setAttribute('aria-pressed',String(!onlyKept));document.getElementById('kept').setAttribute('aria-pressed',String(onlyKept))}document.getElementById('all').onclick=()=>{onlyKept=false;filter()};document.getElementById('kept').onclick=()=>{onlyKept=true;filter()};document.getElementById('search').oninput=filter;</script></html>'''
    atomic_text(out / 'report.html', document)
