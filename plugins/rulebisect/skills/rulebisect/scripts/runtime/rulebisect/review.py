"""Offline previews of instruction comparisons, before any model calls."""
from __future__ import annotations

from html import escape

from .ui import svg_icon


# Bound both the text payload and the number of elements in a saved preview.
_MAX_DIFF_CHARS = 96 * 1024
_MAX_DIFF_LINES = 600


def _source_label(source):
    if source['kind'] == 'git':
        return source['ref']
    if source['kind'] == 'directory':
        return source['path']
    return 'Working tree / 当前工作区'


def review_text(plan: dict, command: str) -> str:
    changes = plan['instruction_changes']
    changed = [entry for entry in changes if entry['changed']]
    lines = ['RuleBisect · Instruction review / 规则变更预览']
    for key, label in [('baseline', 'Before'), ('candidate', 'After')]:
        source = plan['instruction_sources'][key]
        commit = ' @ ' + source['commit'] if source['kind'] == 'git' else ''
        lines.append(f'{label}: {_source_label(source)}{commit}')
    lines.append(f'{len(changed)} of {len(changes)} selected instruction files changed.')
    for entry in changed:
        lines.append(f"  +{entry['added_lines']} -{entry['removed_lines']}  {entry['path']}")
    lines.append('Selected cases: ' + ', '.join(plan['cases']))
    omitted = plan['case_selection']['omitted']
    if omitted:
        lines.append('Omitted cases: ' + ', '.join(omitted))
    lines.extend([f"Planned calls: {plan['required_calls']} (cap {plan['max_runs']}). "
                  "Model calls made: 0. No results yet.",
                  'Both variants use the current repository code and checks.',
                  ('Choose a model by replacing YOUR_CODEX_MODEL_ID, then run:' if not plan.get('model') else 'Run comparison:'), command])
    return '\n'.join(lines)


def _source_card(source, label):
    title = escape(_source_label(source))
    detail = ''
    if source['kind'] == 'git':
        detail = f'<small>Commit / 提交</small><code>{escape(source["commit"])}</code>'
    return f'<article class="source"><h3>{label}</h3><strong>{title}</strong>{detail}</article>'


def _diff_html(diff, any_changed):
    if not diff:
        message = ('No textual patch is available. / 没有可展示的文本补丁。' if any_changed else
                   'Selected instruction files are identical. / 所选规则文件内容相同。')
        return f'<p>{message}</p>'
    prefix = diff[:_MAX_DIFF_CHARS]
    lines = prefix.splitlines(keepends=True)
    truncated = len(diff) > len(prefix) or len(lines) > _MAX_DIFF_LINES
    rendered = []
    for line in lines[:_MAX_DIFF_LINES]:
        tone = ''
        if line.startswith(('+++ ', '--- ', '@@')):
            tone = 'meta'
        elif line.startswith('+'):
            tone = 'added'
        elif line.startswith('-'):
            tone = 'removed'
        rendered.append(f'<span class="{tone}">{escape(line)}</span>')
    notice = ('<p>Diff preview truncated. Counts cover the full change. / '
              '差异预览已截断，统计包含全部改动。</p>' if truncated else '')
    return '<pre class="diff" tabindex="0" aria-label="Unified diff / 统一差异"><code>' + ''.join(rendered) + '</code></pre>' + notice


_STYLE = """
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#192c35;background:#f5f6f2;line-height:1.55}
*{box-sizing:border-box}body{margin:0}main{max-width:65rem;margin:auto;padding:2rem clamp(1rem,4vw,3rem) 4rem}
header{border-bottom:2px solid #126955;padding-bottom:1rem;margin-bottom:1.3rem}
.brand{display:flex;align-items:center;gap:.45rem;color:#126955;font-weight:750}
.icon{width:1.4rem;height:1.4rem}h1{font-size:clamp(1.6rem,4vw,2.4rem);line-height:1.2;margin:.8rem 0}
h2{font-size:1.18rem;margin:0 0 .9rem}h3,dt,small{font-size:.8rem;font-weight:650;color:#405662}
section{margin:1rem 0;background:white;border:1px solid #cdd7d0;border-radius:.8rem;padding:clamp(1rem,3vw,1.55rem)}
p{margin:.7rem 0 0}h3,dd{margin:0}.sources,.budget{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}
.source{border-left:3px solid #17816a;padding-left:.8rem}.source>*{display:block;overflow-wrap:anywhere}.source strong{font-size:1.05rem}.source small{margin-top:.5rem}
.budget{margin:.8rem 0;grid-template-columns:repeat(auto-fit,minmax(8rem,1fr))}.budget dd{font-weight:700}
code,pre{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.88rem}pre{margin:.8rem 0 0;padding:1rem;background:#eef2ee;border-radius:.45rem}
.diff{overflow:auto;max-height:30rem;tab-size:4;line-height:1.5}.diff span{white-space:pre}.added{color:#075737;background:#ddf4e6}.removed{color:#8c2631;background:#ffe1e1}.meta{color:#465e6b}
.files{list-style:none;padding:0;margin:.5rem 0}.files li{display:flex;justify-content:space-between;gap:1rem;padding:.4rem 0;border-top:1px solid #e0e6e0}
.files code,.cases,dd,.cmd{overflow-wrap:anywhere}.counts{white-space:nowrap}.cmd{white-space:pre-wrap;color:#f4ffff;background:#163e38;user-select:all}
:focus-visible{outline:3px solid #157e69;outline-offset:2px}@media(max-width:36rem){.sources{grid-template-columns:1fr}.files li{flex-wrap:wrap}}
@media print{main{max-width:100%;padding:0}.diff{max-height:none;white-space:pre-wrap}.diff span{white-space:pre-wrap}}
"""


def render_review(plan: dict, diff: str, command: str) -> str:
    """Produce a standalone local document. Only caller-supplied text is displayed."""
    changes = plan['instruction_changes']
    changed_count = sum(1 for entry in changes if entry['changed'])
    sources = plan['instruction_sources']
    files = []
    for entry in changes:
        counts = (f"+{int(entry['added_lines'])} / −{int(entry['removed_lines'])}" if entry['changed']
                  else 'Unchanged / 无改动')
        files.append(f'<li><code>{escape(entry["path"])}</code><span class="counts">{counts}</span></li>')
    selected = escape(', '.join(plan['cases']))
    omitted = escape(', '.join(plan['case_selection']['omitted']) or 'None / 无')
    budget = [('Planned calls / 计划调用', plan['required_calls']),
              ('Call cap / 调用上限', plan['max_runs']),
              ('Model / 模型', plan.get('model') or 'Choose at execution / 执行时指定')]
    if plan.get('max_tokens') is not None:
        budget.append(('Reported token cap / 已上报 Token 上限', plan['max_tokens']))
    budget_html = ''.join(f'<div><dt>{label}</dt><dd>{escape(str(value))}</dd></div>' for label, value in budget)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Instruction review / 规则变更预览 · RuleBisect</title><style>{_STYLE}</style></head><body><main>
<header><div class="brand">{svg_icon('mark')}RuleBisect</div>
<h1>Instruction review / 规则变更预览</h1><p>Model calls made: 0. No results yet. / 已调用模型 0 次，尚无实验结果。</p></header>
<section><h2>Instructions to compare / 待比较的规则</h2><div class="sources">
{_source_card(sources['baseline'], 'Before / 基准')}{_source_card(sources['candidate'], 'After / 提案')}</div>
<p>Both variants use the current repository code and checks. / 两组均使用当前仓库的代码和验证器。</p></section>
<section><h2>File changes / 文件改动</h2><p>{changed_count} / {len(changes)} selected files changed · 所选文件中有 {changed_count} 个发生改动</p>
<ul class="files">{''.join(files)}</ul>{_diff_html(diff, bool(changed_count))}</section>
<section><h2>Experiment plan / 实验计划</h2><dl class="budget">{budget_html}</dl>
<p class="cases"><strong>Selected / 所选用例</strong>　{selected}</p>
<p class="cases"><strong>Omitted / 未选用例</strong>　{omitted}</p></section>
<section><h2>Run comparison / 执行对照实验</h2>
<p>This command uses your Codex account. / 此命令使用你的 Codex 账户执行实验。</p>
{'<p>Replace YOUR_CODEX_MODEL_ID with your model. / 请将 YOUR_CODEX_MODEL_ID 替换为你的模型。</p>' if not plan.get('model') else ''}
<pre class="cmd" tabindex="0"><code>{escape(command)}</code></pre></section></main></body></html>
"""
