#!/usr/bin/env node
/**
 * Reproducible mock-DOM logic checks using real, generated offline report HTML.
 * No browser, rendering, layout, screenshots, network, npm or dependencies.
 * Usage: PYTHON=python3 node scripts/check_report_controls.mjs REPORT.html [...]
 */
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const helper = fileURLToPath(new URL('./report_dom_fixture.py', import.meta.url));
const args = process.argv.slice(2);
if (!args.length) {
  console.error('Usage: PYTHON=python3 node scripts/check_report_controls.mjs REPORT.html [REPORT.html ...]');
  process.exit(2);
}

function loadFixture(html) {
  const result = spawnSync(process.env.PYTHON || 'python3', [helper, '--', html], {
    encoding: 'utf8', maxBuffer: 64 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(result.stderr.trim() || 'HTML fixture extraction failed');
  return JSON.parse(result.stdout);
}

class Element {
  constructor(node) {
    this.key = node.key;
    this.parentKey = node.parent;
    this.tagName = node.tag.toUpperCase();
    this.attributes = { ...node.attrs };
    this.id = node.attrs.id || '';
    this.textContent = node.text;
    this.hidden = Object.hasOwn(node.attrs, 'hidden');
    this.open = Object.hasOwn(node.attrs, 'open');
    this.value = node.attrs.value || '';
    this.dataset = Object.fromEntries(Object.entries(node.attrs).filter(([name]) => name.startsWith('data-'))
      .map(([name, value]) => [name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()), value || '']));
    const classes = new Set((node.attrs.class || '').split(/\s+/).filter(Boolean));
    this.classList = {
      contains: value => classes.has(value),
      remove: (...values) => values.forEach(value => classes.delete(value)),
    };
    this.events = new Map();
    Object.defineProperty(this, 'innerHTML', { set() { throw new Error('Unsafe innerHTML write'); } });
  }
  addEventListener(name, callback) {
    if (!this.events.has(name)) this.events.set(name, []);
    this.events.get(name).push(callback);
  }
  getAttribute(name) { return Object.hasOwn(this.attributes, name) ? this.attributes[name] : null; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  removeAttribute(name) { delete this.attributes[name]; }
  fire(name, options = {}) {
    const event = { button: 0, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...options };
    for (const callback of this.events.get(name) || []) callback(event);
    return event;
  }
  closest(selector) {
    assert.equal(selector, '.section', 'Unexpected or user-derived ancestor selector');
    for (let element = this; element; element = element.parent) {
      if (element.classList.contains('section')) return element;
    }
    return null;
  }
  scrollIntoView() { this.scrolled = true; }
}

function mockDom(fixture, { empty = false, withoutControls = false, blockedStorage = false,
                           browserLanguage = 'en-US', dark = false, preferences = {} } = {}) {
  const omitted = new Set();
  for (const node of fixture.nodes) {
    const classes = (node.attrs.class || '').split(/\s+/);
    if (omitted.has(node.parent) || (empty && classes.some(name => ['rule-card', 'evidence-card'].includes(name)))
        || (withoutControls && classes.includes('js-control'))) omitted.add(node.key);
  }
  const elements = fixture.nodes.filter(node => !omitted.has(node.key)).map(node => new Element(node));
  const keys = new Map(elements.map(element => [element.key, element]));
  const ids = new Map(elements.filter(element => element.id).map(element => [element.id, element]));
  for (const element of elements) element.parent = keys.get(element.parentKey) || null;
  for (const select of elements.filter(element => element.tagName === 'SELECT')) {
    const options = elements.filter(element => element.tagName === 'OPTION' && element.parent === select);
    select.options = options;
    select.value = (options.find(element => element.getAttribute('selected') !== null) || options[0])?.value || '';
  }
  const withClass = name => elements.filter(element => element.classList.contains(name));
  const rules = withClass('rule-card');
  const runs = withClass('evidence-card');
  const anchors = elements.filter(element => element.tagName === 'A' && (element.getAttribute('href') || '').startsWith('#'));
  const navigation = anchors.filter(element => element.classList.contains('nav-link') && (() => {
    for (let parent = element.parent; parent; parent = parent.parent) if (parent.classList.contains('sidebar')) return true;
    return false;
  })());
  const controls = withClass('js-control');
  const root = elements.find(element => element.tagName === 'HTML');
  const body = elements.find(element => element.tagName === 'BODY');
  const storage = { ...preferences };
  const windowEvents = new Map();
  const media = {
    matches: dark,
    addEventListener(name, callback) { assert.equal(name, 'change'); this.callback = callback; },
    change(matches) { this.matches = matches; if (this.callback) this.callback(); },
  };
  const window = {
    location: { hash: '' },
    localStorage: {
      getItem(key) { if (blockedStorage) throw new Error('Storage blocked'); return storage[key] || null; },
      setItem(key, value) { if (blockedStorage) throw new Error('Storage blocked'); storage[key] = value; },
    },
    matchMedia(query) { assert.equal(query, '(prefers-color-scheme: dark)'); return media; },
    requestAnimationFrame(callback) { callback(); },
    addEventListener(name, callback) { windowEvents.set(name, callback); },
  };
  const selections = new Map([
    ['.rule-card', rules], ['.evidence-card', runs], ['.js-control', controls],
    ['.sidebar .nav-link[href^="#"]', navigation], ['a[href^="#"]', anchors],
  ]);
  const document = {
    documentElement: root, body,
    getElementById(id) { return ids.get(id) || null; },
    querySelectorAll(selector) {
      assert(selections.has(selector), 'Unexpected or user-derived selector');
      return selections.get(selector);
    },
  };
  const noNetwork = () => { throw new Error('Report controls must not make network requests'); };
  const context = vm.createContext({ document, window, navigator: { language: browserLanguage },
    fetch: noNetwork, XMLHttpRequest: noNetwork, WebSocket: noNetwork });
  return {
    ids, root, body, rules, runs, controls, anchors, navigation, storage, media, window,
    start() { vm.runInContext(fixture.script, context, { timeout: 5000 }); },
    hash(value) { window.location.hash = value; windowEvents.get('hashchange')?.(); },
  };
}

function visible(items) { return items.filter(item => !item.hidden).map(item => item.key); }
function verifyVisible(items, expected) { assert.deepEqual(visible(items), expected.map(item => item.key)); }
function verifyCounter(environment, id, shown, total, language = 'en') {
  const element = environment.ids.get(id);
  if (!element) return;
  assert.deepEqual((element.textContent.match(/\d+/g) || []).map(Number), [shown, total], id);
  assert(element.textContent.includes(language === 'zh' ? '显示' : 'shown'), 'Counter language mismatch');
}
function setControl(environment, id, value, event) {
  const element = environment.ids.get(id);
  assert(element, `Expected control #${id}`);
  if (element.tagName === 'SELECT') assert(element.options.some(option => option.value === value), `Missing option in #${id}`);
  element.value = value;
  element.fire(event);
}
function absentQuery(environment) {
  const text = [...environment.rules, ...environment.runs].map(element => element.textContent).join(' ');
  let query = '__rulebisect_no_matching_evidence__';
  while (text.includes(query)) query += '_';
  return query;
}

function checkReport(fixture) {
  const environment = mockDom(fixture);
  environment.start();
  assert(environment.controls.every(element => !element.hidden), 'Progressive controls were not enabled');
  verifyVisible(environment.rules, environment.rules);
  verifyVisible(environment.runs, environment.runs);
  verifyCounter(environment, 'visible-rules', environment.rules.length, environment.rules.length);
  verifyCounter(environment, 'visible-runs', environment.runs.length, environment.runs.length);
  assert.equal(environment.body.dataset.theme, 'light');
  assert.equal(environment.root.lang, 'en');
  const absent = absentQuery(environment);

  if (environment.ids.has('kept')) {
    environment.ids.get('kept').fire('click');
    const retained = environment.rules.filter(element => element.dataset.kept === 'true');
    verifyVisible(environment.rules, retained);
    assert.equal(environment.ids.get('all').getAttribute('aria-pressed'), 'false');
    assert.equal(environment.ids.get('kept').getAttribute('aria-pressed'), 'true');
    if (retained.length) {
      const query = retained[0].textContent.trim().slice(0, 36).toUpperCase();
      setControl(environment, 'search', query, 'input');
      const expected = retained.filter(element => element.textContent.toLowerCase().includes(query.toLowerCase()));
      verifyVisible(environment.rules, expected);
      verifyCounter(environment, 'visible-rules', expected.length, environment.rules.length);
    }
    setControl(environment, 'search', absent, 'input');
    verifyVisible(environment.rules, []);
    assert.equal(environment.ids.get('no-rules').hidden, environment.rules.length === 0);
    environment.ids.get('all').fire('click');
    setControl(environment, 'search', '', 'input');
    verifyVisible(environment.rules, environment.rules);
  }

  if (environment.runs.length) {
    const target = environment.runs[Math.floor(environment.runs.length / 2)];
    const selected = { outcome: target.dataset.outcome, phase: target.dataset.phase, case: target.dataset.case };
    const expected = environment.runs.filter(element => Object.entries(selected).every(([key, value]) => !value || element.dataset[key] === value));
    for (const key of ['outcome', 'phase', 'case']) setControl(environment, `${key}-filter`, selected[key] || '', 'change');
    verifyVisible(environment.runs, expected);
    verifyCounter(environment, 'visible-runs', expected.length, environment.runs.length);
    setControl(environment, 'run-search', target.id.toUpperCase(), 'input');
    const searchable = element => [element.id, element.dataset.case, element.dataset.phase,
      element.dataset.outcome, element.textContent].join(' ').toLowerCase();
    verifyVisible(environment.runs, expected.filter(element => searchable(element).includes(target.id.toLowerCase())));
    setControl(environment, 'run-search', absent, 'input');
    verifyVisible(environment.runs, []);
    assert.equal(environment.ids.get('no-runs').hidden, false);
    environment.ids.get('reset-filters').fire('click');
    for (const id of ['run-search', 'outcome-filter', 'phase-filter', 'case-filter']) assert.equal(environment.ids.get(id).value, '');
    verifyVisible(environment.runs, environment.runs);
    assert.equal(environment.ids.get('no-runs').hidden, true);

    // Test the actual artifact ID, metadata and its actual closest section.
    setControl(environment, 'run-search', absent, 'input');
    environment.hash('#' + target.id);
    verifyVisible(environment.runs, environment.runs);
    assert.equal(target.open, true);
    assert.equal(target.scrolled, true);
    const section = target.closest('.section');
    const navigation = environment.navigation.find(link => link.getAttribute('href') === '#' + section.id);
    assert.equal(navigation?.getAttribute('aria-current'), 'location');

    const actualRunLink = environment.anchors.find(link => /^#run-\d+$/.test(link.getAttribute('href')));
    if (actualRunLink) {
      const href = actualRunLink.getAttribute('href');
      environment.hash(href);
      setControl(environment, 'run-search', absent, 'input');
      assert.equal(environment.ids.get(href.slice(1)).hidden, true);
      const event = actualRunLink.fire('click');
      assert.equal(event.defaultPrevented, false, 'Same-anchor handling must preserve native link behavior');
      verifyVisible(environment.runs, environment.runs);
      assert.equal(environment.ids.get(href.slice(1)).open, true);
      setControl(environment, 'run-search', absent, 'input');
      actualRunLink.fire('click', { ctrlKey: true });
      verifyVisible(environment.runs, []);
    }
    let unknown = 999999;
    while (environment.ids.has('run-' + unknown)) unknown++;
    setControl(environment, 'run-search', absent, 'input');
    environment.hash('#run-' + unknown);
    verifyVisible(environment.runs, []);
    environment.hash('#run-1%22%20onclick%3Dalert(1)');
    verifyVisible(environment.runs, []);
    environment.ids.get('reset-filters').fire('click');
  }

  if (environment.ids.has('language-select')) {
    setControl(environment, 'language-select', 'zh', 'change');
    assert.equal(environment.root.lang, 'zh-CN');
    verifyCounter(environment, 'visible-rules', environment.rules.length, environment.rules.length, 'zh');
    verifyCounter(environment, 'visible-runs', environment.runs.length, environment.runs.length, 'zh');
    assert.equal(environment.storage['rulebisect-language'], 'zh');
  }
  if (environment.ids.has('theme-toggle')) {
    environment.ids.get('theme-toggle').fire('click');
    assert.equal(environment.body.dataset.theme, 'dark');
    assert.equal(environment.ids.get('theme-toggle').getAttribute('aria-pressed'), 'true');
    environment.ids.get('theme-toggle').fire('click');
    assert.equal(environment.body.dataset.theme, 'light');
    assert.equal(environment.ids.get('theme-toggle').getAttribute('aria-pressed'), 'false');
  }
  for (const link of environment.navigation) {
    environment.hash(link.getAttribute('href'));
    assert.equal(link.getAttribute('aria-current'), 'location');
  }

  // Simulate genuinely optional components using the same report's real DOM.
  for (const options of [{ empty: true }, { withoutControls: true }, { empty: true, withoutControls: true }]) {
    const optional = mockDom(fixture, options);
    optional.start();
    verifyVisible(optional.rules, optional.rules);
    verifyVisible(optional.runs, optional.runs);
    if (options.empty) for (const id of ['no-rules', 'no-runs']) if (optional.ids.has(id)) assert.equal(optional.ids.get(id).hidden, true);
  }
  const blocked = mockDom(fixture, { blockedStorage: true, browserLanguage: 'zh-TW', dark: true });
  blocked.start();
  assert.equal(blocked.root.lang, 'zh-CN');
  assert.equal(blocked.body.dataset.theme, 'dark');
  if (blocked.ids.has('theme-toggle')) {
    blocked.ids.get('theme-toggle').fire('click');
    assert.equal(blocked.body.dataset.theme, 'light');
  }
  const automatic = mockDom(fixture, { preferences: { 'rulebisect-language': 'invalid', 'rulebisect-theme': 'invalid' } });
  automatic.start();
  automatic.media.change(true);
  assert.equal(automatic.body.dataset.theme, 'dark');

  // Add hostile plain text to a real card before controls cache its content.
  // The DOM mock forbids innerHTML and accepts only fixed selector strings.
  const hostile = mockDom(fixture);
  const card = hostile.rules[0] || hostile.runs[0];
  if (card) card.textContent += ' __hostile_text_probe__ </script><img onerror="alert(1)">';
  hostile.start();
  if (card) {
    const id = hostile.rules.length ? 'search' : 'run-search';
    setControl(hostile, id, '__hostile_text_probe__', 'input');
    verifyVisible(hostile.rules.length ? hostile.rules : hostile.runs, [card]);
  }
  return { rules: environment.rules.length, runs: environment.runs.length,
    sameAnchor: environment.anchors.some(link => /^#run-\d+$/.test(link.getAttribute('href'))) };
}

try {
  for (const html of args) {
    const result = checkReport(loadFixture(html));
    console.log(`Mock-DOM PASS ${path.basename(path.dirname(html))}/${path.basename(html)}: ${result.rules} rules, ${result.runs} runs, same-run anchors ${result.sameAnchor ? 'checked' : 'absent'}`);
  }
  console.log('Logic checks only. No browser, CSS/layout, accessibility-tree or visual acceptance performed.');
} catch (error) {
  console.error(`Mock-DOM FAIL: ${error.stack || error.message}`);
  process.exitCode = 1;
}
