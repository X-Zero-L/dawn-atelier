'use strict';

(() => {
  const element = id => document.getElementById(id);
  const controls = [...document.querySelectorAll('[data-action]')];
  const gamePath = element('game-path');
  const frame = element('workbench-frame');
  const state = {
    version: '2.4.1', game_dir: '', detected: false, prepared: false,
    data_dir: '', busy: false,
    progress: {percent: 0, stage: 'idle', message: '选择游戏，开始准备', detail: ''},
    error: '', mode: null, active_url: null, last_prepared: null,
  };
  let api = null;
  let pendingRequest = false;
  let pollTimer = null;
  let polling = false;
  let connected = false;
  let showcase = false;
  let pathDirty = false;
  let localError = '';
  let dismissedError = '';
  let autoLaunchIntent = null;
  let showAfterLaunch = false;
  let assignedUrl = '';
  let assignedMode = null;
  let currentView = 'home';
  let toastTimer = null;
  let frameTimer = null;
  let stateRevision = 0;

  const isBusy = () => state.busy || pendingRequest;
  const setText = (id, value) => { element(id).textContent = String(value ?? ''); };
  const normalizePath = value => String(value || '').trim().replace(/\/+$/, '').replace(/\\+$/, '').toLowerCase();

  function showToast(message) {
    clearTimeout(toastTimer);
    setText('toast', message);
    element('toast').hidden = false;
    toastTimer = setTimeout(() => { element('toast').hidden = true; }, 3000);
  }

  function reportError(error) {
    autoLaunchIntent = null;
    showAfterLaunch = false;
    localError = error instanceof Error ? error.message : String(error || '操作未完成，请重试。');
    dismissedError = '';
    if (currentView === 'workbench') showView('home');
    render();
  }

  function showView(view) {
    currentView = view === 'workbench' && state.active_url ? 'workbench' : 'home';
    element('home-view').hidden = currentView !== 'home';
    element('workbench-view').hidden = currentView !== 'workbench';
    // The iframe stays mounted. Opening settings must preserve its draft and UI.
    document.body.classList.toggle('in-workbench', currentView === 'workbench');
    document.title = currentView === 'workbench'
      ? `黎明工坊 · ${state.mode === 'demo' ? '演示模式' : '黎明门前的吹笛人'}`
      : '黎明工坊 · 黎明门前的吹笛人';
  }

  function trustedWorkbenchUrl(value) {
    if (!value) return '';
    try {
      const url = new URL(value);
      return url.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) ? url.href : '';
    } catch { return ''; }
  }

  function updateFrame() {
    const url = trustedWorkbenchUrl(state.active_url);
    if (!url) {
      if (state.active_url) localError = '工作台地址无效，请重新启动工坊。';
      if (currentView === 'workbench') showView('home');
      if (!state.active_url) assignedUrl = '';
      return;
    }
    if (assignedUrl !== url || assignedMode !== state.mode) {
      assignedUrl = url;
      assignedMode = state.mode;
      showAfterLaunch = true;
      element('frame-loading').hidden = false;
      element('frame-loading').querySelector('p').textContent = '载入本地存档与物品资料…';
      frame.src = url;
      clearTimeout(frameTimer);
      frameTimer = setTimeout(() => {
        if (!element('frame-loading').hidden) {
          const message = element('frame-loading').querySelector('p');
          message.textContent = '载入时间较长，可返回设置查看运行日志。';
        }
      }, 20000);
    }
    if (showAfterLaunch && !isBusy()) {
      showAfterLaunch = false;
      showView('workbench');
    }
  }

  function progressStep(percent) {
    const stage = String(state.progress?.stage || '').toLowerCase();
    if (/launch|serve|ready|running/.test(stage) || percent >= 96) return 2;
    if (/catalog|art|index|整理|图鉴/.test(stage) || percent >= 35) return 1;
    return 0;
  }

  function render() {
    const busy = isBusy();
    const selected = Boolean(state.game_dir);
    const active = Boolean(trustedWorkbenchUrl(state.active_url));
    const error = localError || state.error;
    document.body.classList.toggle('preparing', state.busy);
    element('connection-dot').className = `status-dot${connected ? '' : api ? ' disconnected' : ' connecting'}`;
    setText('connection-label', showcase ? '本地桌面应用' : connected ? '本地桌面服务已连接' : api ? '连接中断，正在重试' : '正在连接桌面服务');
    document.querySelectorAll('[data-version]').forEach(node => { node.textContent = `v${state.version || '2.4.1'}`; });

    if (!pathDirty && document.activeElement !== gamePath) gamePath.value = state.game_dir || '';
    gamePath.disabled = busy || showcase || !api;
    element('save-path-button').hidden = !pathDirty;
    element('selection-badge').classList.toggle('selected', selected);
    setText('selection-badge', state.prepared ? '资料已就绪' : selected ? state.detected ? '已找到游戏' : '已选择目录' : '等待选择');
    setText('path-hint', pathDirty ? '路径已更改，点击“使用此目录”保存。' : state.detected ? '已找到 ThePiper.exe，安装目录已记住。' : selected ? '已保存安装目录，下次打开可继续使用。' : '可选择文件夹，也可以直接粘贴安装路径。');
    setText('prepare-note-title', state.prepared ? '本地资料已就绪' : '首次使用，自动准备本地资料');
    setText('prepare-note-detail', state.prepared && state.compatibility ? `${state.compatibility.package_version} · ${state.compatibility.message}。游戏更新后重新准备即可。` : state.prepared ? '直接打开工坊即可开始编辑。游戏更新后，可重新准备资料。' : '自动核对存档结构与资源配置。兼容补丁可直接准备，完成后进入工作台。');
    setText('start-label', state.busy ? state.mode === 'demo' ? '正在打开演示' : autoLaunchIntent ? '正在准备，完成后自动打开' : '正在处理，请稍候' : active && state.mode === 'game' && !pathDirty ? '返回我的工坊' : state.prepared && !pathDirty ? '打开我的工坊' : '准备并打开工坊');
    setText('demo-label', active && state.mode === 'demo' ? '返回演示' : '先体验演示');
    element('start-arrow').toggleAttribute('hidden', busy);
    element('start-spinner').hidden = !busy;
    element('reprepare-button').hidden = !state.prepared;
    element('resume-card').hidden = !active || state.busy;
    setText('resume-title', state.mode === 'demo' ? '演示工坊正在运行' : '你的工坊正在运行');
    setText('shell-mode', state.mode === 'demo' ? '演示模式' : '本地存档');

    const percent = Math.max(0, Math.min(100, Number(state.progress?.percent) || 0));
    element('progress-card').hidden = !state.busy;
    element('progress-track').setAttribute('aria-valuenow', String(percent));
    element('progress-fill').style.width = `${percent}%`;
    element('progress-percent').replaceChildren(document.createTextNode(String(Math.round(percent))));
    const unit = document.createElement('small');
    unit.textContent = '%';
    element('progress-percent').append(unit);
    setText('progress-heading', autoLaunchIntent ? '正在准备你的工坊' : state.mode === 'demo' ? '正在打开演示工坊' : showAfterLaunch || /launch|serve/.test(state.progress?.stage || '') ? '正在打开你的工坊' : '正在准备本地资料');
    setText('progress-message', state.progress?.message || '正在处理，请稍候…');
    setText('progress-detail', state.progress?.detail || '');
    element('progress-detail').hidden = !state.progress?.detail;
    const step = progressStep(percent);
    ['step-read', 'step-prepare', 'step-launch'].forEach((id, index) => {
      element(id).className = index < step ? 'done' : index === step ? 'active' : '';
    });

    element('error-card').hidden = !error || error === dismissedError;
    setText('error-heading', api ? '暂时没能完成' : '请从桌面应用打开工坊');
    setText('error-message', error);
    controls.forEach(button => {
      const action = button.dataset.action;
      const navigation = ['settings', 'resume', 'dismiss-error'].includes(action);
      const quickAction = ['data', 'backups', 'exports', 'logs', 'help', 'browser'].includes(action);
      button.disabled = showcase || (!api && !navigation) || (!quickAction && !navigation && busy);
      if (action === 'start') button.disabled ||= !selected && !gamePath.value.trim();
      if (action === 'prepare') button.disabled ||= !selected;
      if (action === 'save-path') button.disabled ||= !gamePath.value.trim();
      if (action === 'resume' || action === 'browser') button.disabled ||= !active;
    });
    updateFrame();
  }

  function acceptState(next, options = {}) {
    if (!next || typeof next !== 'object' || !('busy' in next)) throw new Error('桌面服务返回了无效状态，请重试。');
    Object.assign(state, next);
    connected = true;
    if (options.resetPath) {
      pathDirty = false;
      gamePath.value = state.game_dir || '';
    }
    if (state.error) {
      autoLaunchIntent = null;
      showAfterLaunch = false;
    }
    if (autoLaunchIntent && normalizePath(state.game_dir) !== autoLaunchIntent) autoLaunchIntent = null;
    document.body.dataset.ready = 'true';
    render();
  }

  function schedulePoll() {
    clearTimeout(pollTimer);
    if (!api || showcase) return;
    pollTimer = setTimeout(poll, state.busy || autoLaunchIntent || showAfterLaunch ? 800 : 2000);
  }

  async function poll() {
    if (polling || pendingRequest || !api) { schedulePoll(); return; }
    polling = true;
    const revision = stateRevision;
    try {
      const next = await api.status();
      if (revision === stateRevision) acceptState(next);
    } catch (error) {
      connected = false;
      if (!document.body.dataset.ready || document.body.dataset.ready === 'false') reportError(error);
      else render();
    } finally {
      polling = false;
      maybeAutoLaunch();
      schedulePoll();
    }
  }

  async function request(method, args = [], options = {}) {
    if (!api || showcase || pendingRequest) return null;
    pendingRequest = true;
    stateRevision += 1;
    localError = '';
    dismissedError = '';
    clearTimeout(pollTimer);
    render();
    try {
      const result = await api[method](...args);
      if (options.state !== false) acceptState(result, options);
      return result;
    } catch (error) {
      reportError(error);
      return null;
    } finally {
      pendingRequest = false;
      render();
      maybeAutoLaunch();
      schedulePoll();
    }
  }

  function confirmSwitch(message) {
    if (!state.active_url) return true;
    return window.confirm(`${message}\n\n当前工坊会停止，已保存的草稿会保留。游戏存档与演示存档分别保存。`);
  }

  async function savePath() {
    const value = gamePath.value.trim();
    if (!value) { reportError('请先选择游戏目录，或粘贴安装路径。'); gamePath.focus(); return false; }
    if (!pathDirty && normalizePath(value) === normalizePath(state.game_dir)) return true;
    if (!confirmSwitch('更换游戏目录后，需要重新准备本地资料。')) return false;
    autoLaunchIntent = null;
    const result = await request('set_game', [value], {resetPath: true});
    return Boolean(result && !result.error && result.game_dir);
  }

  async function launch(mode, alreadyConfirmed = false) {
    if (state.active_url && state.mode === mode) { showView('workbench'); return; }
    if (!alreadyConfirmed && !confirmSwitch(mode === 'demo' ? '即将切换到示例存档演示。' : '即将切换到你的游戏存档。')) return;
    autoLaunchIntent = null;
    showAfterLaunch = true;
    showView('home');
    const result = await request('launch', [mode]);
    if (!result || result.error) showAfterLaunch = false;
  }

  async function start() {
    if (isBusy()) return;
    if (pathDirty && !await savePath()) return;
    if (!state.game_dir) { gamePath.focus(); return; }
    if (state.prepared) { await launch('game'); return; }
    if (!confirmSwitch('即将准备所选游戏的本地资料，完成后自动打开工坊。')) return;
    autoLaunchIntent = normalizePath(state.game_dir);
    showView('home');
    const result = await request('prepare');
    if (!result || result.error) autoLaunchIntent = null;
  }

  function maybeAutoLaunch() {
    if (!autoLaunchIntent || pendingRequest || state.busy || polling) return;
    const shouldLaunch = state.prepared && !state.error && normalizePath(state.game_dir) === autoLaunchIntent;
    autoLaunchIntent = null;
    if (shouldLaunch) void launch('game', true);
  }

  async function perform(action) {
    if (showcase) return;
    if (action === 'settings') { showView('home'); return; }
    if (action === 'resume') { showView('workbench'); return; }
    if (action === 'dismiss-error') { dismissedError = localError || state.error; render(); return; }
    if (!api) return;
    if (action === 'start') { await start(); return; }
    if (action === 'demo') { if (!isBusy()) await launch('demo'); return; }
    if (action === 'save-path') { if (!isBusy()) await savePath(); return; }
    if (action === 'choose') {
      if (isBusy() || !confirmSwitch('更换游戏目录后，需要重新准备本地资料。')) return;
      autoLaunchIntent = null;
      await request('choose_game', [], {resetPath: true});
      return;
    }
    if (action === 'prepare') {
      if (isBusy() || !confirmSwitch('即将重新读取游戏资料并更新本地图鉴。')) return;
      autoLaunchIntent = null;
      showAfterLaunch = false;
      await request('prepare');
      return;
    }
    if (['data', 'backups', 'exports', 'logs'].includes(action)) {
      const result = await request('open_folder', [action], {state: false});
      if (result?.ok) showToast('已在资源管理器中打开');
      return;
    }
    if (action === 'browser') { await request('open_browser', [], {state: false}); return; }
    if (action === 'help') await request('open_help', [], {state: false});
  }

  controls.forEach(button => button.addEventListener('click', () => { void perform(button.dataset.action); }));
  gamePath.addEventListener('input', () => {
    pathDirty = normalizePath(gamePath.value) !== normalizePath(state.game_dir);
    render();
  });
  gamePath.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !isBusy()) { event.preventDefault(); void savePath(); }
  });
  frame.addEventListener('load', () => {
    if (!assignedUrl) return;
    clearTimeout(frameTimer);
    element('frame-loading').hidden = true;
  });

  async function connectBridge() {
    if (api || showcase || !window.pywebview?.api) return;
    api = window.pywebview.api;
    localError = '';
    dismissedError = '';
    await poll();
  }

  async function init() {
    const scene = new URLSearchParams(location.search).get('showcase');
    if (['welcome', 'preparing'].includes(scene) && ['http:', 'https:'].includes(location.protocol)) {
      try {
        const response = await fetch('/api/health', {cache: 'no-store'});
        const health = response.ok ? await response.json() : null;
        if (health?.demo === true) {
          showcase = true;
          connected = true;
          document.body.classList.add('showcase');
          if (scene === 'preparing') autoLaunchIntent = normalizePath('D:\\Games\\The Piper Of Dawn');
          acceptState({
            version: '2.4.1', game_dir: 'D:\\Games\\The Piper Of Dawn', detected: true,
            prepared: false, data_dir: '', busy: scene === 'preparing',
            progress: scene === 'preparing'
              ? {percent: 68, stage: 'catalogue', message: '正在整理物品、炼金与角色资料', detail: '完成后将自动打开工坊。'}
              : {percent: 0, stage: 'idle', message: '选择游戏，开始准备', detail: ''},
            error: '', mode: null, active_url: null, last_prepared: null,
          }, {resetPath: true});
          return;
        }
      } catch { /* A preview requires confirmed synthetic demo data. */ }
    }
    window.addEventListener('pywebviewready', connectBridge);
    await connectBridge();
    if (!api) {
      render();
      setTimeout(() => {
        if (!api) reportError('双击 DawnAtelier.exe 启动。桌面窗口连接后，即可选择游戏并打开工坊。');
      }, 6000);
    }
  }

  void init();
})();
