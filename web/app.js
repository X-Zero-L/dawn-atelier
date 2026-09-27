'use strict';

const PATHS = {
  sun:'M12 2v2m0 16v2M2 12h2m16 0h2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  sliders:'M4 4v6m0 4v6M12 4v10m0 4v2M20 4v2m0 4v10M1 10h6m2 8h6m2-12h6',
  grid:'M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z',
  book:'M3 4h6a4 4 0 0 1 3 1.5A4 4 0 0 1 15 4h6v15h-6a4 4 0 0 0-3 1.5A4 4 0 0 0 9 19H3zM12 5.5v15M6 8h3m6 0h3M6 12h3m6 0h3',
  archive:'M3 3h18v5H3zm2 5v13h14V8M9 12h6',
  search:'m20 20-5-5M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0',
  moon:'M20.9 13A9 9 0 0 1 11 3.1 9 9 0 1 0 20.9 13z',
  arrowRight:'M4 12h16m-6-6 6 6-6 6',
  arrowUpRight:'M6 18 18 6M6 6h12v12',
  chevron:'m9 5 7 7-7 7',
  calendar:'M4 5h16v16H4zM8 3v4m8-4v4M4 10h16',
  file:'M14 2H5v20h14V7zm0 0v5h5M8 12h8m-8 4h6',
  folder:'M3 5h6l2 2h10v13H3z',
  shield:'m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6zm-4 10 3 3 5-6',
  layers:'m12 2 10 5-10 5L2 7zm-10 10 10 5 10-5M2 17l10 5 10-5',
  sprout:'M12 22V12m0 4C3 17 2 10 3 5c7 0 10 3 9 11Zm0-4c0-8 5-10 9-10 0 7-2 11-9 10',
  bag:'M5 7h14l2 14H3zm3 0V5a4 4 0 0 1 8 0v2M8 10v1m8-1v1',
  flask:'M9 2h6m-5 0v7L4 19a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3L14 9V2M7 15h10',
  heart:'M20.8 4.6a5.5 5.5 0 0 0-7.8 0l-1 1-1-1a5.5 5.5 0 0 0-7.8 7.8L12 22l8.8-9.6a5.5 5.5 0 0 0 0-7.8Z',
  users:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0m9 14v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
  tool:'M14.7 6.3a5 5 0 0 0-6.3 6.3L2 19l3 3 6.4-6.4a5 5 0 0 0 6.3-6.3l-4 4-3-3z',
  dna:'M6 3c0 8 12 10 12 18M18 3c0 8-12 10-12 18M7 7h10M8 17h8M6 3h12M6 21h12',
  star:'m12 2 3.1 6.3L22 9.3l-5 4.9 1.2 6.9-6.2-3.3-6.2 3.3L7 14.2 2 9.3l6.9-1z',
  code:'m8 5-7 7 7 7m8-14 7 7-7 7m-3-17-2 20',
  check:'m5 12 4 4L19 6',
  close:'m6 6 12 12M6 18 18 6',
  info:'M12 8v.1m0 3v6m9-5a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  edit:'m16 3 5 5M3 21l5-1L21 7a2 2 0 0 0-4-4L4 16z',
  refresh:'M20 8a9 9 0 0 0-15-4L2 7m0-5v5h5M4 16a9 9 0 0 0 15 4l3-3m0 5v-5h-5',
  download:'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  bookmark:'M5 3h14v19l-7-4-7 4z',
  copy:'M9 9h12v12H9zM5 15H3V3h12v2',
  coin:'M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0M9 9c0-2 6-2 6 0s-6 2-6 4 6 2 6 0m-3-7v12',
};
const I = (name, cls='') => `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${PATHS[name] || PATHS.file}"/></svg>`;
const $ = s => document.querySelector(s);
const E = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (v, max=0) => Number(v || 0).toLocaleString('en-US', {maximumFractionDigits:max});
const date = v => new Date(v).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
const state = {boot:null, items:[], page:'home', save:null, saveName:null, group:'common', pending:new Map(),
  itemQuery:'', itemCategory:'全部物品', itemPage:0, fieldQuery:'', fieldPage:0, table:'ItemConfig', tableQuery:'', tablePage:0,
  favorites:new Set(JSON.parse(localStorage.getItem('dawn-favorites') || '[]')), editing:null, routeGeneration:0, selectedItem:null};
const NAV = [
  ['home','工坊总览','sun',''],['presets','一键方案','star','NEW'],['saves','存档编辑','sliders',''],['items','物品图鉴','grid',''],
  ['library','数据资料库','book',''],['exports','导出与备份','archive',''],
];
const TABLE_LABELS = {ItemConfig:'物品',FarmCropConfig:'作物',RecipeConfig:'制作配方',FarmGeneConfig:'作物基因',
  SkillConfig:'技能',UnitConfig:'角色',StaffConfig:'员工',AlchemyTalentConfig:'炼金天赋',AlchemyLevelConfig:'炼金等级',
  BuildingConfig:'建筑',FavorNPCConfig:'NPC 好感',BuffConfig:'增益效果',MissionConfig:'任务',Language:'多语言文本',
  LanguageTalk:'对白文本',Conversation:'剧情对话',ToolUpgradeConfig:'工具升级',FishConfig:'鱼类',ShopRankConfig:'店铺等级',
  AttributesConfig:'基础属性',RenownLevelConfig:'声望等级',StaffWorkConfig:'员工工作',OrderConfig:'订单'};
Object.assign(TABLE_LABELS,{AchievementConfig:'成就',ActionEnum:'动作编号',AlchemyProductConfig:'炼金产物',AlchemySeedConfig:'炼金种子',BagTagConfig:'背包分类',BlackJackCardConfig:'卡牌',BlackJackCardEffectConfig:'卡牌效果',BlackJackGameConfig:'牌局',BlackJackGoldCageConfig:'金笼',CGHandBookConfig:'CG 图鉴',Condition:'条件',DailyTips:'每日提示',DailyTipsConfig:'提示配置',EffectConfig:'效果',EventConfig:'事件',FarmLabelConfig:'农田标签',FavorFactionConfig:'阵营好感',FishingPoolConfig:'鱼池',FishingToolConfig:'钓鱼工具',FunctionEnum:'功能编号',FunctionManageConfig:'功能管理',GameStatsEnumConfig:'统计编号',GlobalParamString:'全局参数',GridGroupConfig:'格子组',GuestBubbleConfig:'顾客气泡',GuestBubbleGroupConfig:'顾客气泡组',GuestGroupConfig:'顾客分组',HandBookConfig:'手册',IllustrationConfig:'图鉴',IllustrationForceConfig:'图鉴势力',ItemGroupConfig:'物品组',MapAreaUnlockConfig:'区域解锁',MapAtmosphereControlConfig:'地图氛围',MapAtmosphereController:'氛围控制器',MapConfig:'地图',MapRegionUnlockConfig:'地图区域解锁',MapShopThemeConfig:'店铺主题',NPCEscrowConfig:'NPC 寄存',OrderGroupConfig:'订单组',PortraitConfig:'头像',PuzzleConfig:'谜题',QTEAreaLogicTable:'QTE 区域逻辑',QTEAreaTable:'QTE 区域',QTEConfig:'QTE 配置',QTEData:'QTE 数据',QTEPointerTable:'QTE 指针',RelicEffectConfig:'遗物效果',RelicExtractConfig:'遗物提取',RelicFactionConfig:'遗物阵营',RelicGroupConfig:'遗物组',ScheduleConfig:'日程',ShopBaseConfig:'店铺基础',ShopItemConfig:'商店物品',SoundConfig:'声音',StaffBackpackConfig:'员工背包',StaffSettingConfig:'员工设置',SubtitlesConfig:'字幕',VortexConfig:'漩涡'});

async function api(path, body) {
  const response = await fetch(path, body ? {method:'POST',headers:{'Content-Type':'application/json','X-Dawn-Token':state.boot.token},body:JSON.stringify(body)} : {});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '暂时无法完成操作。');
  return data;
}
function hydrateIcons(scope=document) { scope.querySelectorAll('[data-icon]').forEach(n => {n.innerHTML=I(n.dataset.icon);}); }
function toast(message, error=false) { const t=document.createElement('div');t.className='toast'+(error?' error':'');t.textContent=message;$('#toast-region').append(t);setTimeout(()=>t.remove(),4500); }
function loading() { return `<div class="section-loading"><span class="loading-orbit"></span>正在读取本地数据…</div>`; }
function empty(title, text, icon='search', action='') { return `<div class="empty-state">${I(icon)}<h3>${E(title)}</h3><p>${E(text)}</p>${action}</div>`; }
function heading(eyebrow,title,description,action='') {return `<div class="page-heading"><div><span class="eyebrow">${E(eyebrow)}</span><h1>${E(title)}</h1><p>${E(description)}</p></div>${action}</div>`;}
function iconImage(item, cls='') {return item.icon?`<img class="${cls}" src="${E(item.icon)}" alt="${E(item.name || item.detail)}" loading="lazy">`:I('sprout');}
function setPage(page) {if (location.hash.slice(1)===page) route();else location.hash=page;}
function renderNav() {NAV.find(x=>x[0]==='items')[3]=String(state.items.length);NAV.find(x=>x[0]==='library')[3]=String(state.boot.stats.table_count);$('#navigation').innerHTML=NAV.map(([id,label,icon,count],idx)=>`${id==='exports'?'<div class="nav-divider"></div>':''}<a href="#${id}" class="nav-link ${state.page===id?'active':''}" ${state.page===id?'aria-current="page"':''} title="${label}">${I(icon)}<span class="nav-label">${label}</span>${count?`<span class="nav-count">${count}</span>`:''}</a>`).join('');}

function renderHome() {
  const s=state.boot.saves.find(x=>x.kind==='manual'&&!x.error)||state.boot.saves.find(x=>!x.error);
  const day=new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'});
  const quick=[['bag','背包与物品','让旅途的行囊更充实','inventory'],['flask','炼金与天赋','为下一次灵感做好准备','alchemy'],['heart','NPC 与好感','记录每一份相遇','favor'],['sprout','作物与基因','照看你的小小花园','farm']];
  $('#main').innerHTML=heading('A NEW DAY, YOUR WAY','工坊总览','欢迎回来，旅人。今天，也按自己的节奏出发。',`<div class="date-badge">${I('calendar')}${E(day)}</div>`)+
  `<section class="hero"><div class="hero-copy"><span class="eyebrow">YOUR LITTLE CORNER OF DAWN</span><h2>把冒险，<br>调成喜欢的样子。</h2><p>整理行囊，点亮天赋，照看每一份成长。<br>你的世界，都在这间小工坊。</p><a class="button primary" href="#presets">选择一键方案 ${I('arrowRight')}</a><a class="hero-secondary" href="#saves">手动调整存档</a></div><div class="hero-art"><div class="hero-sun"></div><span class="hero-stars">✦</span><img src="/assets/piper.webp" alt="游戏中的吹笛人"><svg viewBox="0 0 145 190" fill="none" aria-hidden="true"><path d="M36 195C54 133 57 77 98 14M57 124C27 117 24 94 22 72c31 7 43 22 35 52ZM71 83c32 1 42-21 50-40-33 1-44 15-50 40ZM49 160c35-8 53-19 70-39-42-3-61 12-70 39Z" stroke="currentColor" stroke-width="1.4"/><path d="M26 198C32 143 17 139 6 119M30 158c18-8 23-20 25-30-19 2-29 13-25 30Z" stroke="currentColor" stroke-width="1.2"/></svg></div><span class="hero-index">EST. IN YOUR WORLD</span></section>`+
  `<section class="metrics" aria-label="工坊数据">${[[state.boot.stats.item_count,'物品已收录','种','bag'],[state.boot.stats.table_count,'游戏配置表','张','book'],[state.boot.saves.length,'本地存档','份','file'],[state.boot.resources.bundles,'资源包已整理','个','layers']].map(([value,label,unit,icon])=>`<div class="metric"><div><div class="metric-label">${label}</div><strong>${num(value)}<small>${unit}</small></strong></div><span class="metric-symbol">${I(icon)}</span></div>`).join('')}</section>`+
  `<section class="home-presets"><div class="section-heading"><h2>今天，想怎样冒险？</h2><a class="text-button" href="#presets">全部方案 ${I('arrowRight')}</a></div><div class="home-preset-grid">${(presetUI.catalog?.bundles||[]).slice(0,3).map(p=>`<button class="home-preset tone-${p.tone}" data-action="apply-preset" data-id="${p.id}"><span class="home-preset-icon">${I(p.icon)}</span><span><strong>${E(p.name)}</strong><small>${E(p.subtitle)}</small></span>${I('arrowUpRight')}</button>`).join('')}</div></section><div class="home-columns"><section><div class="section-heading"><h2>继续你的冒险 <span>RECENT SAVE</span></h2><a class="text-button" href="#saves">全部存档 ${I('arrowRight')}</a></div>${s?`<div class="panel recent-save"><div class="save-row-heading"><span class="save-symbol">${I('file')}</span><div><h3>${E(s.title)}</h3><p>上次保存于 ${E(date(s.modified))}</p></div><span class="pill">可编辑</span></div><div class="save-numbers"><div><span>持有金币</span><strong>${num(s.gold,1)}</strong></div><div><span>炼金等级</span><strong><small>Lv.</small> ${s.level}</strong></div><div><span>天赋点数</span><strong>${s.talent}<small>点</small></strong></div></div><div class="save-actions"><span class="file-label">${I('shield')}导出时自动备份</span><button class="text-button" data-action="edit-save" data-save="${E(s.name)}">进入存档 ${I('arrowUpRight')}</button></div></div>`:empty('还没有发现存档','先在游戏中保存一次，然后刷新工作台。','file')}<p class="small-note">${I('info')}这里显示已保存的进度，游戏中的即时变化需要重新保存后读取。</p></section><section><div class="section-heading"><h2>从一点小改变开始</h2><span class="pill subtle">QUICK ACCESS</span></div><div class="quick-links">${quick.map(([icon,title,desc,group])=>`<button class="quick-card" data-action="quick" data-group="${group}">${I(icon)}${I('arrowUpRight','quick-arrow')}<strong>${title}</strong><span>${desc}</span></button>`).join('')}</div></section></div>`;
}

function renderItems() {
  $('#main').innerHTML=heading('THE FIELD GUIDE','物品图鉴','从一粒种子到一瓶药剂，在这里找到它们的名字与用途。',`<span class="pill gold">${I('book')} ${state.items.length} 种发现</span>`)+
  `<div class="toolbar"><label class="search-box">${I('search')}<input id="item-search" placeholder="搜索名称、描述或物品 ID" aria-label="搜索物品" value="${E(state.itemQuery)}"></label><div class="filter-tabs" role="group" aria-label="物品分类">${['全部物品','种子','鱼类','药剂','已收藏'].map(c=>`<button class="filter-tab ${state.itemCategory===c?'active':''}" data-action="item-filter" data-category="${c}">${c}</button>`).join('')}</div><span class="results-count" id="item-result-count"></span></div><div id="item-results"></div>`;
  $('#item-search').addEventListener('input',e=>{state.itemQuery=e.target.value;state.itemPage=0;renderItemResults();});
  renderItemResults();
}
function renderItemResults() {
  const q=state.itemQuery.trim().toLowerCase();
  const filtered=state.items.filter(x=>(state.itemCategory==='全部物品'||(state.itemCategory==='已收藏'?state.favorites.has(x.id):x.category===state.itemCategory))&&(!q||`${x.id} ${x.name} ${x.description} ${x.name_en}`.toLowerCase().includes(q)));
  const size=20,totalPages=Math.max(1,Math.ceil(filtered.length/size));state.itemPage=Math.min(state.itemPage,totalPages-1);
  $('#item-result-count').innerHTML=`找到 <b>${num(filtered.length)}</b> 件物品`;
  $('#item-results').innerHTML=filtered.length?`<div class="item-grid">${filtered.slice(state.itemPage*size,(state.itemPage+1)*size).map(x=>`<article class="item-card"><button class="bookmark-button ${state.favorites.has(x.id)?'active':''}" data-action="favorite" data-id="${x.id}" aria-label="${state.favorites.has(x.id)?'取消收藏':'收藏'}${E(x.name)}" aria-pressed="${state.favorites.has(x.id)}">${I('bookmark')}</button><button data-action="item-detail" data-id="${x.id}" class="item-open" aria-label="查看${E(x.name)}详情"><div class="item-picture"><span class="item-id"># ${x.id}</span>${iconImage(x)}</div><div class="item-info"><h3>${E(x.name||'未命名物品')}</h3><p>${E(x.category)}${I('arrowUpRight')}</p></div></button></article>`).join('')}</div><div class="pagination"><button data-action="item-page" data-delta="-1" ${state.itemPage===0?'disabled':''}>上一页</button><span><b class="page-number">${state.itemPage+1}</b> / ${totalPages}</span><button data-action="item-page" data-delta="1" ${state.itemPage===totalPages-1?'disabled':''}>下一页</button></div>`:empty(state.itemCategory==='已收藏'?'留住喜欢的小物件':'没有找到对应物品',state.itemCategory==='已收藏'?'点击物品卡片右上角的书签，就能把它留在这里。':'试试换个名称，或者直接输入物品 ID。','bookmark');
}
function showItem(id) {
  const x=state.items.find(x=>x.id===id);if(!x)return;state.selectedItem=x;
  $('#item-drawer').innerHTML=`<div class="drawer-heading"><span>图鉴 / ${E(x.category)}</span><button class="icon-button" data-action="close-drawer" aria-label="关闭物品详情">${I('close')}</button></div><div class="drawer-image">${iconImage(x)}</div><span class="eyebrow">A LITTLE DISCOVERY</span><h2>${E(x.name)}</h2><p class="drawer-en">${E(x.name_en)}</p><div class="drawer-tags"><span class="pill"># ${x.id}</span><span class="pill gold">${E(x.category)}</span></div><p class="drawer-description">${E(x.description||'此物品暂无描述。')}</p><div class="drawer-actions"><button class="button primary" data-action="favorite" data-id="${x.id}">${I('bookmark')}${state.favorites.has(x.id)?'已收藏':'加入收藏'}</button><button class="button secondary" data-action="copy-id" data-id="${x.id}">${I('copy')}复制 ID</button></div><details><summary>查看原始配置</summary><pre>${E(JSON.stringify(x.raw,null,2))}</pre></details>`;
  state.drawerTrigger=document.activeElement;$('.workspace').inert=true;$('.sidebar').inert=true;$('#drawer-backdrop').hidden=false;$('#item-drawer').hidden=false;$('#item-drawer').focus();document.body.style.overflow='hidden';
}
function closeDrawer() {$('.workspace').inert=false;$('.sidebar').inert=false;if(state.drawerTrigger?.isConnected)state.drawerTrigger.focus({preventScroll:true});state.drawerTrigger=null;$('#drawer-backdrop').hidden=true;$('#item-drawer').hidden=true;document.body.style.overflow='';state.selectedItem=null;}

async function renderSaves() {
  const saves=state.boot.saves.filter(x=>!x.error);
  if(!saves.length){$('#main').innerHTML=heading('MAKE IT YOURS','存档编辑','从一份存档开始，轻轻调整你的冒险。')+empty('还没有发现存档','在游戏中创建一份手动存档，然后刷新工作台。','file');return;}
  if(!state.saveName)state.saveName=saves[0].name;
  $('#main').innerHTML=heading('MAKE IT YOURS','存档编辑','每个改变，都可以先想一想、再确认。',`<div class="save-selector"><select id="save-select" aria-label="选择存档">${saves.map(s=>`<option value="${E(s.name)}" ${state.saveName===s.name?'selected':''}>${E(s.title)}</option>`).join('')}</select><button class="icon-button" data-action="refresh-save" title="重新读取存档" aria-label="重新读取存档">${I('refresh')}</button></div>`)+`<div id="save-content">${loading()}</div>`;
  $('#save-select').addEventListener('change',async e=>{
    if(state.pending.size){e.target.value=state.saveName;toast('先导出或清空当前修改，再切换存档。');return;}
    state.saveName=e.target.value;state.save=null;presetUI.history=[];state.fieldPage=0;await loadSave();
  });
  if(state.save&&state.save.name===state.saveName)renderSaveContent();else await loadSave();
}
async function loadSave() {
  const name=state.saveName;
  try {const data=await api('/api/save?name='+encodeURIComponent(name));if(name!==state.saveName)return;state.save=data;restoreDraft();if(state.page==='saves')renderSaveContent();renderPending();}
  catch(e){if($('#save-content'))$('#save-content').innerHTML=empty('暂时无法读取',e.message,'file');toast(e.message,true);}
}
function groupMatches(field) {return state.group==='all'||(state.group==='common'?field.common:field.group===state.group);}
function renderSaveContent() {
  const s=state.save;
  $('#save-content').innerHTML=`<section class="save-banner"><span class="save-symbol">${I('file')}</span><div><h3>${E(s.title)} <span class="pill subtle">${s.kind==='manual'?'MANUAL':'AUTO'}</span></h3><p>${E(date(s.modified))} · ${E(s.name)}</p></div><div class="save-meta"><div><span>持有金币</span><strong>${num(s.gold,1)}</strong></div><div><span>炼金等级</span><strong>${s.level}<small>Lv.</small></strong></div><div><span>背包物品</span><strong>${s.inventory}<small>组</small></strong></div></div></section><div class="editor-layout"><nav class="category-list" aria-label="存档字段分类">${state.boot.groups.map(g=>`<button class="category-button ${state.group===g.id?'active':''}" data-action="field-group" data-group="${g.id}">${I(g.icon)}<span>${E(g.label)}</span><small>${num(s.fields.filter(f=>g.id==='all'||(g.id==='common'?f.common:f.group===g.id)).length)}</small></button>`).join('')}</nav><section class="editor-content"><div class="toolbar"><label class="search-box">${I('search')}<input id="field-search" value="${E(state.fieldQuery)}" placeholder="搜索物品、角色或字段…" aria-label="搜索存档字段"></label><span class="results-count" id="field-count"></span></div><div id="field-results"></div><p class="table-hint">${I('info')}点击数值进行调整。改动会保留在清单中，确认导出后才会生成副本。</p></section></div>`;
  $('#field-search').addEventListener('input',e=>{state.fieldQuery=e.target.value;state.fieldPage=0;renderFields();});renderFields();
}
function renderFields() {
  if(renderProgressionFields())return;
  if(renderFocusedFields()){
    if(state.group==='alchemy')$('#field-results').insertAdjacentHTML('afterbegin',renderAlchemyTabs());
    return;
  }
  const q=state.fieldQuery.trim().toLowerCase();const rows=state.save.fields.filter(f=>groupMatches(f)&&(!q||`${f.label} ${f.detail} ${f.path} ${f.value}`.toLowerCase().includes(q)));
  const size=12,totalPages=Math.max(1,Math.ceil(rows.length/size));state.fieldPage=Math.min(state.fieldPage,totalPages-1);
  $('#field-count').innerHTML=`<b>${num(rows.length)}</b> 个字段`;
  $('#field-results').innerHTML=rows.length?`<div class="table-panel"><table class="data-table"><colgroup><col style="width:54%"><col style="width:31%"><col class="type-column" style="width:15%"></colgroup><thead><tr><th>项目 / 所属</th><th>当前数值</th><th class="type-column">类型</th></tr></thead><tbody>${rows.slice(state.fieldPage*size,(state.fieldPage+1)*size).map(f=>{
    const changed=state.pending.has(f.path);const value=changed?state.pending.get(f.path).value:f.value;const index=state.save.fields.indexOf(f);
    return `<tr><td><div class="field-cell">${f.icon?`<img class="field-image" src="${E(f.icon)}" alt="">`:`<span class="field-placeholder">${I(f.scale===1000?'coin':state.boot.groups.find(g=>g.id===f.group)?.icon||'sliders')}</span>`}<div><strong title="${E(f.label)}">${E(f.label)}</strong><small title="${E(f.detail)}">${E(f.detail)}</small></div></div></td><td><button class="value-button ${changed?'changed':''}" data-action="edit-field" data-index="${index}" ${f.readonly?'disabled':''} aria-label="修改${E(f.detail+' '+f.label)}"><span>${E(f.type==='bool'?(value==='true'?'开启':'关闭'):value)}</span>${I('edit')}</button></td><td class="type-column"><span class="type-label">${E(f.type==='bool'?'开关':f.type==='string'?'文字':f.scale===1000?'金币':'数值')}</span></td></tr>`;
  }).join('')}</tbody></table></div>${totalPages>1?`<div class="pagination"><button data-action="field-page" data-delta="-1" ${state.fieldPage===0?'disabled':''}>上一页</button><span><b class="page-number">${state.fieldPage+1}</b> / ${totalPages}</span><button data-action="field-page" data-delta="1" ${state.fieldPage===totalPages-1?'disabled':''}>下一页</button></div>`:''}`:empty('没有匹配的字段','换个关键词，或在“全部字段”里继续查找。');
  if(presetUI.raw&&['inventory','favor','tools','staff','alchemy'].includes(state.group))$('#field-results').insertAdjacentHTML('afterbegin',`<div class="focused-actions"><button class="text-button" data-action="toggle-raw">${I('arrowRight')}返回简洁视图</button></div>`);
}
function openEdit(index) {
  const field=state.save.fields[index];if(!field||field.readonly)return;state.editing=field;
  $('#edit-title').textContent='调整'+field.label;$('#edit-detail').textContent=field.detail;
  $('#edit-before').textContent=field.type==='bool'?(field.value==='true'?'开启':'关闭'):field.value;
  $('#edit-value').type='text';$('#edit-value').inputMode=field.type==='string'?'text':'decimal';
  $('#edit-value').value=state.pending.get(field.path)?.value ?? field.value;
  $('#edit-note').textContent=field.path===state.save.sediment_path?'填写沉淀物数量即可；保存时自动同步摘要。支持 0 至 2,147,483,647 的整数。':field.scale===1000?'直接填写金币数即可，工坊会自动换算。':field.type==='bool'?'输入 true 表示开启，false 表示关闭。':'这项改动会先加入清单，导出前都可以撤销。';
  $('#edit-path').textContent=field.path;$('#edit-dialog').showModal();$('#edit-value').focus();$('#edit-value').select();
}
function renderPending() {
  const count=state.pending.size;$('#pending-bar').hidden=!count&&!presetUI.history.length;document.body.classList.toggle('has-pending',!!count||!!presetUI.history.length);
  if(!count){if(presetUI.history.length)$('#pending-bar').innerHTML=`${I('check')}<div><strong>修改清单已清空</strong><p>原始存档未改动</p></div><div class="pending-actions"><button class="clear-pending undo-button" data-action="undo-pending">${I('refresh')}撤销上一步</button></div>`;return;}
  persistDraft();
  $('#pending-bar').innerHTML=`${I('edit')}<div><strong>${count} 项改变，等待你的确认</strong><p>${E(state.save?.title||'存档')} · 原始文件尚未改动</p></div><div class="pending-actions">${presetUI.history.length?`<button class="clear-pending undo-button" data-action="undo-pending">${I('refresh')}撤销上一步</button>`:''}<button class="clear-pending" data-action="clear-pending">撤销全部</button><button class="button" data-action="review">查看并保存 ${I('arrowRight')}</button></div>`;
}
async function reviewChanges() {
  if(!state.pending.size)return;
  $('#review-content').innerHTML=loading();if(!$('#review-dialog').open)$('#review-dialog').showModal();
  try {const data=await api('/api/preview',editBody());$('#review-content').innerHTML=`<p class="review-description">${E(state.save.title)} 的修改已列在这里。选择导出副本，或退出游戏后直接应用；两种方式都会备份原档。</p><div class="change-list">${data.changes.map((c,i)=>`<div class="change-row"><div><strong>${E(c.label)}</strong><small>${E(c.detail)} · ${E(c.automatic?'自动同步':state.pending.get(c.path)?.origin||'手动调整')}</small></div><div class="change-values"><del>${E(c.before)}</del>${I('arrowRight')}<b>${E(c.after)}</b></div>${c.automatic?`<span class="pill subtle">联动</span>`:`<button class="icon-button" data-action="remove-change" data-path="${E(c.path)}" title="撤销此项" aria-label="撤销${E(c.label)}">${I('close')}</button>`}</div>`).join('')}</div><div class="dialog-actions"><button class="button secondary" data-close="review-dialog">再想一想</button><button class="button secondary" data-action="export-save">${I('download')}导出副本</button><button class="button primary" data-action="apply-save" disabled>${I('check')}备份并直接应用</button></div><button class="text-button runtime-refresh" data-action="refresh-runtime">${I('refresh')}重新检测</button><p id="apply-runtime-note" class="runtime-note">正在读取游戏状态…</p>`;await refreshReviewRuntime();}
  catch(e){$('#review-content').innerHTML=empty('需要重新核对',e.message,'info');}
}
function editBody(){return {save:state.save.name,sha256:state.save.sha256,edits:[...state.pending.values()].map(c=>({path:c.field.path,value:c.value}))};}
async function exportChanges(button){button.disabled=true;button.textContent='正在保存副本…';try{const data=await api('/api/export',editBody());state.pending.clear();presetUI.history=[];persistDraft();renderPending();$('#review-content').innerHTML=`<div class="success-content"><div class="success-mark">${I('check')}</div><h3>这一点改变，已妥善保存。</h3><p>已生成修改副本，并备份原始存档。<br>退出游戏后替换对应存档，再回来继续冒险。</p><a class="button primary" href="${E(data.download)}" download>${I('download')}下载修改副本</a><p class="export-filename">${E(data.filename)}</p><div class="dialog-actions"><button class="button secondary" data-action="view-exports">查看全部导出 ${I('arrowRight')}</button></div></div>`;if(state.page==='saves')renderFields();toast('修改副本已保存，原档已备份。');}catch(e){toast(e.message,true);button.disabled=false;button.innerHTML=I('download')+'导出修改副本';}}

async function renderLibrary(){
  const preferred=['ItemConfig','RecipeConfig','FarmCropConfig','FarmGeneConfig','SkillConfig','AlchemyTalentConfig','BuildingConfig','FavorNPCConfig','StaffConfig','ToolUpgradeConfig'];const rank=x=>preferred.includes(x.table)?preferred.indexOf(x.table):999;const tables=[...state.boot.stats.tables].sort((a,b)=>rank(a)-rank(b));
  $('#main').innerHTML=heading('THE WORLD, IN DETAIL','数据资料库','配方、基因与成长规则，让每一份探索都有迹可循。',`<span class="pill gold">${I('layers')} ${num(state.boot.stats.row_count)} 条记录</span>`)+`<div class="library-layout"><nav class="table-list" aria-label="配置表">${tables.map(t=>`<button class="table-list-button ${state.table===t.table?'active':''}" data-action="select-table" data-table="${E(t.table)}" title="${E(t.table)}"><span>${E(TABLE_LABELS[t.table]||t.table)}</span><small>${num(t.count)}</small></button>`).join('')}</nav><section class="library-main"><h2 id="table-heading">${E(TABLE_LABELS[state.table]||state.table)}</h2><p class="library-subtitle" id="table-subtitle">${E(state.table)} · 配置记录</p><div class="toolbar"><label class="search-box">${I('search')}<input id="table-search" value="${E(state.tableQuery)}" placeholder="在这张表中搜索…" aria-label="搜索配置表"></label></div><div id="table-records">${loading()}</div></section></div>`;
  let timeout;$('#table-search').addEventListener('input',e=>{state.tableQuery=e.target.value;state.tablePage=0;clearTimeout(timeout);timeout=setTimeout(loadTable,250);});await loadTable();
}
let tableRequest=0;
async function loadTable(){const request=++tableRequest;const table=state.table;try{const data=await api(`/api/table?name=${encodeURIComponent(table)}&q=${encodeURIComponent(state.tableQuery)}&page=${state.tablePage}`);if(request!==tableRequest||state.page!=='library')return;$('#table-heading').textContent=TABLE_LABELS[table]||table;$('#table-subtitle').textContent=`${table} · ${num(data.total)} 条记录 · 配置原始字段`;$('#table-records').innerHTML=data.rows.length?data.rows.map(row=>{const preview=row.name || Object.values(row.data).filter(v=>typeof v==='string').find(v=>!v.startsWith('Assets/'))||Object.keys(row.data).slice(0,5).join(' · ');return `<details class="config-record"><summary><span class="record-id">${E(row.id)}</span><span class="record-preview">${E(preview)}</span>${I('chevron')}</summary><pre>${E(JSON.stringify(row.data,null,2))}</pre></details>`;}).join('')+`<div class="pagination"><button data-action="table-page" data-delta="-1" ${state.tablePage===0?'disabled':''}>上一页</button><span><b class="page-number">${state.tablePage+1}</b> / ${Math.max(1,Math.ceil(data.total/40))}</span><button data-action="table-page" data-delta="1" ${(state.tablePage+1)*40>=data.total?'disabled':''}>下一页</button></div>`:empty('这里没有匹配的记录','试试其他名称或 ID。');}catch(e){if($('#table-records'))$('#table-records').innerHTML=empty('无法读取配置',e.message,'info');}}
async function renderExports(){
  $('#main').innerHTML=heading('EVERY CHANGE, KEPT SAFE','导出与备份','每一次调整，都留下一份可以回去的原点。')+`<div id="exports-content">${loading()}</div>`;
  try{const data=await api('/api/exports');if(state.page!=='exports')return;$('#exports-content').innerHTML=`<div class="export-summary"><div class="panel">${I('download')}<div><h3>已导出副本</h3><strong>${data.files.length}<small>份</small></strong></div></div><div class="panel">${I('shield')}<div><h3>原始存档备份</h3><strong>${data.backup_count}<small>份</small></strong></div></div></div><div class="section-heading"><h2>你的修改副本</h2><span class="pill subtle">LOCAL ONLY</span></div>${data.files.length?`<div class="panel">${data.files.map(f=>`<div class="export-row">${I('file')}<div><h3>${E(f.name)}</h3><p>${E(date(f.modified))} · ${(f.bytes/1024).toFixed(1)} KB</p></div><a class="button secondary" href="${E(f.download)}" download>${I('download')}下载副本</a></div>`).join('')}</div>`:empty('每次改变，都会留在这里','完成存档编辑后，点击“查看并导出”即可生成副本。原始存档会同时备份。','archive','<a class="button primary" href="#saves">去编辑存档 '+I('arrowRight')+'</a>')}${renderHistory(data)}<p class="small-note">${I('folder')}修改副本保存在工具目录的 modified-saves，原档备份保存在 backups。</p>`;}catch(e){if($('#exports-content'))$('#exports-content').innerHTML=empty('暂时无法读取',e.message,'info');}
}

async function route(){if(!state.boot)return;closeDrawer();const page=location.hash.slice(1)||'home';state.page=NAV.some(n=>n[0]===page)?page:'home';renderNav();$('#breadcrumb-current').textContent=NAV.find(n=>n[0]===state.page)[1];document.title=`${$('#breadcrumb-current').textContent} · 黎明工坊 · 黎明门前的吹笛人`;window.scrollTo(0,0);if(state.page==='home')renderHome();else if(state.page==='presets')await renderPresets();else if(state.page==='items')renderItems();else if(state.page==='saves')await renderSaves();else if(state.page==='library')await renderLibrary();else await renderExports();renderPending();}

document.addEventListener('click',async event=>{
  const close=event.target.closest('[data-close]');if(close){document.getElementById(close.dataset.close).close();return;}
  const button=event.target.closest('[data-action]');if(!button)return;
  const action=button.dataset.action;
  if(action==='edit-save'){if(button.dataset.save&&!state.pending.size)state.saveName=button.dataset.save;state.group='common';setPage('saves');}
  else if(action==='quick'){state.group=button.dataset.group;state.fieldQuery='';state.fieldPage=0;setPage('saves');}
  else if(action==='item-filter'){state.itemCategory=button.dataset.category;state.itemPage=0;renderItems();}
  else if(action==='item-page'){state.itemPage+=Number(button.dataset.delta);renderItemResults();$('#item-results').scrollIntoView({block:'start',behavior:'smooth'});}
  else if(action==='item-detail')showItem(Number(button.dataset.id));
  else if(action==='favorite'){const id=Number(button.dataset.id);if(state.favorites.has(id))state.favorites.delete(id);else state.favorites.add(id);localStorage.setItem('dawn-favorites',JSON.stringify([...state.favorites]));if(state.page==='items')renderItemResults();if(state.selectedItem?.id===id)showItem(id);}
  else if(action==='copy-id'){try{await navigator.clipboard.writeText(button.dataset.id);toast('物品 ID 已复制。');}catch{toast('无法访问剪贴板，请手动复制物品编号。',true);}}
  else if(action==='close-drawer')closeDrawer();
  else if(action==='field-group'){state.group=button.dataset.group;presetUI.raw=false;state.fieldPage=0;state.fieldQuery='';renderSaveContent();}
  else if(action==='field-page'){state.fieldPage+=Number(button.dataset.delta);renderFields();}
  else if(action==='edit-field')openEdit(Number(button.dataset.index));
  else if(action==='clear-pending'){checkpoint('清空修改清单');state.pending.clear();persistDraft();renderPending();if(state.page==='saves')renderFields();toast('所有待保存的修改已撤销。');}
  else if(action==='refresh-save'){if(state.pending.size){toast('请先导出或清空修改，再重新读取。');return;}state.save=null;$('#save-content').innerHTML=loading();await loadSave();toast('已重新读取游戏存档。');}
  else if(action==='review')await reviewChanges();
  else if(action==='remove-change'){const path=button.dataset.path;if(!state.pending.has(path))return;checkpoint('移除一项修改');state.pending.delete(path);persistDraft();renderPending();if(state.page==='saves')renderFields();if(!state.pending.size)$('#review-dialog').close();else await reviewChanges();}
  else if(action==='export-save')await exportChanges(button);
  else if(action==='view-exports'){$('#review-dialog').close();setPage('exports');}
  else if(action==='select-table'){state.table=button.dataset.table;state.tablePage=0;state.tableQuery='';await renderLibrary();}
  else if(action==='table-page'){state.tablePage+=Number(button.dataset.delta);$('#table-records').innerHTML=loading();await loadTable();}
});
$('#edit-form').addEventListener('submit',event=>{event.preventDefault();const field=state.editing;let value=$('#edit-value').value;if(field.type!=='string')value=value.trim();if(field.type==='bool'&&!['true','false'].includes(value)){toast('请输入 true 或 false。',true);return;}if(field.type!=='string'&&field.type!=='bool'&&!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(value)){toast('请输入有效数字。',true);return;}queueChanges([{field,value}],'手动调整');$('#edit-dialog').close();toast(state.pending.has(field.path)?'已加入修改清单。':'已恢复原始数值。');});
$('#global-search').addEventListener('submit',event=>{event.preventDefault();state.itemQuery=$('#global-query').value;state.itemPage=0;state.itemCategory='全部物品';setPage('items');});
$('#drawer-backdrop').addEventListener('click',closeDrawer);
$('#help-button').addEventListener('click',()=>{$('#help-dialog').showModal();});
$('#theme-button').addEventListener('click',()=>{document.body.classList.toggle('dark');localStorage.setItem('dawn-theme',document.body.classList.contains('dark')?'dark':'light');$('#theme-button').innerHTML=I(document.body.classList.contains('dark')?'sun':'moon');});
document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();$('#global-query').focus();$('#global-query').select();}if(event.key==='Escape'&&!$('#item-drawer').hidden)closeDrawer();if(event.key==='Tab'&&!$('#item-drawer').hidden){const all=[...$('#item-drawer').querySelectorAll('button,summary,[tabindex="0"]')];if(!all.length)return;const first=all[0],last=all.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}});
window.addEventListener('hashchange',route);
window.addEventListener('beforeunload',event=>{if(state.pending.size){event.preventDefault();event.returnValue='';}});
if(localStorage.getItem('dawn-theme')==='dark')document.body.classList.add('dark');
hydrateIcons();
(async()=>{try{$('#connection').innerHTML='<i class="status-dot"></i> 正在连接…';const [boot,items,presets]=await Promise.all([api('/api/bootstrap'),api('/api/items'),api('/api/presets')]);state.boot=boot;state.items=items;presetUI.catalog=presets;if(boot.demo){document.body.classList.add('demo-mode');document.querySelector('.workspace').insertAdjacentHTML('afterbegin','<div class="demo-banner">演示模式 · 合成存档与示例配置，修改只作用于演示副本。</div>');}$('#connection').innerHTML='<i class="status-dot"></i> 本地已连接';await route();}catch(e){$('#connection').textContent='连接已断开';$('#main').innerHTML=empty('工坊暂时没有连接上',`${e.message} 请通过“启动网页工作台”快捷方式重新打开。`,'info');}})();
