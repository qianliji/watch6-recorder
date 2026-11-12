(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let state = {}, timer = null, dragging = false, hostVisible = true, bridgeReady = false;
  const recordViews = new Map();
  const activePlayback = () => ['playing', 'paused', 'preparing'].includes(state.playback);
  const number = value => Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
  const clamp = (value, max) => Math.min(number(value), Math.max(0, number(max)));
  const percent = (value, total) => total > 0 ? Math.min(100, Math.floor(clamp(value, total) / total * 100)) : 0;
  const clock = ms => {
    const seconds = Math.floor(number(ms) / 1000);
    return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  };
  const size = bytes => number(bytes) < 1048576 ? `${Math.round(number(bytes) / 1024)} KB` : `${(number(bytes) / 1048576).toFixed(1)} MB`;
  const recordingTime = row => row && row.sample_rate > 0 ? number(row.total) / row.sample_rate * 500 : 0;
  const date = row => {
    const value = new Date(number(row && row.created));
    if (!number(row && row.created) || Number.isNaN(value.getTime())) return {title: '手表录音', received: '接收时间未知'};
    const day = value.toLocaleDateString('zh-CN', {month: 'numeric', day: 'numeric'});
    const time = value.toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit', hour12: false});
    return {title: `${day} · ${time}`, received: `接收于 ${day}`};
  };

  function announce(message) { $('announcement').textContent = message; }
  function call(name, ...args) {
    try {
      if (!window.Recorder || typeof window.Recorder[name] !== 'function') throw new Error('bridge unavailable');
      window.Recorder[name](...args);
      return true;
    } catch (_) {
      announce('手机连接服务暂不可用，请在 Android 应用内重试。');
      return false;
    }
  }

  function showPanel(name) {
    const library = name === 'library';
    $('libraryPanel').hidden = !library;
    $('settingsPanel').hidden = library;
    $('libraryTab').classList.toggle('selected', library);
    $('settingsTab').classList.toggle('selected', !library);
    $('libraryTab').setAttribute('aria-selected', String(library));
    $('settingsTab').setAttribute('aria-selected', String(!library));
    // Connection updates never navigate or re-open help after the user dismisses it.
  }

  function connectionView() {
    if (!bridgeReady) return {title: '手机连接服务不可用', label: '未连接', hint: '请在 Android 应用中开启接收与回听。', action: '开启接收'};
    if (state.connected) return {title: '已连接手表', label: '已连接', hint: '在手表录音列表选择「发送到手机」。', action: '已连接'};
    const phase = state.connection_phase;
    if (phase === 'identity_required') return {title: '请安装手表连接组件', label: '待设置', hint: '首次安装配套 RPK 录音连接组件后重试；日常无需打开组件。', action: '重试连接', attention: true};
    if (phase === 'listener_ready') return {title: '接收已待命', label: '待命', hint: '请在手表录音列表选择「发送到手机」，收到录音通信后会确认连接。', action: '检查连接'};
    if (phase === 'authorization_required') return {title: '等待通信授权', label: '待授权', hint: '点「重新授权」，在运动健康中允许手表通信。', action: '重新授权', attention: true};
    if (phase === 'permission_required') return {title: '需要附近设备权限', label: '待授权', hint: '允许附近设备权限后，再重试连接。', action: '允许权限', attention: true, permission: true};
    if (phase === 'fitness_unavailable') return {title: '运动健康尚未就绪', label: '未连接', hint: '先打开小米运动健康，确认手表已配对连接。', action: '重试连接', attention: true};
    if (phase === 'watch_unavailable') return {title: '等待手表连接', label: '未连接', hint: '在运动健康中确认手表已连接，随后会自动重试。', action: '重试连接'};
    if (phase === 'authorizing') return {title: '请在运动健康中授权', label: '授权中', hint: '首次允许手表通信后返回此页，之后会自动恢复接收。', action: '正在授权', busy: true};
    if (phase === 'listener_pending') return {title: '接收通道仍在确认', label: '重连中', hint: '请确认运动健康已连接手表，稍候会自动重试；也可点「重试连接」。', action: '重试连接'};
    if (['connecting', 'checking_identity', 'subscribing'].includes(phase)) return {title: '正在连接手表', label: '连接中', hint: state.connection || '正在检查运动健康通信，请稍候。', action: '正在连接', busy: true};
    if (['retrying', 'service_disconnected'].includes(phase)) return {title: '连接暂时中断', label: '重连中', hint: '正在自动重试。请保持手表与运动健康连接。', action: '重试连接'};
    if (!state.enabled) return {title: '尚未开启接收', label: '未开启', hint: '连接手表后，从手表录音列表导出。', action: '开启接收'};
    return {title: state.connection || '正在等待手表', label: '未连接', hint: '请保持手表与运动健康连接，或查看连接步骤。', action: '重试连接'};
  }

  function renderConnection() {
    const view = connectionView();
    $('connectionCard').hidden = state.connected === true && Array.isArray(state.records) && state.records.length > 0;
    $('connection').textContent = $('settingsConnection').textContent = view.title;
    $('connectionHint').textContent = view.hint;
    $('settingsHint').textContent = view.hint;
    $('statusLabel').textContent = $('settingsBadge').textContent = view.label;
    $('dot').classList.toggle('ready', !!state.connected);
    $('dot').classList.toggle('attention-state', !!view.attention);
    $('attention').hidden = !view.attention;
    $('identityStep').classList.toggle('needs-attention', state.connection_phase === 'identity_required');
    for (const id of ['connect', 'settingsConnect']) {
      $(id).textContent = view.action;
      $(id).disabled = !bridgeReady || !!view.busy;
      $(id).hidden = !!state.connected;
    }
    $('disable').hidden = !state.enabled;
    $('disable').disabled = !bridgeReady;
    $('appSettings').hidden = !view.permission;
    for (const id of ['appSettings', 'permissionsHelp', 'openFitness', 'diagnostics', 'refresh']) $(id).disabled = !bridgeReady;
  }

  function renderTransfer() {
    const total = number(state.total), durable = clamp(state.durable, total), saved = state.transfer_state === 'saved';
    $('transfer').hidden = !(total > 0);
    $('retrySave').hidden = !(total>0 && durable===total && state.transfer_state==='error' && state.transfer_id);
    $('retrySave').disabled=!bridgeReady;
    if (!total) return;
    // The percentage follows the durable checkpoint, never received/queued bytes.
    const paused = state.transfer_state === 'paused' || (!state.connected && !saved);
    const verifying = !saved && durable === total;
    const failed = state.transfer_state === 'error';
    $('transferTitle').textContent = saved ? '完整录音已保存' : failed ? '保存未完成' : verifying ? '正在完成保存' : paused ? '接收已暂停，可续传' : '正在接收录音';
    $('transferMark').textContent = saved ? '✓' : paused ? 'Ⅱ' : '↓';
    $('percent').textContent = `${percent(durable, total)}%`;
    $('progress').max = total;
    $('progress').value = durable;
    $('transferBytes').textContent = `${size(durable)} / ${size(total)}`;
    $('transferStatus').textContent = saved ? '可回听与分享' : verifying ? '音频已收齐' : '接收进度已保存';
    $('transferHint').textContent = saved ? '可在下方播放录音，也可以保存到下载或分享。' : failed && verifying ? '音频仍在手机。点「完成保存」重试，无需重新传输。' : verifying ? '正在校验完整录音，稍后就能播放。' : paused ? '在手表选择同一条录音重新导出，即可继续接收。' : '接收中断后可继续导出，手表原音保留。';
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function actionButton(label, symbol, action) {
    const button = element('button', 'text');
    const icon = element('span', '', symbol);
    icon.setAttribute('aria-hidden', 'true');
    button.append(icon, element('span', '', label));
    button.onclick = action;
    return button;
  }
  function record(row) {
    const complete = row.complete === true, stamp = date(row);
    let finishAction = null;
    const article = element('article', `glass record${complete ? '' : ' record-incomplete'}`);
    article.dataset.id = row.id;
    const main = element('div', 'record-main');
    const play = element(complete ? 'button' : 'span', 'record-play');
    const symbol = element('span', 'play-symbol', complete ? '▶' : '↓');
    symbol.setAttribute('aria-hidden', 'true');
    play.append(symbol);
    const copy = element('div', 'record-copy');
    copy.append(element('p', 'title', stamp.title));
    const meta = element('p', 'meta');
    meta.append(element('span', '', clock(recordingTime(row))), element('span', '', complete ? size(row.total) : `${size(row.bytes)} / ${size(row.total)}`));
    copy.append(meta);
    const badge = element('span', 'record-badge', complete ? '完整原音' : `${percent(row.bytes, row.total)}%`);
    main.append(play, copy, badge);
    article.append(main);
    if (complete) {
      play.setAttribute('aria-label', `回听 ${stamp.title}`);
      play.onclick = () => {
        if (state.playing_id === row.id && state.playback === 'playing') call('pause');
        else if (state.playing_id === row.id && state.playback === 'paused') call('resume');
        else call('play', row.id);
      };
      const actions = element('div', 'record-actions');
      actions.append(element('span', 'record-date', stamp.received), actionButton('保存', '↓', () => call('download', row.id)), actionButton('分享', '↗', () => call('share', row.id)));
      article.append(actions);
    } else {
      play.setAttribute('aria-hidden', 'true');
      const progress = element('progress');
      progress.max = number(row.total) || 1;
      progress.value = clamp(row.bytes, row.total);
      progress.setAttribute('aria-label', '这条录音已安全保存的接收进度');
      article.append(progress, element('p', 'fine-print', number(row.bytes) === number(row.total) ? '音频已收齐，完成保存后即可播放。' : '尚未完整接收 · 回到手表发送同一条录音即可继续。'));
      if (number(row.total) > 0 && number(row.bytes) === number(row.total)) {
        const actions = element('div', 'record-actions');
        const finish = actionButton('完成保存', '✓', () => call('finish', row.id));
        finishAction = finish;
        finish.disabled = !bridgeReady || (state.transfer_id === row.id && state.transfer_state === 'saving');
        actions.append(finish);article.append(actions);
      }
    }
    recordViews.set(row.id, {article, play, symbol, badge, complete, stamp, finishAction});
    return article;
  }

  function renderRecords() {
    const rows = Array.isArray(state.records) ? state.records : [];
    const complete = rows.filter(row => row.complete === true);
    const waiting = rows.filter(row => row.complete !== true && number(row.total)>0 && number(row.bytes) === number(row.total)).length;
    $('recordCount').textContent = String(complete.length);
    $('librarySummary').textContent = rows.length ? `${complete.length} 条完整录音${rows.length > complete.length ? `${waiting ? ` · ${waiting} 条待保存` : ''}${rows.length-complete.length-waiting ? ` · ${rows.length-complete.length-waiting} 条待续传` : ''}` : ` · ${clock(complete.reduce((total, row) => total + recordingTime(row), 0))}`}` : '手表原音，在这里收藏。';
    const key = JSON.stringify(rows);
    if ($('records').dataset.key !== key) {
      recordViews.clear();
      $('records').replaceChildren(...rows.map(record));
      $('records').dataset.key = key;
    }
    for (const [id, view] of recordViews) {
      if (!view.complete) {
        if(view.finishAction) {
          const saving=state.transfer_id===id && state.transfer_state==='saving';
          view.finishAction.disabled=!bridgeReady || saving;
          view.finishAction.setAttribute('aria-label',saving?'正在保存录音':'完成保存');
        }
        continue;
      }
      const current = state.playing_id === id && activePlayback();
      view.article.classList.toggle('is-playing', current);
      view.play.classList.toggle('playing', current && state.playback === 'playing');
      view.play.disabled = !bridgeReady || (current && state.playback === 'preparing');
      view.symbol.textContent = current && state.playback === 'playing' ? 'Ⅱ' : current && state.playback === 'preparing' ? '…' : '▶';
      view.badge.textContent = current ? state.playback === 'playing' ? '回听中' : state.playback === 'paused' ? '已暂停' : '正在打开' : '完整原音';
      view.play.setAttribute('aria-label', `${current && state.playback === 'playing' ? '暂停' : current && state.playback === 'paused' ? '继续回听' : '回听'} ${view.stamp.title}`);
    }
    $('empty').hidden = rows.length > 0;
  }

  function updateSeek(value, duration) {
    const position = clamp(value, duration);
    $('seek').style.setProperty('--played', `${duration > 0 ? position / duration * 100 : 0}%`);
    $('seek').setAttribute('aria-valuetext', `${clock(position)}，共 ${clock(duration)}`);
    $('elapsed').textContent = clock(position);
  }
  function renderPlayer() {
    const active = activePlayback(), preparing = state.playback === 'preparing';
    $('player').hidden = !active;
    document.body.classList.toggle('has-player', active);
    if (!active) { dragging = false; return; }
    const row = (state.records || []).find(item => item.id === state.playing_id);
    $('playerTitle').textContent = row ? date(row).title : '手表录音';
    $('playerState').textContent = preparing ? '正在验证并打开完整录音…' : state.playback === 'paused' ? '已暂停 · 拖动进度可继续回听' : '正在回听 · 完整原音';
    const paused = state.playback === 'paused';
    $('toggleIcon').textContent = preparing ? '…' : paused ? '▶' : 'Ⅱ';
    $('toggleLabel').textContent = paused ? '继续回听' : '暂停';
    $('toggle').setAttribute('aria-label', preparing ? '正在打开录音' : paused ? '继续回听' : '暂停');
    $('toggle').disabled = preparing || !bridgeReady;
    $('seek').disabled = preparing || !bridgeReady || !number(state.duration);
    $('duration').textContent = clock(state.duration);
    if (!dragging) {
      $('seek').max = number(state.duration) || 1;
      $('seek').value = clamp(state.position, state.duration);
      updateSeek(state.position, number(state.duration));
    }
  }

  function syncTimer() {
    const needed = bridgeReady && hostVisible && !document.hidden && state.playback === 'playing';
    if (!needed && timer !== null) { clearTimeout(timer); timer = null; }
    if (needed && timer === null) timer = setTimeout(() => { timer = null; window.refresh(); }, 500);
  }
  window.refresh = () => {
    try {
      if (!window.Recorder || typeof window.Recorder.snapshot !== 'function') throw new Error('bridge unavailable');
      const next = JSON.parse(window.Recorder.snapshot());
      if (!next || typeof next !== 'object' || Array.isArray(next)) throw new Error('invalid snapshot');
      state = next;
      bridgeReady = true;
    } catch (_) { bridgeReady = false; }
    renderConnection();
    renderTransfer();
    renderRecords();
    $('error').hidden = !state.error;
    $('error').textContent = state.error || '';
    renderPlayer();
    syncTimer();
  };
  // Covers WebViews whose document.hidden is delayed after Activity.onPause.
  window.setHostVisible = visible => {
    hostVisible = visible === true;
    if (hostVisible) window.refresh(); else syncTimer();
  };

  $('libraryTab').onclick = () => showPanel('library');
  $('settingsTab').onclick = $('connectionShortcut').onclick = $('connectionDetails').onclick = () => showPanel('settings');
  $('emptySetup').onclick = () => {showPanel('settings');$('setup').open = true;};
  $('connect').onclick = $('settingsConnect').onclick = () => call('connect');
  $('disable').onclick = () => call('disable');
  $('retrySave').onclick = () => call('finish',state.transfer_id);
  $('appSettings').onclick = $('permissionsHelp').onclick = () => call('openSettings');
  $('openFitness').onclick = () => call('openFitness');
  $('diagnostics').onclick = () => call('diagnostics');
  $('refresh').onclick = () => { call('refresh'); window.refresh(); announce('正在刷新录音库。'); };
  $('stop').onclick = () => call('stop');
  $('toggle').onclick = () => call(state.playback === 'paused' ? 'resume' : 'pause');
  $('seek').onpointerdown = () => { dragging = true; };
  $('seek').oninput = () => { dragging = true; updateSeek($('seek').value, number(state.duration)); };
  $('seek').onchange = () => { call('seek', Math.round(clamp($('seek').value, state.duration))); dragging = false; };
  $('seek').onpointercancel = $('seek').onblur = () => { dragging = false; renderPlayer(); };
  document.addEventListener('visibilitychange', () => { if (document.hidden) syncTimer(); else window.refresh(); });
  window.refresh();
})();
