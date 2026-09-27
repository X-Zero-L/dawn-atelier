// Capture the complete public gallery from an isolated localhost demo.
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {CONFIG, ROOT, delay, sha256, sourceSnapshot, removeOwnedTemporaryDirectory} from './media-lib.mjs';

if (process.argv.length > 2) throw new Error('Capture always refreshes the complete gallery. Set DAWN_DEMO_URL and DAWN_CAPTURE_DIR as needed.');
const base = process.env.DAWN_DEMO_URL || 'http://127.0.0.1:8767';
if (!['127.0.0.1', 'localhost'].includes(new URL(base).hostname)) throw new Error('Capture is limited to a localhost demo.');
const health = await (await fetch(base + '/api/health')).json();
if (!health.demo) throw new Error('Start the synthetic demo before capturing public screenshots.');
const snapshot = await sourceSnapshot();
const output = path.resolve(process.env.DAWN_CAPTURE_DIR || path.join(ROOT, 'docs/images'));
const candidates = [process.env.CHROME_PATH, ...(process.platform === 'win32' ? [
  path.join(process.env.PROGRAMFILES || 'C:/Program Files', 'Google/Chrome/Application/chrome.exe'),
  path.join(process.env['PROGRAMFILES(X86)'] || 'C:/Program Files (x86)', 'Microsoft/Edge/Application/msedge.exe'),
] : process.platform === 'darwin' ? ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'] : [
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
])].filter(Boolean);
let executable;
for (const candidate of candidates) { try { await fs.access(candidate); executable = candidate; break; } catch {} }
if (!executable) throw new Error('Set CHROME_PATH to an installed Chromium browser.');
const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'dawn-atelier-capture-'));
let browserLog = '', browserError;
const browserProcess = spawn(executable, [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  // Ubuntu hosted runners restrict Chrome user namespaces. This opt-in is
  // limited to the disposable browser rendering our localhost synthetic demo.
  ...(process.env.DAWN_CAPTURE_NO_SANDBOX === '1' ? ['--no-sandbox', '--disable-dev-shm-usage'] : []),
  '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank',
], {windowsHide: true, stdio: ['ignore', 'ignore', 'pipe']});
browserProcess.stderr.on('data', data => { browserLog = (browserLog + data).slice(-12000); });
browserProcess.on('error', error => { browserError = error; });
const sockets = [];
const screenshots = {};
let endpoint, browser;

async function connect(url) {
  const socket = new WebSocket(url);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  sockets.push(socket);
  let id = 0;
  const pending = new Map();
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    const task = pending.get(message.id);
    if (!task) return;
    pending.delete(message.id);
    clearTimeout(task.timer);
    message.error ? task.reject(new Error(message.error.message)) : task.resolve(message.result);
  };
  socket.onclose = () => {
    for (const task of pending.values()) { clearTimeout(task.timer); task.reject(new Error('Renderer closed.')); }
    pending.clear();
  };
  return {send(method, params = {}) {
    const current = ++id;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { pending.delete(current); reject(new Error('CDP timeout: ' + method)); }, 25000);
      pending.set(current, {resolve, reject, timer});
      socket.send(JSON.stringify({id: current, method, params}));
    });
  }};
}

async function evaluate(page, expression) {
  const result = await page.client.send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result.value;
}

async function waitFor(page, expression) {
  for (let i = 0; i < 150; i++) {
    if (await evaluate(page, expression)) return;
    await delay(100);
  }
  throw new Error('UI did not become ready: ' + expression);
}

async function click(page, selector) {
  await waitFor(page, `!!document.querySelector(${JSON.stringify(selector)})`);
  await evaluate(page, `document.querySelector(${JSON.stringify(selector)}).click()`);
}

async function openPage(route, width = 1600, height = 1200, mobile = false) {
  const {targetId} = await browser.send('Target.createTarget', {url: 'about:blank', background: false});
  const targets = await (await fetch(endpoint + '/json/list')).json();
  const socketUrl = new URL(targets.find(target => target.id === targetId).webSocketDebuggerUrl);
  socketUrl.host = new URL(endpoint).host;
  const client = await connect(socketUrl.href);
  const page = {client, targetId, route, width, height};
  await client.send('Page.enable');
  await client.send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile});
  await client.send('Emulation.setTimezoneOverride', {timezoneId: 'Asia/Shanghai'});
  await client.send('Emulation.setLocaleOverride', {locale: 'zh-CN'});
  if (route.startsWith('desktop')) {
    const scene = route === 'desktop' ? 'welcome' : 'preparing';
    await client.send('Page.navigate', {url: base + '/desktop/index.html?showcase=' + scene});
    await waitFor(page, `document.body?.dataset.ready === 'true'`);
    return page;
  }
  await client.send('Page.navigate', {url: base + '/#' + route});
  const selector = route === 'presets' ? '.preset-card' : route === 'saves' ? '.category-list' : route === 'items' ? '.item-card' : '.hero';
  await waitFor(page, `!!document.querySelector('${selector}') && !!document.querySelector('.demo-banner')`);
  return page;
}

async function capture(page, name) {
  await evaluate(page, `(async () => {
    document.querySelectorAll('img').forEach(image => image.loading = 'eager');
    await Promise.all([...document.images].map(image => image.decode()));
    await document.fonts.ready;
    document.activeElement?.blur();
  })()`);
  await waitFor(page, `![...document.querySelectorAll('.toast')].some(element => !element.hidden && element.getClientRects().length)`);
  await delay(200);
  const result = await page.client.send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
  const bytes = Buffer.from(result.data, 'base64');
  if (bytes.readUInt32BE(16) !== page.width || bytes.readUInt32BE(20) !== page.height) throw new Error('Unexpected screenshot dimensions: ' + name);
  await fs.writeFile(path.join(output, name + '.png'), bytes);
  screenshots[name] = {file: name + '.png', width: page.width, height: page.height, sha256: sha256(bytes), bytes: bytes.length, route: page.route};
  console.log('Captured ' + name + '.png');
}

async function closePage(page) {
  // Only browser drafts are cleared. Export and apply are never clicked.
  if (!page.route.startsWith('desktop')) await evaluate(page, `document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close()); state.pending.clear(); persistDraft(); presetUI.history = []; renderPending();`);
  await browser.send('Target.closeTarget', {targetId: page.targetId});
}

async function review(page) {
  await waitFor(page, `!!document.querySelector('#pending-bar:not([hidden])')`);
  await click(page, '[data-action="review"]');
  await waitFor(page, `document.querySelector('#review-dialog')?.open && document.querySelector('#apply-runtime-note')?.textContent.includes('演示模式')`);
}

try {
  await fs.mkdir(output, {recursive: true});
  await fs.rm(path.join(output, 'screenshots.json'), {force: true});
  let portFile;
  for (let i = 0; i < 200; i++) {
    if (browserError || browserProcess.exitCode !== null) throw new Error('Headless Chrome failed: ' + (browserError?.message || browserLog));
    try { portFile = await fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8'); break; } catch { await delay(100); }
  }
  if (!portFile) throw new Error('Headless Chrome did not start. ' + browserLog);
  const [port, browserPath] = portFile.trim().split(/\r?\n/);
  for (const host of ['127.0.0.1', '[::1]']) {
    try { const candidate = `http://${host}:${port}`; await fetch(candidate + '/json/version'); endpoint = candidate; break; } catch {}
  }
  if (!endpoint) throw new Error('Cannot reach the isolated renderer.');
  browser = await connect(endpoint.replace('http:', 'ws:') + browserPath);

  for (const name of ['desktop', 'desktop-preparing']) {
    const launcher = await openPage(name, 1280, 900);
    await capture(launcher, name);
    await closePage(launcher);
  }

  const overview = await openPage('home');
  await capture(overview, 'overview');
  await closePage(overview);

  const presets = await openPage('presets', 1600, 1470);
  await capture(presets, 'presets');
  await click(presets, '[data-action="configure-preset"][data-id="farmer"]');
  await capture(presets, 'builder');
  await click(presets, '[data-action="preview-custom-preset"]');
  await waitFor(presets, `!!document.querySelector('.plan-reports')`);
  await click(presets, '[data-action="stage-preset"]');
  await review(presets);
  await capture(presets, 'preview');
  await closePage(presets);

  const saves = await openPage('saves');
  for (const [group, name] of [['inventory', 'inventory'], ['favor', 'relationships'], ['tools', 'tools'], ['alchemy', 'alchemy']]) {
    await click(saves, `[data-action="field-group"][data-group="${group}"]`);
    await capture(saves, name);
  }
  await click(saves, '[data-action="sediment-target"][data-value="1000"]');
  await review(saves);
  await waitFor(saves, `document.querySelector('#review-content').textContent.includes('沉淀总量摘要')`);
  await capture(saves, 'alchemy-preview');
  await closePage(saves);

  const items = await openPage('items');
  await capture(items, 'items');
  await closePage(items);

  const supply = await openPage('presets', 1600, 1300);
  await capture(supply, 'super-supply');
  await click(supply, '[data-action="apply-preset"][data-id="super"]');
  await review(supply);
  await waitFor(supply, `['铜锭', '铁锭', '金锭', '未拥有'].every(text => document.querySelector('#review-content').textContent.includes(text))`);
  await evaluate(supply, `document.querySelector('.review-dialog .change-list').scrollTop = 100000`);
  await capture(supply, 'super-supply-preview');
  await closePage(supply);

  const mobile = await openPage('presets', 430, 1060, true);
  await capture(mobile, 'super-supply-mobile');
  await evaluate(mobile, `window.scrollTo(0, document.querySelector('.preset-filter-row').getBoundingClientRect().top + window.scrollY - 18)`);
  await capture(mobile, 'mobile');
  await closePage(mobile);

  if (CONFIG.screenshots.some(name => !screenshots[name])) throw new Error('Screenshot set is incomplete.');
  if ((await sourceSnapshot()).fingerprint !== snapshot.fingerprint) throw new Error('Source changed during capture. Run again.');
  await fs.writeFile(path.join(output, 'screenshots.json'), JSON.stringify({
    schemaVersion: 1, generatedAt: new Date().toISOString(), syntheticDemo: true,
    source: snapshot, screenshots,
  }, null, 2) + '\n');
} finally {
  if (browser) { try { await browser.send('Browser.close'); } catch {} }
  sockets.forEach(socket => socket.close());
  if (browserProcess.exitCode === null) browserProcess.kill();
  await delay(500);
  await removeOwnedTemporaryDirectory(profile, os.tmpdir(), 'dawn-atelier-capture-');
}
