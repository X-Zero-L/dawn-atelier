'use strict';

const progressionUI = {tab: 'resources', filter: 'available', page: 0, target: null, saveKey: ''};
const progressNumber = value => new Intl.NumberFormat('zh-CN', {maximumFractionDigits: 3}).format(Number(value) || 0);

function renderAlchemyTabs() {
  return `<div class="progression-tabs" role="tablist" aria-label="炼金管理"><button role="tab" aria-selected="${progressionUI.tab === 'resources'}" class="${progressionUI.tab === 'resources' ? 'active' : ''}" data-action="progression-tab" data-tab="resources">${I('flask')}炼金资源</button><button role="tab" aria-selected="${progressionUI.tab === 'unlocks'}" class="${progressionUI.tab === 'unlocks' ? 'active' : ''}" data-action="progression-tab" data-tab="unlocks">${I('star')}解锁条件 <span>NEW</span></button></div>`;
}

function nativePlanNotes(plan) {
  if (!plan.notes?.length && !plan.blockers?.length && !plan.unlock_order?.length) return '';
  return `<section class="native-plan-note"><div class="native-note-heading">${I('sprout')}回到游戏，完成最后一步</div>${(plan.notes || []).map(note => `<p>${E(note)}</p>`).join('')}${plan.blockers?.length ? `<div class="native-blockers"><strong>还需在游戏内满足</strong><ul>${plan.blockers.map(note => `<li>${E(note)}</li>`).join('')}</ul></div>` : ''}${plan.unlock_order?.length ? `<details><summary>查看 ${plan.unlock_order.length} 个天赋的解锁顺序</summary><ol class="unlock-order">${plan.unlock_order.map(node => `<li>${E(node.name)} <small>#${node.id}</small></li>`).join('')}</ol></details>` : ''}</section>`;
}

function progressionPendingNote() {
  return state.pending.size ? `<div class="progression-pending">${I('info')}已有 ${state.pending.size} 项待保存修改。当前条件显示本次读取的存档进度，保存后重新读取即可更新。</div>` : '';
}

function renderProgressionFields() {
  if (!state.save || presetUI.raw || !['workshop', 'alchemy'].includes(state.group)) return false;
  const key = state.save.name + ':' + state.save.sha256;
  if (progressionUI.saveKey !== key) {
    progressionUI.saveKey = key;
    progressionUI.page = 0;
    progressionUI.target = null;
  }
  if (state.group === 'alchemy' && progressionUI.tab !== 'unlocks') return false;
  const data = state.save.progression;
  if (state.group === 'workshop') {
    $('#field-count').textContent = '工坊条件与成长';
    $('#field-results').innerHTML = renderWorkshopPreparation(data?.workshop);
  } else {
    $('#field-count').textContent = '炼金天赋与解锁条件';
    $('#field-results').innerHTML = renderAlchemyTabs() + renderAlchemyPreparation(data?.alchemy);
  }
  return true;
}

function renderWorkshopPreparation(workshop) {
  if (!workshop?.available) return empty('还没有工坊成长记录', '先在游戏中进入工坊并保存，再重新读取存档。', 'layers');
  const choices = workshop.targets || [];
  const target = choices.find(choice => choice.level === progressionUI.target) || choices[0];
  progressionUI.target = target?.level || workshop.rank;
  const pending = progressionPendingNote();
  if (!target) return pending + `<section class="workshop-growth"><span class="eyebrow">A WORKSHOP OF YOUR OWN</span><h2>工坊已达 Lv.${workshop.rank}</h2><p>当前版本的工坊等级已达到上限。原有解锁与奖励保持在游戏进度中。</p></section>`;
  const physicalMissing = target.metrics.filter(metric => !metric.editable && !metric.met);
  return pending + `<section class="workshop-growth"><div><span class="eyebrow">A WORKSHOP OF YOUR OWN</span><h2>为工坊的下一步，<br>做好准备。</h2><p>补足累计营业额与总好感，<br>回到游戏逐级升级，领取对应的解锁与奖励。</p></div><div class="workshop-level"><span>当前工坊等级</span><strong><small>Lv.</small>${workshop.rank}</strong><span>最高 Lv.${workshop.max_rank}</span></div></section><div class="workshop-target"><label for="workshop-target">准备到哪一级<select id="workshop-target" data-action="progression-target">${choices.map(choice => `<option value="${choice.level}" ${choice.level === target.level ? 'selected' : ''}>Lv.${choice.level}${choice === choices[0] ? ' · 下一级' : ''}</option>`).join('')}</select></label><div class="amount-chips">${[choices[0].level, 20, 30, 50].filter((value, index, all) => all.indexOf(value) === index && choices.some(choice => choice.level === value)).map(value => `<button data-action="progression-level" data-value="${value}" class="${target.level === value ? 'selected' : ''}">Lv.${value}</button>`).join('')}</div></div><div class="workshop-metrics">${target.metrics.map(metric => `<article class="growth-metric ${metric.met ? 'met' : ''}"><div><span>${E(metric.name)}</span><span class="pill ${metric.met ? 'subtle' : 'gold'}">${metric.met ? '已满足' : metric.editable ? '可补足' : '需布置'}</span></div><strong>${progressNumber(metric.current)}<small>${E(metric.unit)}</small></strong><p>目标 ${progressNumber(metric.required)} ${E(metric.unit)}</p><div class="growth-track"><i style="width:${metric.required ? Math.max(0, Math.min(100, metric.current / metric.required * 100)) : 100}%"></i></div><small>${metric.met ? '当前记录已达到目标' : '还差 ' + progressNumber(metric.gap) + ' ' + E(metric.unit)}</small></article>`).join('')}</div><section class="native-guidance"><span>${I('info')}</span><div><h3>升级由游戏正常完成</h3><p>建筑价值与美观度按游戏中的实际布置重新计算${physicalMissing.length ? '，当前仍有 ' + physicalMissing.length + ' 项布置条件待满足' : '，回游戏后以工坊面板为准'}。总好感补足会调整已有角色的好感值，保存前可逐项查看。</p></div></section><div class="progression-actions"><span>本次只准备条件 · 保留更高现值</span><button class="button primary" data-action="prepare-workshop">${I('layers')}准备升级条件 ${I('arrowRight')}</button></div>`;
}

function talentStatus(talent) {
  if (talent.unlocked) return {name: talent.story && !talent.active ? '剧情待启用' : '已解锁', tone: 'subtle'};
  if (talent.story) return {name: '剧情节点', tone: 'subtle'};
  if (talent.ready) return {name: '可回游戏解锁', tone: 'subtle'};
  if (talent.blockers.length) return {name: '还有前置条件', tone: 'gold'};
  return {name: talent.resources_ready ? '先解锁前置天赋' : '可准备资源', tone: 'gold'};
}

function renderAlchemyPreparation(alchemy) {
  if (!alchemy?.available) return empty('暂时没有炼金天赋资料', '在启动设置中重新准备游戏资料，再读取存档。', 'flask');
  const filters = [{id:'available',name:'待准备'},{id:'ready',name:'可解锁'},{id:'blocked',name:'有前置'},{id:'unlocked',name:'已解锁'},{id:'all',name:'全部'}];
  const query = state.fieldQuery.trim().toLowerCase();
  const rows = alchemy.talents.filter(talent => (!query || `${talent.name} ${talent.description} ${talent.id}`.toLowerCase().includes(query)) &&
    (progressionUI.filter === 'all' || progressionUI.filter === 'available' && talent.can_prepare ||
     progressionUI.filter === 'ready' && talent.ready || progressionUI.filter === 'blocked' && !talent.unlocked && (talent.blockers.length || talent.story) ||
     progressionUI.filter === 'unlocked' && talent.unlocked));
  const pages = Math.max(1, Math.ceil(rows.length / 6));
  progressionUI.page = Math.min(progressionUI.page, pages - 1);
  const available = alchemy.talents.filter(talent => talent.can_prepare && !talent.blockers.length).length;
  return progressionPendingNote() + `<section class="unlock-intro"><div><span class="eyebrow">LET THE NEXT IDEA GROW</span><h2>点亮天赋，先备齐条件。</h2><p>按前置顺序合并金币、天赋点和材料费用。<br>保存读档后，回游戏点击解锁，让配方、建筑与能力正常生效。</p><div class="unlock-totals"><span><b>${alchemy.unlocked}</b> / ${alchemy.total} 已解锁</span><span><b>${available}</b> 个普通天赋可准备</span></div></div><button class="button primary" data-action="prepare-alchemy" ${!available ? 'disabled' : ''}>${I('flask')}准备当前可解锁项 ${I('arrowRight')}</button></section>${!alchemy.entry_open ? `<div class="native-guidance"><span>${I('info')}</span><div><h3>先完成主线“炼金入门”</h3><p>完成主线后，游戏会开放炼金界面。这里可以查看条件，单项资源也可提前准备。</p></div></div>` : ''}<div class="unlock-filter"><div class="filter-tabs">${filters.map(filter => `<button class="filter-tab ${filter.id === progressionUI.filter ? 'active' : ''}" data-action="progression-filter" data-filter="${filter.id}">${filter.name}</button>`).join('')}</div><span>${rows.length} 项天赋</span></div><div class="unlock-card-grid">${rows.slice(progressionUI.page * 6, (progressionUI.page + 1) * 6).map(renderTalentCard).join('') || empty('没有匹配的天赋', '换个关键词或分类继续查看。', 'flask')}</div>${pages > 1 ? `<div class="pagination"><button data-action="progression-page" data-delta="-1" ${!progressionUI.page ? 'disabled' : ''}>上一页</button><span>${progressionUI.page + 1} / ${pages}</span><button data-action="progression-page" data-delta="1" ${progressionUI.page + 1 >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}<p class="progression-footnote">${I('shield')}故事节点与原料“曾获得”记录由游戏推进。补库存后仍有前置条件时，会在预览中逐项列出。</p>`;
}

function renderTalentCard(talent) {
  const status = talentStatus(talent);
  const prerequisites = talent.prerequisites.filter(item => !item.active);
  return `<article class="unlock-card ${talent.unlocked ? 'is-unlocked' : ''}"><div class="unlock-card-top"><span class="unlock-symbol">${I(talent.story ? 'star' : talent.kind === 0 ? 'layers' : 'flask')}</span><span class="pill ${status.tone}">${status.name}</span></div><h3>${E(talent.name)}</h3><p class="unlock-kind">${E(talent.kind_name)}${talent.rank ? ' · 工坊 Lv.' + talent.rank : ''}</p>${talent.description !== talent.name ? `<p class="unlock-description">${E(talent.description)}</p>` : ''}${!talent.story ? `<div class="unlock-cost"><span>${I('coin')}${progressNumber(talent.gold)} 金币</span><span>${I('star')}${talent.points} 天赋点</span></div><div class="unlock-materials">${talent.materials.length ? talent.materials.map(item => `<span class="${item.owned >= item.quantity ? 'enough' : ''}">${E(item.name)} <b>${progressNumber(item.owned)} / ${item.quantity}</b></span>`).join('') : '<span>无需额外解锁材料</span>'}</div>` : ''}${prerequisites.length ? `<p class="unlock-prerequisites">前置：${prerequisites.map(item => E(item.name)).join('、')}</p>` : ''}${talent.blockers.length && !talent.unlocked ? `<details class="unlock-blockers"><summary>${talent.blockers.length} 项仍需满足的条件</summary><ul>${talent.blockers.map(message => `<li>${E(message)}</li>`).join('')}</ul></details>` : ''}<div class="unlock-card-bottom">${talent.story ? `<span>${talent.unlocked ? '剧情已解锁' : '随游戏剧情推进'}</span>` : `<button class="button ${talent.unlocked ? 'secondary' : 'primary'}" data-action="prepare-talent" data-id="${talent.id}" ${!talent.can_prepare ? 'disabled' : ''}>${talent.unlocked ? '已经解锁' : '准备这个天赋'} ${I(talent.unlocked ? 'check' : 'arrowRight')}</button>`}</div></article>`;
}

async function requestProgression(kind, options, button) {
  const original = button?.innerHTML;
  if (button) { button.disabled = true; button.textContent = '正在计算条件…'; }
  try {
    await ensurePresetSave();
    const result = await api('/api/progression-plan', {save: state.save.name, sha256: state.save.sha256, kind, ...options});
    if (result.save !== state.save?.name || result.sha256 !== state.save.sha256) throw new Error('存档已切换，请重新生成方案。');
    presetUI.plan = result;
    presetUI.planName = result.title;
    showPresetPreview();
  } catch (error) { toast(error.message, true); }
  finally { if (button) { button.disabled = false; button.innerHTML = original; } }
}

document.addEventListener('click', event => {
  const button = event.target.closest('[data-action]');
  if (!button || button.disabled) return;
  const action = button.dataset.action;
  if (action === 'progression-tab') { progressionUI.tab = button.dataset.tab; presetUI.raw = false; renderFields(); }
  else if (action === 'progression-filter') { progressionUI.filter = button.dataset.filter; progressionUI.page = 0; renderFields(); }
  else if (action === 'progression-page') { progressionUI.page = Math.max(0, progressionUI.page + Number(button.dataset.delta)); renderFields(); }
  else if (action === 'progression-level') { progressionUI.target = Number(button.dataset.value); renderFields(); }
  else if (action === 'prepare-workshop') void requestProgression('workshop', {target: progressionUI.target}, button);
  else if (action === 'prepare-alchemy') void requestProgression('alchemy', {}, button);
  else if (action === 'prepare-talent') void requestProgression('alchemy', {talent_ids: [Number(button.dataset.id)]}, button);
});
document.addEventListener('change', event => {
  if (event.target.matches('#workshop-target')) { progressionUI.target = Number(event.target.value); renderFields(); }
});
