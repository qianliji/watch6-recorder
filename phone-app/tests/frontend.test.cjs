'use strict';
// Deterministic DOM/bridge boundary tests. No browser, device, microphone or network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assets = path.join(__dirname, '..', 'assets');
const html = fs.readFileSync(path.join(assets, 'index.html'), 'utf8');
const source = fs.readFileSync(path.join(assets, 'app.js'), 'utf8');
let assertions = 0;
function check(actual, expected, message) { assertions++; assert.deepEqual(actual, expected, message); }

class Element {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {}; this.dataset = {};
    this.className = ''; this.hidden = false; this.disabled = false; this.value = 0; this.max = 1;
    this._text = ''; this.style = {values: {}, setProperty(name, value) { this.values[name] = value; }};
    this.classList = {
      toggle: (name, force) => {
        const classes = new Set(this.className.split(/\s+/).filter(Boolean));
        const add = force === undefined ? !classes.has(name) : force;
        if (add) classes.add(name); else classes.delete(name);
        this.className = [...classes].join(' '); return add;
      },
      contains: name => this.className.split(/\s+/).includes(name)
    };
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name]; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this._text = ''; }
  click() { if (!this.disabled && this.onclick) this.onclick(); }
}
function boot(initial, withBridge = true) {
  const elements = new Map();
  for (const match of html.matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    const node = new Element(match[1]);
    node.hidden = /\bhidden\b/.test(match[2]);
    node.className = /\bclass="([^"]*)"/.exec(match[2])?.[1] || '';
    elements.set(match[3], node);
  }
  const events = {}, tasks = new Map(), calls = [];
  let state = initial, serial = 0, snapshots = 0;
  const document = {
    hidden: false, body: new Element('body'),
    getElementById: id => { assert(elements.has(id), `Missing real HTML element #${id}`); return elements.get(id); },
    createElement: tag => new Element(tag),
    addEventListener: (name, callback) => { events[name] = callback; }
  };
  const recorder = {
    snapshot() { snapshots++; if (state instanceof Error) throw state; return JSON.stringify(state); }
  };
  for (const name of ['connect', 'disable', 'refresh', 'play', 'pause', 'resume', 'stop', 'seek', 'share', 'download', 'openSettings', 'openFitness', 'diagnostics', 'finish']) recorder[name] = (...args) => calls.push([name, ...args]);
  const window = withBridge ? {Recorder: recorder} : {};
  vm.runInNewContext(source, {document, window, Date, Map, Number, String, Math, JSON, Error,
    setTimeout(callback, delay) { check(delay, 500, 'only playback schedules a 500ms timer'); const id = ++serial; tasks.set(id, callback); return id; },
    clearTimeout(id) { tasks.delete(id); }
  }, {filename: 'app.js'});
  return {
    $: id => elements.get(id), window, document, calls, tasks,
    get snapshots() { return snapshots; },
    update(next) { state = {...state, ...next}; window.refresh(); },
    fail() { state = new Error('lost bridge'); window.refresh(); },
    visible(visible) { document.hidden = !visible; events.visibilitychange(); },
    tick() { const [id, callback] = tasks.entries().next().value; tasks.delete(id); callback(); }
  };
}
const ready = {connection: '运动健康通道已就绪', connected: true, enabled: true, connection_phase: 'ready', playback: 'idle', records: []};
const full = {id: '0123456789abcdef', created: 1794110400000, complete: true, total: 1920000, bytes: 1920000, sample_rate: 16000};
const partial = {id: 'fedcba9876543210', created: 1794110460000, complete: false, total: 3200000, bytes: 960000, sample_rate: 16000};

// Standalone previews contain no fabricated connection or audio. Fixtures must be external.
{
  const app = boot({}, false);
  check(app.$('connection').textContent, '手机连接服务不可用');
  check(app.$('connect').disabled, true);
  check(app.$('empty').hidden, false);
  check(app.tasks.size, 0);
  check(app.calls.length, 0);
}

// Blocked identity, authorization and permission have honest, actionable states.
{
  const app = boot({...ready, connected: false, connection_phase: 'identity_required'});
  check(app.$('connection').textContent, '请安装手表连接组件');
  check(app.$('connectionHint').textContent.includes('日常无需打开'), true);
  check(app.$('settingsPanel').hidden, true, 'identity does not force-open setup');
  app.$('settingsTab').click();
  check(app.$('settingsPanel').hidden, false);
  app.$('help').open = false;
  app.$('libraryTab').click();
  for (let index = 0; index < 5; index++) app.window.refresh();
  check(app.$('settingsPanel').hidden, true, 'refresh preserves user navigation');
  check(app.$('help').open, false, 'refresh does not re-open help');
  app.$('connect').click(); check(app.calls.pop(), ['connect']);
  app.update({connection_phase: 'authorization_required'});
  check(app.$('connect').textContent, '重新授权');
  app.$('settingsConnect').click(); check(app.calls.pop(), ['connect']);
  app.update({connection_phase: 'permission_required'});
  check(app.$('appSettings').hidden, false);
  app.$('appSettings').click(); check(app.calls.pop(), ['openSettings']);
  app.$('openFitness').click(); check(app.calls.pop(), ['openFitness']);
  app.$('disable').click(); check(app.calls.pop(), ['disable']);
  app.$('diagnostics').click(); check(app.calls.pop(), ['diagnostics']);
  check(html.includes('配套 RPK「录音连接组件」'), true, 'first installation names the supported connection component');
  check(html.includes('日常无需打开'), true, 'installed identity needs no routine launch');
  check(app.tasks.size, 0, 'idle connection updates do not poll');
}

// Listening permits first export without claiming a verified watch handshake.
{
  const app = boot({...ready, connected: false, connection_phase: 'listener_ready'});
  check(app.$('connection').textContent, '接收已待命');
  check(app.$('statusLabel').textContent, '待命');
  check(app.$('dot').classList.contains('ready'), false);
  check(app.$('connectionHint').textContent.includes('发送到手机'), true);
  check(app.$('connect').disabled, false);
  app.update({connected: true, connection_phase: 'ready'});
  check(app.$('connection').textContent, '已连接手表');
  check(app.$('connect').hidden, true);
  app.update({connected: false, connection_phase: 'listener_pending'});
  check(app.$('connect').disabled, false, 'timed-out listener offers an actionable retry');
  app.$('connect').click(); check(app.calls.pop(), ['connect']);
  check(app.tasks.size, 0, 'passive listening adds no frontend polling');
}

// Only durable checkpoints advance transfer progress, and incomplete rows have no audio actions.
{
  const app = boot({...ready, records: [full, partial], transfer_state: 'receiving', total: partial.total, durable: partial.bytes, received: partial.total});
  check(app.$('percent').textContent, '30%');
  check(app.$('progress').value, partial.bytes);
  check(app.$('recordCount').textContent, '1');
  check(app.$('librarySummary').textContent, '1 条完整录音 · 1 条待续传');
  const [complete, incomplete] = app.$('records').children;
  check(incomplete.children.flatMap(child => child.children).filter(child => child.tagName === 'BUTTON').length, 0);
  check(incomplete.textContent.includes('尚未完整接收'), true);
  const play = complete.children[0].children[0];
  play.click(); check(app.calls.pop(), ['play', full.id]);
  complete.children[1].children[1].click(); check(app.calls.pop(), ['download', full.id]);
  complete.children[1].children[2].click(); check(app.calls.pop(), ['share', full.id]);
  app.update({durable: partial.total, transfer_state: 'receiving'});
  check(app.$('transferTitle').textContent, '正在完成保存');
  check(app.$('records').children[1], incomplete, 'unrelated transfer state preserves row/focus');
  app.update({durable: partial.bytes, connected: false, transfer_state: 'paused'});
  check(app.$('transferTitle').textContent, '接收已暂停，可续传');
  app.update({durable: partial.total, connected: true, transfer_state: 'saved'});
  check(app.$('transferTitle').textContent, '完整录音已保存');
}

// Fully received bytes stay distinct from a finalized, playable file.
{
 const row = {...partial, bytes: partial.total};
 const app = boot({...ready, records: [row], transfer_id: row.id, transfer_state: 'error', total: row.total, durable: row.total});
 check(app.$('transferTitle').textContent, '保存未完成');
 check(app.$('transferStatus').textContent, '音频已收齐');
 check(app.$('retrySave').hidden,false);app.$('retrySave').click();check(app.calls.pop(),['finish',row.id]);
 check(app.$('librarySummary').textContent.includes('待保存'), true);
 const card=app.$('records').children[0];
 const actions=card.children[card.children.length-1];
 actions.children[0].click();check(app.calls.pop(), ['finish', row.id]);
 app.update({transfer_id:row.id,transfer_state:'saving'});check(actions.children[0].disabled,true,'local finalization disables repeated taps');
 app.update({transfer_state:'error'});check(actions.children[0].disabled,false,'failed save is retryable without opening watch');
 check(app.$('recordCount').textContent, '0', 'received bytes are not a saved recording');
 app.update({records:[{...row,complete:true}],transfer_state:'saved'});
 check(app.$('recordCount').textContent, '1');
 check(app.$('connectionCard').hidden, true, 'connected library focuses on recordings');
}

// Playback/scrubbing retains input while dragging and sends exactly one bounded seek.
{
  const app = boot({...ready, records: [full], playback: 'playing', playing_id: full.id, position: 12000, duration: 60000});
  check(app.$('player').hidden, false);
  check(app.$('elapsed').textContent, '00:12');
  check(app.tasks.size, 1);
  const row = app.$('records').children[0];
  row.children[0].children[0].click(); check(app.calls.pop(), ['pause']);
  app.$('seek').onpointerdown(); app.$('seek').value = 45000; app.$('seek').oninput();
  const before = app.calls.length;
  app.update({position: 14000});
  check(app.$('seek').value, 45000, 'refresh cannot fight scrubbing');
  check(app.$('elapsed').textContent, '00:45');
  check(app.calls.length, before, 'input does not flood native seek calls');
  app.$('seek').onchange(); check(app.calls.pop(), ['seek', 45000]);
  app.$('seek').value = 90000; app.$('seek').onchange(); check(app.calls.pop(), ['seek', 60000]);
  app.update({playback: 'paused', position: 45000});
  check(app.tasks.size, 0, 'paused playback has no polling');
  check(app.$('toggle').getAttribute('aria-label'), '继续回听');
  app.$('toggle').click(); check(app.calls.pop(), ['resume']);
  app.$('stop').click(); check(app.calls.pop(), ['stop']);
  app.update({playback: 'preparing'});
  check(app.$('seek').disabled, true);
  check(app.$('toggle').disabled, true);
  app.update({playback: 'idle'});
  check(app.$('player').hidden, true);
}

// Background/native pause cannot recreate polling through a late service refresh.
{
  const app = boot({...ready, records: [full], playback: 'playing', playing_id: full.id, position: 12000, duration: 60000});
  app.visible(false); check(app.tasks.size, 0);
  app.update({position: 13000}); check(app.tasks.size, 0, 'late hidden refresh stays asleep');
  app.visible(true); check(app.tasks.size, 1);
  app.window.setHostVisible(false); check(app.tasks.size, 0);
  app.update({position: 14000}); check(app.tasks.size, 0, 'late native-paused refresh stays asleep');
  app.window.setHostVisible(true); check(app.tasks.size, 1);
  const before = app.snapshots; app.tick();
  check(app.snapshots, before + 1); check(app.tasks.size, 1, 'single timer recurs while visible and playing');
  for (let index = 0; index < 3; index++) app.window.refresh();
  check(app.tasks.size, 1, 'native refresh cannot duplicate playback timers');
  app.fail(); check(app.tasks.size, 0, 'broken bridge does not spin');
}

console.log(JSON.stringify({passed: true, assertions, physical_verified: false, scope: 'production phone assets in deterministic DOM and native bridge boundary; no browser or device'}));
