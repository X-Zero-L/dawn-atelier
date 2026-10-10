'use strict';

const adapterGuideURL = 'https://github.com/X-Zero-L/dawn-atelier/blob/main/docs/framework.md';
const adapterExampleCommand = 'python -m atelier sample sample.json';
const adapterCapabilityIcons = {fields: 'sliders', presets: 'star', inventory: 'bag', favor: 'heart', progression: 'sprout'};
let adapterPageRequest = 0;

async function renderAdapters() {
  const request = ++adapterPageRequest;
  $('#main').innerHTML = heading('A PLACE FOR EVERY ADVENTURE', '游戏与扩展', '查看当前游戏的功能，也为下一段冒险留一个位置。') + loading();
  try {
    const catalogue = await api('/api/adapters');
    if (request !== adapterPageRequest || state.page !== 'adapters') return;
    const active = catalogue.adapters.find(adapter => adapter.id === catalogue.active);
    if (!active) throw new Error('当前游戏的适配资料暂时不可用。');
    const references = catalogue.adapters.filter(adapter => adapter.synthetic);
    const realCount = catalogue.adapters.filter(adapter => !adapter.synthetic).length;
    $('#main').innerHTML = heading('A PLACE FOR EVERY ADVENTURE', '游戏与扩展', '查看当前游戏的功能，也为下一段冒险留一个位置。',
      `<span class="pill subtle">${realCount} 款游戏 · ${references.length} 个开发示例</span>`) +
      `<div class="adapters-page">
        <section class="adapter-current" aria-labelledby="adapter-current-title">
          <div class="adapter-current-copy"><span class="adapter-current-status"><i class="status-dot"></i> 当前工作台${state.boot.demo ? ' · 演示模式' : ''}</span>
            <h2 id="adapter-current-title">${E(active.title)}</h2>
            <p>备足行囊，照看成长。<br>熟悉的修改与预设，都从这一份存档开始。</p>
            <div class="adapter-current-actions"><a class="button" href="#presets">打开一键方案 ${I('arrowRight')}</a><a href="#saves">进入存档编辑 ${I('arrowUpRight')}</a></div>
          </div>
          <div class="adapter-current-art" aria-hidden="true"><span class="adapter-orbit"></span><img src="/assets/piper.webp" alt=""><span class="adapter-art-label">THE PIPER OF DAWN</span></div>
        </section>

        <section class="adapter-capabilities" aria-labelledby="adapter-capabilities-title">
          <div class="section-heading"><h2 id="adapter-capabilities-title">为这段冒险准备好的功能</h2><span class="adapter-section-note">按游戏规则适配</span></div>
          <div class="adapter-capability-grid">${active.capabilities.map(capability =>
            `<article class="adapter-capability"><span class="adapter-capability-icon">${I(adapterCapabilityIcons[capability.id] || 'layers')}</span><h3>${E(capability.title)}</h3><p>${E(capability.description)}</p></article>`
          ).join('')}</div>
        </section>

        <section class="adapter-save-flow" aria-label="共同的存档保护流程">
          <div class="adapter-flow-heading">${I('shield')}<div><h2>每次保存，都有来处</h2><p>先看清变化，再带着备份出发。</p></div></div>
          <ol>${[['读取进度', '以当前存档为起点'], ['预览变化', '核对修改前后数值'], ['备份原档', '保留修改前的进度'], ['保存结果', '导出副本或退出游戏后应用']].map(([title, description], index) =>
            `<li><span class="adapter-step-number">0${index + 1}</span><div><strong>${title}</strong><small>${description}</small></div></li>`
          ).join('')}</ol>
        </section>

        <section class="adapter-extension" aria-labelledby="adapter-extension-title">
          <div class="adapter-extension-intro"><span class="eyebrow">THE NEXT ADVENTURE</span><h2 id="adapter-extension-title">让下一款游戏，<br>拥有自己的工坊。</h2><p>复用预览、备份与保存流程，<br>为每款游戏编写合适的修改规则。</p><a class="text-button" href="${adapterGuideURL}" target="_blank" rel="noopener noreferrer">阅读接入指南 ${I('arrowUpRight')}</a></div>
          <div class="adapter-reference"><div class="adapter-reference-top"><span class="adapter-reference-symbol">${I('code')}</span><span class="pill gold">开发示例 · 合成数据</span></div><h3>JSON 参考工程</h3><p>一个可运行的最小示例：读取金币、生成预览、导出修改副本。它演示另一种存档格式，不对应实际游戏。</p><div class="adapter-code-row"><code>${E(adapterExampleCommand)}</code><button type="button" class="icon-button" data-adapter-copy aria-label="复制创建合成存档的命令" title="复制命令">${I('copy')}</button></div><span class="adapter-reference-footnote">${I('file')}在源码目录运行，仅创建示例文件</span></div>
        </section>

        <details class="adapter-developer-notes"><summary><span>${I('layers')}开发者接入说明</span>${I('chevron')}</summary><div><p>目前完整支持的实际游戏为《黎明门前的吹笛人》。新增游戏需要确认存档格式、数值规则和版本兼容，再接入对应的界面。</p><div class="adapter-developer-grid"><article><h3>游戏规则独立</h3><p>金币编码、物品上限与解锁条件由各自的适配器处理。</p></article><article><h3>保存流程复用</h3><p>快照、预览校验、备份与操作记录由通用模块处理。</p></article><article><h3>数据按游戏区分</h3><p>独立管理每款游戏的配置、备份与导出，保留现有工坊数据。</p></article></div><p class="adapter-scope-note">当前框架处理本地存档。实时内存修改、多文件存档事务与第三方插件安装尚未提供。</p></div></details>
      </div>`;
    $('[data-adapter-copy]')?.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(adapterExampleCommand); toast('示例命令已复制。'); }
      catch { toast('暂时无法复制，请选中旁边的命令后手动复制。', true); }
    });
  } catch (error) {
    if (request !== adapterPageRequest || state.page !== 'adapters') return;
    $('#main').innerHTML = heading('YOUR GAME LIBRARY', '游戏与扩展', '查看当前游戏与可用功能。') + empty('暂时无法读取适配资料', error.message, 'info', '<button type="button" class="button secondary" id="adapter-retry">重新读取</button>');
    $('#adapter-retry')?.addEventListener('click', renderAdapters);
  }
}
