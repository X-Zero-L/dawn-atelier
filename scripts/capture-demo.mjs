// Capture only this project's localhost demo in a fresh headless Chrome profile.
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const base=process.env.DAWN_DEMO_URL||'http://127.0.0.1:8767';
if(!['127.0.0.1','localhost','[::1]'].includes(new URL(base).hostname))throw new Error('Capture is limited to a localhost demo.');
const health=await(await fetch(base+'/api/health')).json();
if(!health.demo)throw new Error('Start the synthetic demo before capturing public screenshots.');
const browserCandidates=[process.env.CHROME_PATH,...(process.platform==='win32'?[
  path.join(process.env.PROGRAMFILES||'C:/Program Files','Google/Chrome/Application/chrome.exe'),
  path.join(process.env['PROGRAMFILES(X86)']||'C:/Program Files (x86)','Microsoft/Edge/Application/msedge.exe')]:
  process.platform==='darwin'?['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']:['/usr/bin/google-chrome','/usr/bin/chromium','/usr/bin/chromium-browser'])].filter(Boolean);
let executable;
for(const candidate of browserCandidates){try{await fs.access(candidate);executable=candidate;break;}catch{}}
if(!executable)throw new Error('Set CHROME_PATH to an installed Chromium browser.');
const profile=await fs.mkdtemp(path.join(os.tmpdir(),'dawn-atelier-capture-'));
const browserProcess=spawn(executable,['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{windowsHide:true,stdio:'ignore'});
const sockets=[];
const output=path.join(root,'docs/images');await fs.mkdir(output,{recursive:true});
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function connect(url){const socket=new WebSocket(url);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});sockets.push(socket);let id=0;const pending=new Map();socket.onmessage=event=>{const message=JSON.parse(event.data);if(message.id&&pending.has(message.id)){const p=pending.get(message.id);pending.delete(message.id);clearTimeout(p.timer);message.error?p.reject(new Error(message.error.message)):p.resolve(message.result);}};return{send(method,params={}){const current=++id;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(current);reject(new Error('CDP timeout: '+method));},25000);pending.set(current,{resolve,reject,timer});socket.send(JSON.stringify({id:current,method,params}));});}};}
let endpoint;
let browser;
async function evaluate(page,expression){const result=await page.client.send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw new Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result.value;}
async function waitFor(page,selector){for(let i=0;i<100;i++){if(await evaluate(page,`!!document.querySelector(${JSON.stringify(selector)})`))return;await pause(100);}throw new Error('Missing UI: '+selector);}
async function openPage(route,width=1600,height=1200,mobile=false){const {targetId}=await browser.send('Target.createTarget',{url:'about:blank',background:false});const targets=await(await fetch(endpoint+'/json/list')).json();const socketUrl=new URL(targets.find(t=>t.id===targetId).webSocketDebuggerUrl);socketUrl.host=new URL(endpoint).host;const client=await connect(socketUrl.href);const page={client,targetId};await client.send('Page.enable');await client.send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile});await client.send('Page.navigate',{url:base+'/#'+route});await waitFor(page,route==='presets'?'.preset-card':route==='saves'?'.category-list':route==='items'?'.item-card':'.hero');return page;}
async function capture(page,name){await evaluate(page,`(async()=>{document.querySelectorAll('img').forEach(i=>i.loading='eager');await Promise.allSettled([...document.images].map(i=>i.decode()));await document.fonts.ready;return true})()`);await pause(160);const result=await page.client.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(path.join(output,name+'.png'),Buffer.from(result.data,'base64'));console.log(name+'.png');}
async function close(page){await browser.send('Target.closeTarget',{targetId:page.targetId});}
try{
  let portFile;
  for(let i=0;i<100;i++){try{portFile=await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8');break;}catch{await pause(100);}}
  if(!portFile)throw new Error('Headless Chrome did not start.');
  const [port,browserPath]=portFile.trim().split(/\r?\n/);
  for(const host of ['127.0.0.1','[::1]']){try{const test=`http://${host}:${port}`;await fetch(test+'/json/version');endpoint=test;break;}catch{}}
  if(!endpoint)throw new Error('Cannot reach the isolated renderer.');
  browser=await connect(endpoint.replace('http:','ws:')+browserPath);
  const overview=await openPage('home',1600,1200);await capture(overview,'overview');await close(overview);
  const presets=await openPage('presets',1600,1470);await capture(presets,'presets');
  await evaluate(presets,`document.querySelector('[data-action="configure-preset"][data-id="farmer"]').click()`);await capture(presets,'builder');
  await evaluate(presets,`document.querySelector('[data-action="preview-custom-preset"]').click()`);await waitFor(presets,'.plan-reports');await capture(presets,'preview');await close(presets);
  const saves=await openPage('saves',1600,1200);
  for(const [group,name] of [['inventory','inventory'],['favor','relationships'],['tools','tools']]){await evaluate(saves,`document.querySelector('[data-action="field-group"][data-group="${group}"]').click()`);await capture(saves,name);}
  await close(saves);
  const items=await openPage('items',1600,1200);await capture(items,'items');await close(items);
  const mobile=await openPage('presets',430,1000,true);await capture(mobile,'mobile');await close(mobile);
}finally{if(browser){try{await browser.send('Browser.close');}catch{}}sockets.forEach(socket=>socket.close());browserProcess.kill();}
