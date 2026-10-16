// Production-bundle conversation QA with isolated responses; no user's data or model calls.
import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/LENOVO/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve('frontend/dist');
const server=createServer((req,res)=>{
 const file=path.resolve(root,'.'+decodeURIComponent(req.url.split('?')[0])+(req.url==='/'?'index.html':''));
 if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
 try{res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));}catch{res.writeHead(404).end();}
});
await new Promise(r=>server.listen(4175,'127.0.0.1',r));
let browser;
try{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 for(const [label,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const context=await browser.newContext({viewport}),page=await context.newPage(),errors=[],requests=[];
  let signedIn=false;
  page.on('pageerror',e=>errors.push(e.message));
  const session=()=>({user:signedIn?{id:1,email:'qa@example.test',is_admin:false}:null,csrf_token:'qa-token',mail_configured:false,model_mode:'fake'});
  await page.route('**/api/v1/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;let data,status=200;
   if(p.endsWith('/auth/session'))data=session();
   else if(p.endsWith('/auth/login')){signedIn=true;data=session();}
   else if(p.endsWith('/auth/logout')){signedIn=false;data=session();}
   else if(p.endsWith('/watchlists'))data=[];
   else if(p.endsWith('/agent/chat')){
    const messages=req.postDataJSON().messages;requests.push(messages);
    assert(messages.length<=20);assert(messages.reduce((n,m)=>n+m.content.length,0)<=20000);
    assert(messages.every(m=>m.content.length<=4000&&m.content.trim()));assert.equal(messages.at(-1).role,'user');
    const n=requests.length;
    const answer=n===1?'隔离测试：RSI衡量一段时间内价格上涨和下跌的相对强弱。它需要结合行情判断，不能单凭一个数字决定买卖。':n===2?'隔离测试：这类指标反映过去的价格变化，不能保证下一步走势。':n===3?'隔离测试长回答：'+ '历史指标需要核对样本。'.repeat(600)+'结尾总结：资料不足时应保留判断。':'隔离测试：结合刚才的讨论，先确认数据日期与样本，再解读历史指标。\n\n**简要总结**：指标是研究线索，资料缺失时不能补造结论。';
    data={status:'completed',rounds:1,model_mode:'fake',answer,executions:[]};
   }else{status=404;data={detail:'QA route missing: '+p};}
   await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  });
  await page.goto('http://127.0.0.1:4175');await page.locator('#startBtn').click();await page.locator('#auth-email').fill('qa@example.test');await page.locator('#auth-password').fill('qa-password');await page.locator('#auth-submit').click();await page.locator('[data-page="agent"]').click();
  const send=async question=>{await page.locator('#input-box').fill(question);await page.locator('#send-button').click();await page.locator('#send-button:not([disabled])').waitFor();};
  await send('RSI是什么？简短说一下');await send('那它能预测明天吗？');
  assert(requests[1].some(m=>m.role==='user'&&m.content.includes('RSI是什么')));
  assert(requests[1].some(m=>m.role==='assistant'&&m.content.includes('相对强弱')));
  await send('长回答边界验收');assert((await page.locator('.message').last().textContent()).length>4000);
  await send('刚才结尾说的资料不足是什么意思？');
  assert(requests[3].some(m=>m.role==='assistant'&&m.content.includes('原回答中间部分省略')&&m.content.endsWith('结尾总结：资料不足时应保留判断。')));
  for(let i=0;i<10;i++)await send('继续解释第'+i+'个问题');
  assert.equal(requests.at(-1).at(-1).content,'继续解释第9个问题');assert.equal(requests.at(-1)[0].role,'user');
  assert.equal(await page.locator('.tool-record,.tool-tag').count(),0);assert.equal(await page.locator('#session-meta').isVisible(),false);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.evaluate(()=>{const e=document.querySelector('#messages-area');e.scrollTop=e.scrollHeight;});
  await page.screenshot({path:`docs/visual-qa/assistant-natural-${label}.png`,fullPage:true});
  await page.locator('#account-button').click();assert.equal(await page.locator('#input-box').inputValue(),'');
  assert.deepEqual(errors,[]);console.log(`PASS ${label}: conversation context, long answers, 14 turns, private-state cleanup, hidden operations, responsive production bundle`);await context.close();
 }
}finally{await browser?.close();await new Promise(r=>server.close(r));}
