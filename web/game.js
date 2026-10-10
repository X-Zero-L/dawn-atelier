'use strict';
const $=selector=>document.querySelector(selector);
const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const format=value=>Number(value).toLocaleString('zh-CN');
const state={boot:null,save:null,pending:new Map(),group:'全部',plan:null,requests:0,generation:0,updating:null,lastInput:0};
function toast(text){const node=document.createElement('div');node.className='toast';node.textContent=text;$('#toasts').append(node);setTimeout(()=>node.remove(),5500);}
function error(text){$('#error').hidden=!text;$('#error').textContent=text||'';}
async function api(route,body){
  if(state.updating)throw new Error('工坊正在更新，请稍候。');
  state.requests++;
  try{const response=await fetch(route,body?{method:'POST',headers:{'Content-Type':'application/json','X-Dawn-Token':state.boot.token},body:JSON.stringify(body)}:{});const value=await response.json();if(!response.ok)throw new Error(value.error||'暂时无法完成。');return value;}finally{state.requests--;}
}
function draftKey(){return state.save?`atelier-draft:${state.boot.game.id}:${state.save.id}:${state.save.sha256}`:null;}
function persist(){const key=draftKey();if(!key)return;try{if(state.pending.size)localStorage.setItem(key,JSON.stringify([...state.pending]));else localStorage.removeItem(key);}catch{toast('浏览器草稿存储不可用，请在关闭前导出。');}}
function pending(){const count=state.pending.size;$('#pending').hidden=!count;document.body.classList.toggle('has-pending',!!count);$('#pending-count').textContent=`${count} 项修改，等待预览`;persist();}
function resetPlan(){state.plan=null;}
function renderFields(){
  if(!state.save)return;
  const groups=['全部',...new Set(state.save.fields.map(f=>f.group))];
  if(!groups.includes(state.group))state.group='全部';
  $('#groups').innerHTML=groups.map(g=>`<button class="${state.group===g?'active':''}" data-group="${escapeHTML(g)}">${escapeHTML(g)}</button>`).join('');
  const query=$('#search').value.trim().toLowerCase();
  const fields=state.save.fields.filter(f=>(state.group==='全部'||f.group===state.group)&&(!query||(f.label+' '+f.id).toLowerCase().includes(query)));
  $('#fields').innerHTML=fields.map(f=>`<article class="field ${state.pending.has(f.id)?'changed':''}"><div class="field-top"><span class="field-id">${escapeHTML(f.id)}</span>${state.pending.has(f.id)?'<span class="changed-tag">已加入清单</span>':''}</div><h3>${escapeHTML(f.label)}</h3><p>${escapeHTML(f.description)}</p><div class="value">${format(f.value)}<small>当前数量</small></div><div class="field-edit"><input type="number" inputmode="numeric" min="${f.min}" max="${f.max}" step="1" value="${state.pending.get(f.id)??f.value}" data-value="${escapeHTML(f.id)}" aria-label="${escapeHTML(f.label)}目标数量"><button class="button" data-set="${escapeHTML(f.id)}">加入清单</button></div><small class="field-hint">可填 ${format(f.min)} – ${format(f.max)} · ${escapeHTML(f.group)}</small></article>`).join('')||'<div class="empty"><h2>没有匹配的可修改项</h2><p>仅展示本存档中已存在且已确认的记录。</p></div>';
}
function renderSave(){
  $('#empty').hidden=true;$('#editor').hidden=false;
  $('#presets').innerHTML=state.boot.presets.map((p,index)=>`<button class="preset" data-preset="${escapeHTML(p.id)}"><span class="preset-number">PRESET / 0${index+1}</span><span class="arrow">↗</span><strong>${escapeHTML(p.title)}</strong><p>${escapeHTML(p.description)}</p></button>`).join('');
  $('#notes').innerHTML=(state.save.notes||state.boot.notes).map(n=>`<li>${escapeHTML(n)}</li>`).join('');
  $('#summary').innerHTML=Object.entries(state.save.summary||{}).map(([k,v])=>`<div class="summary-row"><span>${escapeHTML(k)}</span><span>${escapeHTML(v)}</span></div>`).join('');
  renderActors();
  $('#status').textContent=`${state.save.title} · 已读取 ${state.save.fields.length} 项可修改资源`;
  renderFields();pending();
}
function renderActors(){
  const actors=state.save?.actors||[],plan=state.save?.actor_plan;
  $('#actor-section').hidden=!actors.length;
  if(!actors.length)return;
  $('#actor-message').textContent=plan.message;
  $('#prepare-actors').disabled=!Object.keys(plan.targets).length;
  $('#prepare-actors').textContent=Object.keys(plan.targets).length?'补足未解锁角色的解析资源 →':'没有可准备的角色资源';
  $('#actor-costs').innerHTML=(plan.requirements||[]).map(r=>`<span>${escapeHTML(r.label)} · 总计 ${r.required} · 当前 ${format(r.owned)} · 缺 ${r.missing}</span>`).join('');
  $('#actor-grid').innerHTML=actors.map(a=>`<article class="actor-card ${a.owned?'owned':'locked'}"><div class="actor-card-heading"><span class="actor-monogram" aria-hidden="true">${escapeHTML(a.name.slice(0,1))}</span><div><h3>${escapeHTML(a.name)}</h3><small>${escapeHTML(a.kind)}角色 · ${a.id}</small></div></div><strong>${escapeHTML(a.status)}</strong><p>${escapeHTML(a.detail)}</p></article>`).join('');
}
async function refreshSaves(){
  if(!state.boot)return;
  const response=await api('/api/saves');
  state.boot.saves=response.saves;
  const previous=state.save?.id||$('#save-select').value;
  $('#save-select').innerHTML=response.saves.length?response.saves.map((s,index)=>`<option value="${escapeHTML(s.id)}">${escapeHTML(s.title)} · ${escapeHTML(s.modified?.replace('T',' ')||'不可读')}${response.saves.filter(row=>row.title===s.title).length>1?' · '+s.id.slice(0,6):''}</option>`).join(''):'<option value="">尚未发现存档</option>';
  if(response.saves.some(s=>s.id===previous))$('#save-select').value=previous;
  if(state.save){const current=response.saves.find(s=>s.id===state.save.id);$('#stale').hidden=!!current&&current.sha256===state.save.sha256;}
  if(!response.saves.length&&!state.save){$('#empty').hidden=false;$('#editor').hidden=true;$('#status').textContent='等待游戏保存本地进度';}
}
async function loadSave(){
  const id=$('#save-select').value;
  if(!id)return;
  persist();const generation=++state.generation;error('');$('#status').textContent='正在核对存档与游戏规则…';
  try{
    const save=await api('/api/save?id='+encodeURIComponent(id));
    if(generation!==state.generation)return;
    state.save=save;state.pending=new Map();resetPlan();$('#stale').hidden=true;
    try{const saved=JSON.parse(localStorage.getItem(draftKey())||'[]');for(const [key,value]of saved){const field=save.fields.find(f=>f.id===key);if(field&&Number.isSafeInteger(value)&&value>=field.min&&value<=field.max&&value!==field.value)state.pending.set(key,value);}}catch{ /* Invalid old drafts are not applied. */ }
    renderSave();
  }catch(e){if(generation!==state.generation)return;state.save=null;state.pending.clear();resetPlan();$('#editor').hidden=true;$('#pending').hidden=true;error(e.message);$('#status').textContent='存档暂未开放编辑';}
}
function setValue(key,value){
  const field=state.save.fields.find(f=>f.id===key);
  if(!field||!Number.isSafeInteger(value)||value<field.min||value>field.max)throw new Error(`请输入 ${format(field?.min||0)} 至 ${format(field?.max||0)} 的整数。`);
  if(value===field.value)state.pending.delete(key);else state.pending.set(key,value);
  resetPlan();renderFields();pending();
}
function requestBody(){return{save:state.save.id,sha256:state.save.sha256,operations:[...state.pending].map(([target,value])=>({action:'set',target,value})),plan_id:state.plan?.plan_id};}
async function review(){
  if(!state.pending.size)return;
  const dialog=$('#review-dialog');if(!dialog.open)dialog.showModal();$('#review-content').textContent='正在核对修改方案…';resetPlan();
  try{state.plan=await api('/api/preview',requestBody());
    $('#review-content').innerHTML=`<p class="dialog-note">${escapeHTML(state.save.title)} · 只有以下数值会改变。导出和直接应用都会先备份原始存档。</p><div>${state.plan.changes.map(c=>`<div class="change"><span>${escapeHTML(c.label)}</span><div><del>${format(c.before)}</del><span>→</span><b>${format(c.after)}</b><button class="icon-button" data-remove="${escapeHTML(c.target)}" aria-label="移除${escapeHTML(c.label)}">×</button></div></div>`).join('')}</div><div class="dialog-actions"><button class="button" id="export-save">导出修改副本</button><button class="button primary" id="apply-save" disabled>备份并直接应用</button></div><p class="dialog-note" id="runtime-note">正在检测游戏运行状态…</p><button class="text-button" id="refresh-runtime">重新检测 ↻</button>`;
    await runtime();
  }catch(e){$('#review-content').textContent=e.message;}
}
async function runtime(){const value=await api('/api/runtime');if($('#runtime-note'))$('#runtime-note').textContent=value.message;if($('#apply-save'))$('#apply-save').disabled=!value.can_apply;}
async function commit(mode){
  if(!state.plan)return;
  const buttons=[...$('#review-content').querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  try{const result=await api('/api/'+mode,requestBody());state.pending.clear();persist();pending();resetPlan();
    $('#review-content').innerHTML=`<div class="success"><div class="success-symbol">✓</div><h3>${mode==='export'?'修改副本已保存':'已备份并应用'}</h3><p>${mode==='export'?'退出游戏后，将副本替换到对应存档位置，再进入游戏读取。导出文件名不同，替换时应改回原存档名。':'重新进入游戏，读取这份存档即可。'}<br>原始进度已在工坊中备份。</p>${result.download?`<a class="button primary" href="${escapeHTML(result.download)}" download>下载修改副本 ↓</a>`:''}<p>${escapeHTML(result.filename)}</p><a class="text-button" href="/backups/${encodeURIComponent(result.backup)}" download>下载修改前的原档</a></div>`;
    if(result.warning)toast(result.warning);
    if(mode==='apply')await loadSave();else renderFields();await refreshSaves();
  }catch(e){toast(e.message);buttons.forEach(b=>b.disabled=false);await runtime().catch(()=>{});}
}
async function history(){
  $('#history-dialog').showModal();$('#history-content').textContent='正在读取…';
  try{const result=await api('/api/exports');$('#history-content').innerHTML='<h3>已导出副本</h3>'+result.files.map(f=>`<div class="history-row"><div><strong>${escapeHTML(f.name)}</strong><small>${escapeHTML(f.modified)}</small></div><a class="button" download href="${escapeHTML(f.download)}">下载 ↓</a></div>`).join('')+(!result.files.length?'<p class="dialog-note">还没有导出记录。</p>':'')+'<h3>原始存档备份</h3>'+result.history.map(h=>`<div class="history-row"><div><strong>${h.mode==='apply'?'直接应用':'导出副本'} · ${h.count} 项修改</strong><small>${escapeHTML(h.created)}</small></div><a class="button" download href="${escapeHTML(h.backup_download)}">下载原档 ↓</a></div>`).join('')+(!result.history.length?'<p class="dialog-note">每次保存前都会创建备份。</p>':'');}catch(e){$('#history-content').textContent=e.message;}
}
document.addEventListener('click',async event=>{
  const target=event.target.closest('button');if(!target)return;
  try{
    if(target.classList.contains('close')){target.closest('dialog').close();return;}
    if(target.dataset.group){state.group=target.dataset.group;renderFields();return;}
    if(target.dataset.set){const input=[...document.querySelectorAll('[data-value]')].find(n=>n.dataset.value===target.dataset.set);if(input.value.trim()==='')throw new Error('请填写目标数量。');setValue(target.dataset.set,Number(input.value));toast('已加入修改清单。');return;}
    if(target.dataset.preset){const preset=state.boot.presets.find(p=>p.id===target.dataset.preset);let added=0,missing=0;for(const [key,value]of Object.entries(preset.targets)){const field=state.save.fields.find(f=>f.id===key);if(!field){missing++;continue;}const next=Math.max(field.value,Math.min(field.max,Math.max(value,state.pending.get(key)||0)));if(next!==field.value){state.pending.set(key,next);added++;}}resetPlan();renderFields();pending();toast(`${added} 项已加入清单${missing?'；'+missing+' 项因存档没有记录而跳过':''}。`);return;}
    if(target.dataset.remove){state.pending.delete(target.dataset.remove);pending();renderFields();if(state.pending.size)await review();else $('#review-dialog').close();return;}
    if(target.id==='prepare-actors'){
      let count=0;
      for(const [key,value] of Object.entries(state.save.actor_plan.targets)){
        const field=state.save.fields.find(f=>f.id===key);if(!field)continue;
        const next=Math.max(field.value,Math.min(field.max,Math.max(value,state.pending.get(key)||0)));
        if(next!==field.value){state.pending.set(key,next);count++;}
      }
      resetPlan();renderFields();pending();toast(count?`${count} 项解析资源已加入清单。保存后回游戏执行角色解析。`:'解析资源已满足目标，回游戏选择角色并解析即可。');return;
    }
    const actions={'refresh-list':async()=>{await refreshSaves();if(!state.save)await loadSave();toast('存档列表已刷新。');},'reload-save':loadSave,'review':review,'history-button':history,'refresh-runtime':runtime,'export-save':()=>commit('export'),'apply-save':()=>commit('apply'),'clear':()=>{state.pending.clear();resetPlan();renderFields();pending();}};
    if(actions[target.id])await actions[target.id]();
  }catch(e){toast(e.message);}
});
$('#save-select').addEventListener('change',()=>loadSave());
$('#save-select').addEventListener('focus',()=>refreshSaves().catch(e=>error(e.message)));
$('#search').addEventListener('input',renderFields);
window.addEventListener('focus',()=>refreshSaves().catch(()=>{}));
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshSaves().catch(()=>{});});
window.addEventListener('beforeunload',event=>{if(state.pending.size){event.preventDefault();event.returnValue='';}});
document.addEventListener('input',()=>{state.lastInput=Date.now();});
window.addEventListener('message',event=>{
  if(window.parent===window||event.source!==window.parent||event.origin!==state.boot?.desktop_origin)return;
  const {type,token}=event.data||{};if(typeof token!=='string'||!/^[a-f0-9]{32}$/.test(token))return;
  if(type==='dawn-update-resume'&&state.updating===token){state.updating=null;document.body.inert=false;}
  if(type!=='dawn-update-check')return;
  const ready=!state.pending.size&&!state.requests&&!document.querySelector('dialog[open]')&&!document.activeElement?.matches('input,select,textarea')&&Date.now()-state.lastInput>2000;
  if(ready){state.updating=token;document.body.inert=true;}
  event.source.postMessage({type:'dawn-update-idle',token,ready,message:'当前有编辑或预览，请保存或关闭后再更新。'},event.origin);
});
(async()=>{try{state.boot=await api('/api/bootstrap');$('#demo-note').hidden=!state.boot.demo;$('#version').textContent='v'+state.boot.version;await refreshSaves();if(state.boot.saves.length)await loadSave();}catch(e){error(e.message);$('#status').textContent='工作台暂时无法连接';}})();
