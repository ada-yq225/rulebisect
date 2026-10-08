"""Shared, entirely offline presentation for evidence and shareable summaries."""
from __future__ import annotations


STYLE = r'''
:root {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-synthesis: none; text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  --bg: #f6f5f1; --surface: #ffffff; --surface-muted: #f1f4ef;
  --text: #182b3a; --muted: #687780; --faint: #849087;
  --border: #dee5e1; --border-strong: #cbd7cb;
  --brand: #087f70; --brand-hover: #056653; --brand-soft: #eaf6f0; --on-brand: #ffffff;
  --success: #187149; --success-soft: #eaf5ee; --success-border: #cbe5d5;
  --danger: #b23e4b; --danger-soft: #fff0f1; --danger-border: #f0d2d7;
  --warning: #966112; --warning-soft: #fff6e5; --warning-border: #ecdcb9;
  --code-bg: #f5f7f3; --shadow: 0 8px 28px rgba(27, 48, 34, .035);
  --radius: 14px; --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
body { margin: 0; min-height: 100vh; background: var(--bg); color: var(--text); color-scheme: light; font-size: 14px; line-height: 1.55; }
body[data-theme="dark"] {
  color-scheme: dark;
  --bg: #101720; --surface: #151e29; --surface-muted: #1b2733;
  --text: #e1eae5; --muted: #a0b1ac; --faint: #758b84;
  --border: #293946; --border-strong: #3a4d59;
  --brand: #64d4b3; --brand-hover: #88e2c5; --brand-soft: #183c34; --on-brand: #0d281f;
  --success: #83d9ad; --success-soft: #1b342c; --success-border: #33564a;
  --danger: #f2a0aa; --danger-soft: #382631; --danger-border: #61414b;
  --warning: #e8c281; --warning-soft: #342f23; --warning-border: #5a4d34;
  --code-bg: #111b25; --shadow: 0 8px 28px rgba(0, 0, 0, .08);
}
@media (prefers-color-scheme: dark) {
  body:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #101720; --surface: #151e29; --surface-muted: #1b2733;
    --text: #e1eae5; --muted: #a0b1ac; --faint: #758b84;
    --border: #293946; --border-strong: #3a4d59;
    --brand: #64d4b3; --brand-hover: #88e2c5; --brand-soft: #183c34; --on-brand: #0d281f;
    --success: #83d9ad; --success-soft: #1b342c; --success-border: #33564a;
    --danger: #f2a0aa; --danger-soft: #382631; --danger-border: #61414b;
    --warning: #e8c281; --warning-soft: #342f23; --warning-border: #5a4d34;
    --code-bg: #111b25; --shadow: 0 8px 28px rgba(0, 0, 0, .08);
  }
}
*, *::before, *::after { box-sizing: border-box; }
[hidden] { display: none !important; }
html[data-language="en"] [data-lang="zh"], html[data-language="zh"] [data-lang="en"] { display: none !important; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.skip-link { position: fixed; top: 12px; left: 16px; z-index: 1000; padding: 10px 16px; border: 1px solid var(--brand); border-radius: 8px; background: var(--surface); color: var(--brand); font-size: 12px; font-weight: 650; transform: translateY(-160%); }
.skip-link:focus { transform: translateY(0); }
a { color: var(--brand); text-decoration: none; }
a:hover { text-decoration: underline; text-underline-offset: 3px; }
button, input { font: inherit; }
button { cursor: pointer; }
button:disabled { opacity: .55; cursor: default; }
button, a, input, summary { -webkit-tap-highlight-color: transparent; }
:focus-visible { outline: 3px solid var(--brand); outline-offset: 3px; }
h1, h2, h3, p { margin-top: 0; }
h1, h2, h3 { color: var(--text); line-height: 1.25; }
::selection { background: var(--brand-soft); color: var(--text); }
code { font-family: var(--mono); font-size: .9em; overflow-wrap: anywhere; }
pre { margin: 0; tab-size: 4; }
.icon { display: inline-block; width: 18px; height: 18px; flex: 0 0 auto; vertical-align: -.2em; }
.app-shell { display: grid; grid-template-columns: 220px minmax(0, 1fr); min-height: 100vh; }
.sidebar { position: sticky; top: 0; height: 100vh; height: 100svh; display: flex; flex-direction: column; padding: 28px 18px 20px; background: var(--surface); border-right: 1px solid var(--border); overflow-y: auto; }
.brand { display: flex; align-items: center; gap: 11px; margin: 0 8px 38px; color: var(--text); font-size: 17px; font-weight: 730; letter-spacing: -.035em; text-decoration: none; }
.brand:hover { text-decoration: none; }
.brand-mark { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 10px; color: var(--brand); background: var(--brand-soft); border: 1px solid var(--success-border); }
.brand-mark .icon { width: 22px; height: 22px; }
.nav-label { margin: 0 12px 10px; color: var(--faint); font-size: 10px; font-weight: 700; letter-spacing: .13em; text-transform: uppercase; }
.nav-link { display: flex; align-items: center; gap: 11px; min-height: 41px; margin-bottom: 5px; padding: 9px 12px; border: 1px solid transparent; border-radius: 8px; color: var(--muted); font-size: 13px; font-weight: 550; }
.nav-link:hover { background: var(--surface-muted); color: var(--text); text-decoration: none; }
.nav-link[aria-current="page"], .nav-link[aria-current="true"], .nav-link.is-active, .nav-link.active { background: var(--brand-soft); color: var(--brand); border-color: var(--success-border); }
.nav-link[aria-current="location"] { background: var(--brand-soft); color: var(--brand); border-color: var(--success-border); }
.sidebar-note { margin: auto 10px 0; padding-top: 30px; color: var(--muted); font-size: 11px; line-height: 1.7; overflow-wrap: anywhere; }
.sidebar-note strong { display: block; margin-bottom: 3px; color: var(--text); font-size: 11px; font-weight: 650; }
.workspace { min-width: 0; }
.topbar { display: flex; align-items: center; justify-content: space-between; gap: 20px; min-height: 72px; padding: 16px 38px; border-bottom: 1px solid var(--border); background: var(--surface); }
.breadcrumb { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: 12px; min-width: 0; overflow-wrap: anywhere; }
.breadcrumb strong { color: var(--text); font-weight: 600; }
.breadcrumb .icon { width: 14px; height: 14px; color: var(--faint); }
.topbar-actions { display: flex; align-items: center; gap: 10px; flex: 0 0 auto; }
.source-pill { display: inline-flex; align-items: center; gap: 6px; padding: 5px 9px; border-radius: 6px; border: 1px solid var(--border); color: var(--muted); background: var(--surface-muted); font-size: 10px; font-weight: 650; letter-spacing: .025em; white-space: nowrap; }
.source-pill .icon { width: 13px; height: 13px; }
.btn, .icon-button { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 36px; padding: 8px 13px; border: 1px solid var(--border-strong); border-radius: 8px; background: var(--surface); color: var(--text); font-size: 12px; font-weight: 600; line-height: 1.3; transition: background .12s ease, border-color .12s ease; }
.btn:hover, .icon-button:hover { background: var(--surface-muted); text-decoration: none; }
.btn-primary { border-color: var(--brand); background: var(--brand); color: var(--on-brand); }
.btn-primary:hover { border-color: var(--brand-hover); background: var(--brand-hover); }
.btn-secondary { background: var(--surface); color: var(--text); }
.icon-button { width: 36px; padding: 8px; }
.btn .icon, .icon-button .icon { width: 16px; height: 16px; }
#theme-toggle .icon-sun { display: none; }
body[data-theme="dark"] #theme-toggle .icon-sun { display: inline-block; }
body[data-theme="dark"] #theme-toggle .icon-moon { display: none; }
.page-content { max-width: 1180px; margin: 0 auto; padding: 36px 38px 24px; }
.page-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; margin-bottom: 24px; }
.page-heading h1 { margin-bottom: 9px; font-size: clamp(25px, 2.7vw, 33px); font-weight: 720; letter-spacing: -.045em; }
.eyebrow { margin-bottom: 8px; color: var(--brand); font-size: 10px; font-weight: 750; letter-spacing: .13em; text-transform: uppercase; }
.subtitle { max-width: 760px; margin-bottom: 0; color: var(--muted); font-size: 13px; line-height: 1.75; overflow-wrap: anywhere; }
.hero { display: flex; align-items: flex-start; gap: 18px; margin: 0 0 20px; padding: 24px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow); }
.hero-icon { display: grid; place-items: center; flex: 0 0 auto; width: 43px; height: 43px; color: var(--brand); background: var(--brand-soft); border-radius: 12px; }
.hero-icon .icon { width: 22px; height: 22px; }
.hero-copy { flex: 1; min-width: 0; }
.hero-copy h2 { margin: 0 0 9px; font-size: 20px; font-weight: 650; letter-spacing: -.025em; }
.hero-copy p { margin-bottom: 12px; color: var(--muted); font-size: 13px; line-height: 1.8; overflow-wrap: anywhere; }
.hero-copy p:last-child { margin-bottom: 0; }
.hero[data-tone="danger"] { border-color: var(--danger-border); }
.hero[data-tone="danger"] .hero-icon { background: var(--danger-soft); color: var(--danger); }
.hero[data-tone="warning"] { border-color: var(--warning-border); }
.hero[data-tone="warning"] .hero-icon { background: var(--warning-soft); color: var(--warning); }
.hero[data-tone="success"] { border-color: var(--success-border); }
.hero[data-tone="success"] .hero-icon { background: var(--success-soft); color: var(--success); }
.status-badge, .verdict-badge, .outcome-badge { display: inline-flex; align-items: center; gap: 5px; max-width: 100%; padding: 4px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface-muted); color: var(--muted); font-size: 10px; font-weight: 650; line-height: 1.35; overflow-wrap: anywhere; }
[data-tone="success"].status-badge, [data-tone="success"].verdict-badge, [data-tone="success"].outcome-badge { background: var(--success-soft); color: var(--success); border-color: var(--success-border); }
[data-tone="danger"].status-badge, [data-tone="danger"].verdict-badge, [data-tone="danger"].outcome-badge { background: var(--danger-soft); color: var(--danger); border-color: var(--danger-border); }
[data-tone="warning"].status-badge, [data-tone="warning"].verdict-badge, [data-tone="warning"].outcome-badge { background: var(--warning-soft); color: var(--warning); border-color: var(--warning-border); }
.status-badge .icon, .verdict-badge .icon, .outcome-badge .icon { width: 12px; height: 12px; }
.next-step { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border); color: var(--text); font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }
.next-step strong { color: var(--text); font-weight: 650; }
.next-step code { padding: 3px 6px; background: var(--surface-muted); border: 1px solid var(--border); border-radius: 5px; }
.stats-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 32px; }
.metric { min-width: 0; padding: 18px 19px; background: var(--surface); border: 1px solid var(--border); border-radius: 11px; }
.metric-label { display: flex; align-items: center; gap: 7px; margin-bottom: 12px; color: var(--muted); font-size: 11px; font-weight: 550; }
.metric-label .icon { width: 15px; height: 15px; color: var(--faint); }
.metric-value { color: var(--text); font-size: 27px; font-weight: 700; letter-spacing: -.04em; line-height: 1.15; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.metric-denominator { color: var(--muted); font-size: 14px; font-weight: 500; letter-spacing: 0; }
.metric-detail { margin-top: 8px; color: var(--muted); font-size: 10px; line-height: 1.6; overflow-wrap: anywhere; }
.section { margin: 0 0 30px; scroll-margin-top: 24px; }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-bottom: 13px; }
.section-heading h2 { margin: 0; font-size: 16px; font-weight: 650; letter-spacing: -.02em; }
.section-heading h2 .icon { margin-right: 6px; width: 17px; height: 17px; color: var(--muted); }
.section-note { margin: 5px 0 0; color: var(--muted); font-size: 11px; line-height: 1.7; overflow-wrap: anywhere; }
.panel { min-width: 0; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 13px 16px; border-bottom: 1px solid var(--border); }
.segmented { display: inline-flex; align-items: center; gap: 3px; padding: 3px; border-radius: 8px; background: var(--surface-muted); border: 1px solid var(--border); }
.segmented button, .segmented a { display: inline-flex; align-items: center; gap: 5px; min-height: 28px; padding: 5px 9px; border: 1px solid transparent; border-radius: 5px; background: transparent; color: var(--muted); font-size: 11px; font-weight: 550; line-height: 1.3; }
.segmented button:hover, .segmented a:hover { color: var(--text); text-decoration: none; }
.segmented [aria-pressed="true"], .segmented [aria-selected="true"], .segmented .is-active, .segmented .active { background: var(--surface); border-color: var(--border); color: var(--text); box-shadow: 0 1px 2px rgba(0, 0, 0, .03); }
.search-field { display: inline-flex; align-items: center; gap: 7px; min-width: 140px; max-width: 300px; min-height: 34px; padding: 6px 10px; background: var(--surface); border: 1px solid var(--border); border-radius: 7px; color: var(--muted); }
.search-field:focus-within { border-color: var(--brand); }
.search-field input { width: 100%; min-width: 0; padding: 0; border: 0; background: transparent; color: var(--text); font-size: 11px; outline-offset: 5px; }
input.search-field { color: var(--text); font-size: 11px; }
.search-field input::placeholder, input.search-field::placeholder { color: var(--faint); }
select { min-height: 34px; max-width: 100%; padding: 6px 26px 6px 10px; border: 1px solid var(--border); border-radius: 7px; background: var(--surface); color: var(--text); font: inherit; font-size: 11px; line-height: 1.5; }
.filter-row { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; padding: 13px 16px; border-bottom: 1px solid var(--border); }
.filter-row .search-field { flex: 1 1 180px; max-width: none; }
.filter-row select { flex: 0 1 auto; min-width: 110px; max-width: 220px; }
.filter-row label { color: var(--muted); font-size: 10px; }
.rule-toolbar { align-items: center; flex-wrap: wrap; }
.rule-toolbar .search-field { flex: 1 1 180px; }
.rule-toolbar .section-note, .filter-row .section-note { margin: 0; }
.table-wrap { overflow-x: auto; }
.comparison-matrix { width: 100%; border-collapse: collapse; text-align: left; font-size: 12px; }
.comparison-matrix th { padding: 12px 17px; background: var(--surface-muted); color: var(--muted); font-size: 10px; font-weight: 650; letter-spacing: .025em; white-space: nowrap; }
.comparison-matrix td { padding: 16px 17px; border-top: 1px solid var(--border); vertical-align: middle; overflow-wrap: anywhere; }
.comparison-matrix tbody tr:hover { background: var(--surface-muted); }
.comparison-matrix td:first-child { max-width: 300px; font-weight: 600; }
.comparison-matrix td small { display: block; margin-top: 4px; color: var(--muted); font-size: 10px; font-weight: 400; }
.count-cell { white-space: nowrap; font-variant-numeric: tabular-nums; }
.count-cell .pass { color: var(--success); }
.count-cell .fail { color: var(--danger); }
.mobile-label { display: none; }
.rule-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.rule-card { min-width: 0; padding: 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; }
.rule-card.kept { border-color: var(--success-border); }
.rule-card.removed { background: var(--surface-muted); }
.rule-label { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 11px; color: var(--muted); font-size: 10px; font-weight: 600; }
.rule-label code { min-width: 0; overflow-wrap: anywhere; }
.rule-card pre { color: var(--text); white-space: pre-wrap; overflow-wrap: anywhere; font: 11px/1.75 var(--mono); }
.rule-card .kept { color: var(--success); }
.rule-card .removed { color: var(--muted); }
.evidence-list { display: grid; gap: 10px; }
.evidence-card { min-width: 0; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); overflow: hidden; }
.evidence-summary { display: flex; align-items: center; gap: 13px; min-height: 68px; padding: 16px 18px; list-style: none; cursor: pointer; }
.evidence-summary::-webkit-details-marker { display: none; }
.evidence-summary::marker { content: ''; }
.evidence-summary:hover { background: var(--surface-muted); }
.evidence-summary:focus-visible { outline-offset: -4px; }
.evidence-card:target { border-color: var(--brand); box-shadow: 0 0 0 2px var(--brand-soft); }
.evidence-summary .icon-chevron { margin-left: auto; color: var(--faint); transition: transform .12s ease; }
.evidence-card[open] > .evidence-summary .icon-chevron { transform: rotate(90deg); }
.run-number { display: grid; place-items: center; flex: 0 0 auto; min-width: 31px; height: 31px; padding: 0 6px; background: var(--surface-muted); color: var(--muted); border: 1px solid var(--border); border-radius: 7px; font: 11px var(--mono); }
.summary-meta { min-width: 0; flex: 1; color: var(--text); font-size: 12px; font-weight: 550; overflow-wrap: anywhere; }
.summary-meta small { display: block; margin-top: 4px; color: var(--muted); font-size: 10px; font-weight: 400; }
.evidence-body { padding: 0 18px 18px; border-top: 1px solid var(--border); color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
.evidence-body p { margin: 14px 0; }
.artifact-links { display: flex; flex-wrap: wrap; gap: 8px 16px; margin: 15px 0; font-size: 11px; }
.artifact-links a { display: inline-flex; align-items: center; gap: 5px; }
.artifact-links .icon { width: 13px; height: 13px; }
.code-block { max-height: 540px; margin-top: 12px; padding: 16px; overflow: auto; border: 1px solid var(--border); border-radius: 8px; background: var(--code-bg); color: var(--text); white-space: pre-wrap; overflow-wrap: anywhere; font: 11px/1.8 var(--mono); }
.code-block code { font: inherit; }
.code-block .diff-add, .code-block .added { color: var(--success); }
.code-block .diff-del, .code-block .deleted { color: var(--danger); }
.code-block .diff-meta { color: var(--muted); }
.diff-line { display: block; min-height: 1.8em; }
.diff-add { color: var(--success); background: var(--success-soft); }
.diff-del { color: var(--danger); background: var(--danger-soft); }
.diff-header, .diff-hunk { color: var(--brand); }
.diff-meta, .diff-context { color: var(--muted); }
.changed-files { display: grid; gap: 6px; margin: 14px 0; padding: 0; list-style: none; }
.changed-files li { display: flex; align-items: flex-start; gap: 9px; padding: 7px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface-muted); color: var(--muted); font-size: 10px; }
.changed-files code { min-width: 0; flex: 1; color: var(--text); font-size: 10px; overflow-wrap: anywhere; }
.changed-files .icon { width: 13px; height: 13px; margin-top: 2px; }
.notice { display: flex; align-items: flex-start; gap: 10px; margin: 16px 0; padding: 13px 15px; border: 1px solid var(--border); border-radius: 9px; background: var(--surface-muted); color: var(--muted); font-size: 11px; line-height: 1.75; overflow-wrap: anywhere; }
.notice .icon { margin-top: 2px; width: 16px; height: 16px; }
.notice p { margin: 0; }
.notice-warning { color: var(--warning); background: var(--warning-soft); border-color: var(--warning-border); }
.empty-state { padding: 36px 24px; color: var(--muted); font-size: 12px; text-align: center; line-height: 1.8; }
.empty-state .icon { display: block; width: 27px; height: 27px; margin: 0 auto 12px; color: var(--faint); }
.empty-state strong { display: block; margin-bottom: 5px; color: var(--text); font-weight: 600; }
.disclosure { color: var(--muted); font-size: 11px; line-height: 1.8; }
.disclosure summary { padding: 12px 0; color: var(--text); font-weight: 550; cursor: pointer; }
.disclosure ul { margin: 0 0 15px; padding-left: 20px; }
.disclosure li { margin-bottom: 5px; }
.settings-disclosure > summary { padding: 15px 18px; }
.settings-disclosure + .settings-disclosure { border-top: 1px solid var(--border); }
.settings-disclosure > .fact-list { padding: 0 18px 18px; }
.settings-disclosure > .disclosure { margin: 0 18px 18px; }
.settings-disclosure > .code-block { margin: 0 18px 16px; }
.settings-disclosure > p { margin: 0 18px 18px; }
.footer { display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-top: 30px; padding: 20px 0 4px; border-top: 1px solid var(--border); color: var(--faint); font-size: 10px; line-height: 1.75; overflow-wrap: anywhere; }
.footer a { color: var(--muted); }
.share-shell { width: 100%; max-width: 920px; margin: 0 auto; padding: 38px 24px 24px; }
.summary-header { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 32px; }
.summary-header .brand { margin: 0; }
.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 13px; margin: 22px 0; }
.mini-stat { min-width: 0; padding: 17px 18px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.mini-stat .metric-label { margin-bottom: 9px; }
.mini-stat .metric-value { font-size: 24px; }
.privacy-banner { display: flex; align-items: flex-start; gap: 11px; margin: 22px 0; padding: 16px 18px; border: 1px solid var(--success-border); border-radius: 10px; background: var(--success-soft); color: var(--success); font-size: 11px; line-height: 1.8; }
.privacy-banner .icon { width: 18px; height: 18px; margin-top: 2px; }
.privacy-banner p { margin: 0; }
.fact-list { margin: 0; padding: 0; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
dl.fact-list { display: grid; grid-template-columns: 160px minmax(0, 1fr); gap: 12px 20px; padding: 20px; }
.fact-list dt { color: var(--muted); }
.fact-list dd { margin: 0; color: var(--text); }
ul.fact-list { list-style: none; }
.fact-list li { display: flex; justify-content: space-between; gap: 20px; padding: 13px 20px; border-bottom: 1px solid var(--border); }
.fact-list li:last-child { border-bottom: 0; }
@media (max-width: 1100px) {
  .app-shell { grid-template-columns: 200px minmax(0, 1fr); }
  .page-content { padding: 30px 26px 22px; }
  .topbar { padding: 15px 26px; }
  .stats-grid { gap: 10px; }
  .metric { padding: 16px 14px; }
  .metric-value { font-size: 25px; }
}
@media (max-width: 850px) {
  .app-shell { display: block; }
  .sidebar { position: static; height: auto; padding: 16px 22px 12px; border-right: 0; border-bottom: 1px solid var(--border); overflow: visible; }
  .brand { margin: 0 0 16px; }
  .sidebar nav { display: flex; flex-wrap: wrap; gap: 5px; }
  .sidebar .nav-label, .sidebar-note { display: none; }
  .nav-link { min-height: 34px; margin: 0; padding: 7px 10px; font-size: 11px; }
  .nav-link .icon { width: 15px; height: 15px; }
  .topbar { min-height: 60px; padding: 13px 22px; }
  .page-content { padding: 28px 22px 20px; }
}
@media (max-width: 620px) {
  .sidebar { padding: 16px 16px 12px; }
  .topbar { flex-wrap: wrap; gap: 12px; padding: 12px 16px; }
  .topbar-actions { gap: 7px; }
  .page-content { padding: 24px 16px 18px; }
  .page-heading { display: block; margin-bottom: 20px; }
  .page-heading > .btn { margin-top: 14px; }
  .hero { padding: 18px; gap: 12px; }
  .hero-icon { width: 34px; height: 34px; border-radius: 9px; }
  .hero-icon .icon { width: 18px; height: 18px; }
  .hero-copy h2 { font-size: 18px; }
  .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 26px; }
  .metric { padding: 15px; }
  .metric-value { font-size: 24px; }
  .metric-label { margin-bottom: 10px; font-size: 10px; }
  .section-heading { align-items: flex-start; flex-wrap: wrap; gap: 8px; }
  .toolbar { align-items: stretch; flex-direction: column; padding: 12px; }
  .filter-row { align-items: stretch; gap: 8px; padding: 12px; }
  .filter-row .search-field { flex-basis: 100%; }
  .filter-row select { flex: 1 1 110px; max-width: none; }
  .rule-toolbar .search-field { flex-basis: auto; }
  .segmented { align-self: flex-start; flex-wrap: wrap; }
  .search-field { width: 100%; max-width: none; }
  .comparison-matrix, .comparison-matrix tbody { display: block; width: 100%; }
  .comparison-matrix thead { display: none; }
  .comparison-matrix tbody tr { display: block; padding: 14px 16px; border-top: 1px solid var(--border); }
  .comparison-matrix tbody tr:first-child { border-top: 0; }
  .comparison-matrix td { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 6px 0; border: 0; }
  .comparison-matrix td:first-child { display: block; max-width: none; margin-bottom: 8px; padding: 0; }
  .mobile-label { display: inline; flex: 0 0 auto; color: var(--muted); font-size: 10px; font-weight: 500; }
  .comparison-matrix td:first-child .mobile-label { display: block; margin-bottom: 4px; }
  .ledger-table { display: table; min-width: 620px; }
  .ledger-table thead { display: table-header-group; }
  .ledger-table tbody { display: table-row-group; }
  .ledger-table tbody tr { display: table-row; padding: 0; border: 0; }
  .ledger-table td, .ledger-table td:first-child { display: table-cell; padding: 12px 16px; margin: 0; border-top: 1px solid var(--border); }
  .rule-grid { grid-template-columns: minmax(0, 1fr); }
  .evidence-summary { gap: 10px; padding: 14px 12px; }
  .summary-meta { font-size: 11px; }
  .evidence-body { padding: 0 12px 14px; }
  .code-block { padding: 12px; font-size: 10px; }
  .footer { display: block; }
  .footer > * + * { margin-top: 6px; }
  .share-shell { padding: 24px 16px 20px; }
  .summary-header { align-items: flex-start; flex-wrap: wrap; margin-bottom: 26px; }
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .mini-stat { padding: 15px; }
  dl.fact-list { grid-template-columns: minmax(0, 1fr); gap: 5px; padding: 16px; }
  .fact-list dd { margin-bottom: 10px; }
}
@media (max-width: 360px) {
  .stats-grid, .summary-grid { grid-template-columns: minmax(0, 1fr); }
  .hero { display: block; }
  .hero-icon { margin-bottom: 13px; }
  .source-pill { white-space: normal; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; animation: none !important; }
}
@media print {
  body, body[data-theme="dark"], body[data-theme="light"], body:not([data-theme="light"]) { color-scheme: light; --bg: white; --surface: white; --surface-muted: #f5f5f5; --text: #111; --muted: #555; --faint: #666; --border: #ddd; --code-bg: #f5f5f5; --shadow: none; --brand: #087f70; --success: #187149; --success-soft: #eaf5ee; --danger: #b23e4b; --danger-soft: #fff0f1; --warning: #966112; --warning-soft: #fff6e5; }
  .app-shell { display: block; }
  .sidebar, .topbar-actions, .toolbar { display: none; }
  .topbar { padding: 0 0 16px; background: white; }
  .page-content, .share-shell { max-width: none; padding: 0; }
  .hero, .metric, .rule-card, .evidence-card { break-inside: avoid; box-shadow: none; }
  .code-block { max-height: none; }
  .footer { margin-top: 20px; }
}
'''


def styles() -> str:
    """Return shared CSS for insertion inside a local HTML ``style`` element."""
    return STYLE


_ICONS = {
    'mark': '<path d="M5 4h5v16H5zM14 4h5v16h-5z"/><path d="m3 16 18-8"/>',
    'flask': '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-9V3M8 14h8"/>',
    'compare': '<path d="M4 7h15m-4-4 4 4-4 4M20 17H5m4-4-4 4 4 4"/>',
    'checks': '<rect x="4" y="3" width="16" height="18" rx="3"/><path d="m8 9 2 2 5-5m-7 9 2 2 5-5"/>',
    'rules': '<path d="M6 4h12M6 9h12M6 14h8M6 19h8"/><path d="m17 16 2 2 3-4"/>',
    'activity': '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    'download': '<path d="M12 3v12m-4-4 4 4 4-4M4 16v4h16v-4"/>',
    'sun': '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4 19 5"/>',
    'moon': '<path d="M20.7 14.3A9 9 0 0 1 9.7 3.3 9 9 0 1 0 20.7 14.3Z"/>',
    'arrow': '<path d="M5 12h14m-6-6 6 6-6 6"/>',
    'chevron': '<path d="m9 5 7 7-7 7"/>',
    'shield': '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
    'file': '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Z"/><path d="M14 3v6h6M8 14h8M8 17h5"/>',
    'warning': '<path d="m10.3 4-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3l-8-14a2 2 0 0 0-3.4 0Z"/><path d="M12 9v5m0 3h.01"/>',
    'success': '<circle cx="12" cy="12" r="9"/><path d="m7.5 12 3 3 6-6"/>',
}


def svg_icon(name: str) -> str:
    """Return a fixed decorative SVG; the surrounding control provides its label."""
    if not isinstance(name, str) or name not in _ICONS:
        raise ValueError('Unknown UI icon')
    return (f'<svg class="icon icon-{name}" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
            'stroke-linejoin="round" aria-hidden="true" focusable="false">'
            f'{_ICONS[name]}</svg>')


SCRIPT = r'''
(() => {
  "use strict";
  const root = document.documentElement;
  const body = document.body;
  if (!root || !body) return;
  const byId = id => document.getElementById(id);
  const all = selector => Array.from(document.querySelectorAll(selector));
  const bind = (element, event, callback) => {
    if (element) element.addEventListener(event, callback);
  };
  const readPreference = key => {
    try { return window.localStorage.getItem(key); } catch (_) { return null; }
  };
  const savePreference = (key, value) => {
    try { window.localStorage.setItem(key, value); } catch (_) { /* Optional on file URLs. */ }
  };
  const storedLanguage = readPreference("rulebisect-language");
  const browserLanguage = typeof navigator === "undefined" ? "en" : (navigator.language || "en");
  let language = storedLanguage === "en" || storedLanguage === "zh" ? storedLanguage
    : (browserLanguage.toLowerCase().startsWith("zh") ? "zh" : "en");
  const storedTheme = readPreference("rulebisect-theme");
  let themeChoice = storedTheme === "light" || storedTheme === "dark" ? storedTheme : null;
  const colorPreference = typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  const themeButton = byId("theme-toggle");
  const languageSelect = byId("language-select");
  const theme = () => themeChoice || (colorPreference && colorPreference.matches ? "dark" : "light");
  function updateTheme() {
    const current = theme();
    body.dataset.theme = current;
    if (themeButton) {
      themeButton.dataset.currentTheme = current;
      themeButton.setAttribute("aria-pressed", String(current === "dark"));
      const label = language === "zh"
        ? (current === "dark" ? "切换至浅色主题" : "切换至深色主题")
        : (current === "dark" ? "Switch to light theme" : "Switch to dark theme");
      themeButton.setAttribute("aria-label", label);
      themeButton.setAttribute("title", label);
    }
  }
  bind(themeButton, "click", () => {
    themeChoice = theme() === "dark" ? "light" : "dark";
    savePreference("rulebisect-theme", themeChoice);
    updateTheme();
  });
  if (colorPreference && typeof colorPreference.addEventListener === "function") {
    colorPreference.addEventListener("change", () => { if (!themeChoice) updateTheme(); });
  }

  const rules = all(".rule-card").map(element => ({
    element, text: element.textContent.toLowerCase(),
    kept: ["true", "1", "yes", "kept"].includes((element.dataset.kept || "").toLowerCase())
  }));
  const ruleSearch = byId("search");
  const allRulesButton = byId("all");
  const keptRulesButton = byId("kept");
  let onlyKept = !!keptRulesButton && keptRulesButton.getAttribute("aria-pressed") === "true";
  const ruleCounter = byId("visible-rules");
  const noRules = byId("no-rules");
  function updateRules() {
    const query = ruleSearch ? ruleSearch.value.trim().toLowerCase() : "";
    let shown = 0;
    for (const rule of rules) {
      const visible = (!onlyKept || rule.kept) && (!query || rule.text.includes(query));
      rule.element.hidden = !visible;
      if (visible) shown++;
    }
    if (allRulesButton) allRulesButton.setAttribute("aria-pressed", String(!onlyKept));
    if (keptRulesButton) keptRulesButton.setAttribute("aria-pressed", String(onlyKept));
    if (ruleCounter) ruleCounter.textContent = language === "zh"
      ? `显示 ${shown} / ${rules.length} 条规则` : `${shown} of ${rules.length} rules shown`;
    if (noRules) noRules.hidden = rules.length === 0 || shown > 0;
  }
  bind(ruleSearch, "input", updateRules);
  bind(allRulesButton, "click", () => { onlyKept = false; updateRules(); });
  bind(keptRulesButton, "click", () => { onlyKept = true; updateRules(); });

  const runs = all(".evidence-card").map(element => ({
    element, caseId: element.dataset.case || "", phase: element.dataset.phase || "",
    outcome: element.dataset.outcome || "",
    text: [element.id, element.dataset.case, element.dataset.phase, element.dataset.outcome,
      element.textContent].join(" ").toLowerCase()
  }));
  const runSearch = byId("run-search");
  const outcomeFilter = byId("outcome-filter");
  const phaseFilter = byId("phase-filter");
  const caseFilter = byId("case-filter");
  const runCounter = byId("visible-runs");
  const noRuns = byId("no-runs");
  function updateRuns() {
    const query = runSearch ? runSearch.value.trim().toLowerCase() : "";
    const outcome = outcomeFilter ? outcomeFilter.value : "";
    const phase = phaseFilter ? phaseFilter.value : "";
    const caseId = caseFilter ? caseFilter.value : "";
    let shown = 0;
    for (const run of runs) {
      const visible = (!query || run.text.includes(query)) && (!outcome || run.outcome === outcome)
        && (!phase || run.phase === phase) && (!caseId || run.caseId === caseId);
      run.element.hidden = !visible;
      if (visible) shown++;
    }
    if (runCounter) runCounter.textContent = language === "zh"
      ? `显示 ${shown} / ${runs.length} 次运行` : `${shown} of ${runs.length} runs shown`;
    if (noRuns) noRuns.hidden = runs.length === 0 || shown > 0;
  }
  function resetRunFilters() {
    for (const control of [runSearch, outcomeFilter, phaseFilter, caseFilter]) {
      if (control) control.value = "";
    }
    updateRuns();
  }
  bind(runSearch, "input", updateRuns);
  for (const select of [outcomeFilter, phaseFilter, caseFilter]) bind(select, "change", updateRuns);
  bind(byId("reset-filters"), "click", event => { event.preventDefault(); resetRunFilters(); });

  function updateLanguage() {
    root.dataset.language = language;
    root.lang = language === "zh" ? "zh-CN" : "en";
    if (languageSelect) languageSelect.value = language;
    if (ruleSearch) ruleSearch.setAttribute("placeholder", language === "zh" ? "搜索规则或文件…" : "Search rules or files…");
    if (runSearch) runSearch.setAttribute("placeholder", language === "zh" ? "搜索运行记录…" : "Search run evidence…");
    updateTheme();
    updateRules();
    updateRuns();
  }
  bind(languageSelect, "change", () => {
    if (languageSelect.value !== "en" && languageSelect.value !== "zh") return;
    language = languageSelect.value;
    savePreference("rulebisect-language", language);
    updateLanguage();
  });

  const navigation = all('.sidebar .nav-link[href^="#"]');
  function fragment() {
    try { return decodeURIComponent(window.location.hash.slice(1)); }
    catch (_) { return ""; }
  }
  function updateNavigation(target) {
    const section = target && typeof target.closest === "function" ? target.closest(".section") : null;
    const selected = section && section.id ? section.id : fragment();
    let matched = false;
    for (const link of navigation) {
      const active = (link.getAttribute("href") || "").slice(1) === selected;
      link.classList.remove("active", "is-active");
      if (active) { link.setAttribute("aria-current", "location"); matched = true; }
      else link.removeAttribute("aria-current");
    }
    if (!matched && !selected && navigation.length) navigation[0].setAttribute("aria-current", "location");
  }
  function revealAnchor() {
    const id = fragment();
    const target = id ? byId(id) : null;
    if (target && /^run-\d+$/.test(id) && target.classList.contains("evidence-card")) {
      resetRunFilters();
      target.hidden = false;
      if (target.tagName === "DETAILS") target.open = true;
      const scroll = () => {
        if (typeof target.scrollIntoView === "function") target.scrollIntoView({ block: "start" });
      };
      if (typeof window.requestAnimationFrame === "function") window.requestAnimationFrame(scroll);
      else scroll();
    }
    updateNavigation(target);
  }
  bind(window, "hashchange", revealAnchor);
  for (const link of all('a[href^="#"]')) {
    bind(link, "click", event => {
      if (event.defaultPrevented || event.button > 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      if (link.getAttribute("href") === window.location.hash) revealAnchor();
    });
  }
  updateLanguage();
  for (const control of all(".js-control")) control.hidden = false;
  revealAnchor();
})();
'''


def script() -> str:
    """Return fixed report interactions; it embeds no report data and makes no requests."""
    return SCRIPT
