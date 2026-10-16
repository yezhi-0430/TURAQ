import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const {chromium}=require('C:/Users/LENOVO/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const script=fs.readFileSync('frontend/theme-ui.js','utf8');
const css=fs.readFileSync('frontend/theme-ui.css','utf8');
const html=`<!DOCTYPE html><html lang="zh-CN"><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box}[hidden]{display:none!important}body{background:#101211;color:#eeefe9;font:14px/1.7 sans-serif;margin:24px}button,select{font:inherit}label{display:block}dialog{background:#171a18;color:#eee;border:1px solid #554b36;padding:24px;width:min(440px,90vw)} .sample{margin:20px 0} ${css}</style></head><body>
<form id="sample"><label>自选范围<select id="scope"><option value="">全部自选组</option><option value="1">核心观察</option><option value="2">长期跟踪</option><option value="3" disabled>不可选分组</option></select></label><button id="reset" type="reset">重置</button></form>
<label class="sample">很多股票<select id="many"></select></label><button id="show" onclick="document.querySelector('dialog').showModal()">分析公告/财报</button>
<details id="history" class="sample"><summary>分析历史</summary><p>QA 历史内容</p><button>查看结果</button></details>
<dialog id="dialog"><label>资料类型<select id="material"><option>公告</option><option>财报</option></select></label><button onclick="this.closest('dialog').close()">关闭</button></dialog>
<div id="risk-detail" hidden>详情内容</div><script>for(let i=0;i<50;i++){const o=document.createElement('option');o.value=i;o.textContent='QA 股票 '+i;document.querySelector('#many').append(o)}window.changes=[];document.querySelector('#scope').addEventListener('change',e=>changes.push(e.target.value));</script><script>${script}</script></body></html>`;
const server=createServer((req,res)=>{res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html)});
await new Promise(r=>server.listen(4175,'127.0.0.1',r));
let browser;
try{
 browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 for(const [name,viewport,motion] of [['desktop',{width:1440,height:900},'no-preference'],['mobile',{width:390,height:844},'no-preference'],['reduced',{width:900,height:700},'reduce']]){
  const context=await browser.newContext({viewport,reducedMotion:motion}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));await page.goto('http://127.0.0.1:4175');
  const scope=page.locator('[data-select-for="scope"]');await scope.waitFor();
  assert.equal(await scope.getAttribute('role'),'combobox');await scope.click();
  assert.equal(await scope.getAttribute('aria-expanded'),'true');
  const menu=page.locator('#scope-theme-menu');await menu.waitFor({state:'visible'});
  assert(await menu.evaluate(e=>getComputedStyle(e).backgroundColor!=='rgb(255, 255, 255)'));
  assert.equal(await page.getByRole('option',{name:'不可选分组'}).getAttribute('aria-disabled'),'true');
  if(motion==='no-preference')assert(await menu.evaluate(e=>e.getAnimations().some(a=>a.playState==='running')),'menu has a real opening animation');
  await scope.press('ArrowDown');await scope.press('Enter');
  assert.equal(await page.locator('#scope').inputValue(),'1');assert.deepEqual(await page.evaluate(()=>changes),['1']);
  await scope.click();await scope.press('Escape');assert.equal(await scope.getAttribute('aria-expanded'),'false');
  await page.evaluate(()=>document.querySelector('#scope').labels[0].click());
  assert.equal(await scope.getAttribute('aria-expanded'),'true','label activates the themed picker');await scope.press('Escape');
  await page.evaluate(()=>{const s=document.querySelector('#scope');s.replaceChildren(new Option('新的范围','9'));s.value='9'});
  await page.waitForFunction(()=>document.querySelector('[data-select-for="scope"]').textContent.includes('新的范围'));
  await page.locator('#reset').click();await scope.click();await scope.press('Tab');assert.equal(await scope.getAttribute('aria-expanded'),'false');
  await page.evaluate(()=>{document.querySelector('#scope').disabled=true});await page.waitForFunction(()=>document.querySelector('[data-select-for="scope"]').disabled);
  const many=page.locator('[data-select-for="many"]');
  await page.evaluate(()=>document.querySelector('#many').value='7');
  assert((await many.textContent()).includes('QA 股票 7'),'direct native value updates stay in sync');
  await page.evaluate(()=>document.querySelector('#many').selectedIndex=0);
  assert((await many.textContent()).includes('QA 股票 0'),'direct selectedIndex updates stay in sync');
  await many.click();
  const bounds=await page.locator('#many-theme-menu').boundingBox();assert(bounds.x>=0&&bounds.x+bounds.width<=viewport.width);assert(bounds.y>=0&&bounds.y+bounds.height<=viewport.height);
  await many.press('End');await many.press('Enter');assert.equal(await page.locator('#many').inputValue(),'49');
  await page.locator('#show').click();await page.locator('#dialog').waitFor({state:'visible'});
  if(motion==='no-preference')assert(await page.locator('#dialog').evaluate(e=>e.getAnimations().length>0),'dialog opens smoothly');
  await page.locator('[data-select-for="material"]').click();await page.getByRole('option',{name:'财报',exact:true}).click();
  assert.equal(await page.locator('#material').inputValue(),'财报');await page.getByRole('button',{name:'关闭',exact:true}).click();
  const summary=page.locator('#history summary');await summary.click();await page.waitForFunction(()=>document.querySelector('#history').open);
  if(motion==='no-preference')assert(await page.locator('#history .theme-disclosure-body').evaluate(e=>e.getAnimations().length>0),'accordion has an opening animation');
  await summary.click();await summary.click();await page.waitForFunction(()=>document.querySelector('#history').open);
  await page.evaluate(()=>document.querySelector('#risk-detail').hidden=false);
  if(motion==='no-preference'){await page.waitForFunction(()=>document.querySelector('#risk-detail').getAnimations().length>0)}
  await many.click();await page.evaluate(()=>window.dispatchEvent(new CustomEvent('private-session-cleared')));assert.equal(await many.getAttribute('aria-expanded'),'false');assert.equal(await page.locator('.theme-select-menu:not([hidden])').count(),0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);
  console.log('PASS '+name+': themed dropdown, keyboard, form/dynamic sync, modal, disclosure, privacy, viewport, motion');await context.close();
 }
}finally{await browser?.close();await new Promise(r=>server.close(r))}
