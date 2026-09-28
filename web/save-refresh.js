'use strict';

const liveSaveUI = {request: null, generation: 0, loading: false, stale: false, timer: null};

function saveRefreshControls() {
  return `<div class="save-refresh-controls"><button class="button secondary" data-action="refresh-save-list">${I('refresh')}刷新列表</button><button class="button secondary" data-action="reload-live-save" ${!state.saveName ? 'disabled' : ''}>${I('file')}重新读取存档</button></div>`;
}

function renderSaveFreshness() {
  const selected = state.boot?.saves.find(save => save.name === state.saveName);
  const stale = !!state.save && (!selected || selected.sha256 !== state.save.sha256);
  liveSaveUI.stale = stale;
  let box = $('#save-freshness');
  if (!['saves', 'presets'].includes(state.page)) { box?.remove(); return; }
  if (!box) {
    box = document.createElement('div');
    box.id = 'save-freshness';
    const heading = $('#main .page-heading');
    if (!heading) return;
    heading.insertAdjacentElement('afterend', box);
  }
  box.className = 'save-freshness' + (stale ? ' is-stale' : '');
  box.innerHTML = `<div>${I(stale ? 'info' : 'check')}<span>${stale ? selected ? '游戏中已保存了新进度，重新读取后继续编辑。' : '当前存档已从文件夹移除，请刷新后选择其他存档。' : '存档列表自动更新，也可随时刷新。'}${state.pending.size && stale ? '<small>当前修改已保留为草稿，重新读取后按新进度重新配置。</small>' : ''}</span></div>${saveRefreshControls()}`;
  box.querySelectorAll('button').forEach(button => { button.disabled ||= liveSaveUI.loading; });
  document.querySelectorAll('#save-select, #preset-save-select').forEach(select => { select.disabled = liveSaveUI.loading; });
}

function syncSaveSelectors() {
  for (const select of document.querySelectorAll('#save-select, #preset-save-select')) {
    const values = state.boot.saves.map(save => ({value: save.name, text: `${save.title} · ${date(save.modified)}`, disabled: !!save.error}));
    if (state.saveName && !values.some(row => row.value === state.saveName)) {
      values.unshift({value: state.saveName, text: `${state.save?.title || state.saveName} · 已移除`, disabled: false});
    }
    // Keep existing option nodes in place while the native picker is open.
    const allowed = new Set(values.map(row => row.value));
    for (const option of [...select.options]) if (!allowed.has(option.value)) option.remove();
    for (const row of values) {
      let option = [...select.options].find(item => item.value === row.value);
      if (!option) { option = document.createElement('option'); option.value = row.value; select.append(option); }
      option.textContent = row.text;
      option.disabled = row.disabled;
    }
    select.value = state.saveName || '';
  }
  renderSaveFreshness();
}

async function refreshSaveList({notify = false} = {}) {
  if (!state.boot) return [];
  if (liveSaveUI.request) return liveSaveUI.request;
  liveSaveUI.request = (async () => {
    const result = await api('/api/saves');
    state.boot.saves = result.saves;
    if (!state.saveName && result.saves.some(save => !save.error)) state.saveName = result.saves.find(save => !save.error).name;
    syncSaveSelectors();
    if (notify) toast(`存档列表已更新，共 ${result.saves.length} 份。`);
    return result.saves;
  })();
  try { return await liveSaveUI.request; }
  finally { liveSaveUI.request = null; }
}

async function selectLiveSave(name, {notify = true} = {}) {
  if (!name || liveSaveUI.loading) return;
  const generation = ++liveSaveUI.generation;
  liveSaveUI.loading = true;
  renderSaveFreshness();
  const previous = state.save;
  try {
    const data = await api('/api/save?name=' + encodeURIComponent(name));
    if (generation !== liveSaveUI.generation) return;
    if (state.save !== previous) return;
    // Archive first, then replace the snapshot. Old SHA-bound drafts are never
    // reapplied to a new game save automatically.
    const retained = state.pending.size;
    persistDraft();
    state.pending = new Map();
    presetUI.history = [];
    presetUI.plan = null;
    presetUI.planName = '';
    state.editing = null;
    document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
    state.saveName = name;
    state.save = data;
    state.fieldPage = 0;
    restoreDraft();
    const row = state.boot.saves.findIndex(save => save.name === name);
    if (row >= 0) state.boot.saves[row] = data;
    else state.boot.saves.unshift(data);
    if (state.page === 'saves') {
      if ($('#save-content')) renderSaveContent(); else await renderSaves();
    } else if (state.page === 'presets') renderPresetContent();
    renderPending();
    syncSaveSelectors();
    if (notify) toast(retained && previous?.sha256 !== data.sha256 ? '已读取新进度；旧修改已保留为草稿，请按当前进度重新配置。' : '已重新读取 ' + data.title + '。');
  } catch (error) {
    syncSaveSelectors();
    toast(error.message, true);
  } finally {
    liveSaveUI.loading = false;
    renderSaveFreshness();
  }
}

async function reloadLiveSave() {
  try {
    await refreshSaveList();
    if (!state.saveName) state.saveName = state.boot.saves.find(save => !save.error)?.name;
    if (!state.saveName) {
      if (state.page === 'saves') await renderSaves();
      toast('尚未找到存档，请先在游戏中保存。');
      return;
    }
    await selectLiveSave(state.saveName);
  } catch (error) { toast(error.message, true); }
}

function bindSaveSelector(select) {
  select.addEventListener('focus', () => { void refreshSaveList().catch(error => toast(error.message, true)); });
  select.addEventListener('pointerdown', () => { void refreshSaveList().catch(error => toast(error.message, true)); });
  select.addEventListener('change', () => { void selectLiveSave(select.value); });
  syncSaveSelectors();
}

document.addEventListener('click', event => {
  const button = event.target.closest('[data-action]');
  if (!button || button.disabled) return;
  if (button.dataset.action === 'reload-live-save') void reloadLiveSave();
  if (button.dataset.action === 'refresh-save-list') {
    void refreshSaveList({notify: true}).then(async () => {
      if (state.page === 'saves' && !$('#save-select')) await renderSaves();
      if (state.page === 'presets' && !$('#preset-save-select')) await renderPresets();
    }).catch(error => toast(error.message, true));
  }
});
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && state.boot) void refreshSaveList().catch(() => {});
});
window.addEventListener('focus', () => { if (state.boot) void refreshSaveList().catch(() => {}); });
setInterval(() => {
  if (state.boot && !document.hidden && ['saves', 'presets'].includes(state.page)) void refreshSaveList().catch(() => {});
}, 8000);
