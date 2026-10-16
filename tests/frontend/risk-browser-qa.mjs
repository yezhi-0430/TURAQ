// Browser integration with explicitly fake data, never touches the user's database/model.
import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/LENOVO/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve('frontend/dist');
const server=createServer((req,res)=>{
 const file=path.join(root,decodeURIComponent(req.url.split('?')[0]).replace(/^\//,'')||'index.html');
 if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
 try{res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css': 'text/html');res.end(fs.readFileSync(file));}catch{res.writeHead(404).end();}
});
await new Promise(r=>server.listen(4174,'127.0.0.1',r));
let browser;
try{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 for(const [label,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const context=await browser.newContext({viewport,reducedMotion:'no-preference'}),page=await context.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let signedIn=false,events=[],failure=null,agentTimeout=false,agentResearch=false,autoTask=null,autoEvent=null,collectCount=0;
  const session=()=>({user:signedIn?{id:1,email:'qa@example.test',is_admin:false}:null,csrf_token:'qa-token',mail_configured:false,model_mode:'fake'});
  await page.route('**/api/v1/**',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname;
   let data,status=200;
   if(p.endsWith('/auth/session'))data=session();
   else if(p.endsWith('/auth/login')){signedIn=true;data=session();}
   else if(p.endsWith('/auth/logout')){signedIn=false;data=session();}
   else if(p.endsWith('/watchlists'))data=[{id:1,name:'核心观察'}];
   else if(p.endsWith('/watchlists/1/stocks'))data=[{symbol:'000001.SZ',name:'平安银行'}];
   else if(p==='/api/v1/stocks/search')data={results:[{symbol:'600519.SH',name:'贵州茅台'}]};
   else if(p==='/api/v1/risk/tasks'&&req.method()==='GET')data={items:autoTask?[autoTask]:[]};
   else if(p==='/api/v1/risk/tasks'&&req.method()==='POST'){const b=req.postDataJSON();autoTask={id:1,status:'queued',days:90,total:1,processed:0,updated_at:'2026-10-13T03:00:00Z',scope:{kind:b.scope,symbol:b.symbol,group_id:b.group_id},items:[{id:1,symbol:b.symbol||'000001.SZ',name:b.symbol?'贵州茅台':'平安银行',status:'pending',facts:[],coverage:{},progress:{phase:'market',documents:0,extracted:0,pages:0,batches:0,read_characters:0,errors:[]}}]};data=autoTask;}
   else if(p==='/api/v1/risk/tasks/1/collect'){collectCount++;autoTask={...autoTask,items:autoTask.items.map(i=>({...i,progress:{...i.progress,phase:'overview'}}))};data=autoTask;}
   else if(p==='/api/v1/risk/tasks/1/process'){autoTask={...autoTask,status:'completed',processed:1,items:autoTask.items.map(i=>({...i,status:'completed',progress:{...i.progress,phase:'paused',can_deepen:true},answer:{analysis_scope:'preliminary',inferences:['隔离测试首轮判断：趋势偏弱，应观察量价变化。']},event_id:i.symbol==='600519.SH'?2:null,coverage:{market:'available',reports:'partial',announcements:'failed'}}))};autoEvent={...(events[0]||{}),id:2,analysis_id:2,symbol:'600519.SH',stock_name:'贵州茅台',title:'隔离测试自动分析',summary:'隔离测试结果，未进行真实分析。',risk_type:'price_volume',risk_level:'unknown',status:'unread',analyzed_at:'2026-10-13T03:00:00Z',trade_date:'2026-10-09',model_mode:'fake',input_text:'QA隔离材料',result:{facts:[],inferences:[],unknowns:['隔离测试，未分析真实公司'],sources:[]},model_sources:[],evidence:[{verification:'source_retrieved',title:'QA财报原文夹具',date:'2026-08-15',url:'https://example.com/report.pdf',page:'5',excerpt:'QA原文，非真实财报数据。'}]};data=autoTask;}
   else if(p==='/api/v1/risk/tasks/1')data=autoTask;
   else if(p==='/api/v1/risk/events/2')data=autoEvent;
   else if(p==='/api/v1/risk/analyses/2')data={...autoEvent,historical:false,version:1};
   else if(p==='/api/v1/risk/analyses'&&req.method()==='POST'){
    if(failure){status=failure;data={detail:{429:'请求额度已用尽，请稍后重试',503:'研究服务暂不可用',504:'模型请求超时，请稍后重试'}[failure]};}
    else{const b=req.postDataJSON();data={id:1,analysis_id:1,stock_name:'平安银行',symbol:b.symbol,title:b.title,summary:'隔离测试模型结果，未对资料进行真实分析。',risk_type:b.risk_type,risk_level:'unknown',status:'unread',published_date:b.published_date,analyzed_at:'2026-10-13T03:00:00Z',model_mode:'fake',input_text:b.input_text,result:{facts:[],inferences:[],unknowns:['隔离测试模型结果，未对资料进行真实分析。'],risk_level:'unknown',sources:[]},model_sources:[],evidence:[{title:b.title,date:b.published_date,url:b.source_url,page:b.page,excerpt:b.input_text,verification:'user_provided'}]};events=[data];status=201;}
   }
   else if(p==='/api/v1/risk/analyses/1')data={...events[0],historical:true,version:1};
   else if(p==='/api/v1/risk/analyses')data={items:events.map(e=>({...e,event_id:e.id,generation_status:'completed',created_at:e.analyzed_at})),total:events.length};
   else if(p==='/api/v1/risk/events')data={items:events,total:events.length,page:1,page_size:10,overview:{monitored_stocks:1,pending:0,high:0,unknown:0},scan:{status:'not_connected'}};
   else if(p==='/api/v1/risk/events/1'){if(req.method()==='PATCH')events[0].status=req.postDataJSON().status;data=events[0];}
   else if(p==='/api/v1/agent/chat'&&agentResearch)data={status:'completed',rounds:3,run_id:'qa-research-tools',model_mode:'fake',answer:'## 隔离测试：研究结论\n\n以下内容只用于答案展示验收，非真实行情分析。\n\n- 股票资料与最新报价\n- 日、周、月 K 线与复权口径\n- MA、RSI、MACD 与量价统计',executions:[
    ...['search_stocks','get_stock_quotes','get_kline_history','calculate_technical_indicators','analyze_price_volume'].map((name,i)=>({tool_name:name,arguments:{note:'QA测试参数'},status:'success',duration_ms:1,result:'{"note":"隔离夹具，非真实行情"}',source:{kind:i===0?'cached_catalog':i>2?'python_calculation':'online_market',executed_at:'2026-10-13T03:00:00Z',record_count:2,latest_trade_date:i===0?null:'2026-10-09',upstream_source:'QA 测试源',quote_time:i===1?'2026-10-09T15:00:00+08:00':null,price_adjustment:i===2?'qfq':null,inputs_origin:i>2?'market_data':null,data_status:i===1?'partial':'available',warnings:['仅展示验收，不是实际行情。']}}))]};
   else if(p==='/api/v1/agent/chat'&&agentTimeout){status=504;data={detail:'隔离测试：模型生成超时，请稍后重试',partial:{status:'incomplete',run_id:'qa-timeout',model_mode:'fake',executions:[{tool_name:'get_daily_prices',arguments:{stock_code:'600519.SH'},status:'success',duration_ms:400,result:'{"rows":[],"note":"QA夹具，非实际行情"}',source:{kind:'online_market',executed_at:'2026-10-13T03:00:00Z',record_count:98,upstream_source:'QA 测试夹具',warnings:['仅测试展示，不是实际行情。']}}]}};}
   else if(p==='/api/v1/agent/chat')data={status:'completed',rounds:2,run_id:'qa-markdown',model_mode:'fake',
    answer:'## 隔离测试模型：排版验收\n\n**股票资料**\n- 标题和列表正常显示\n- `600519.SH`\n\n| 字段 | 内容 |\n| --- | --- |\n| 数据 | 测试夹具，非真实分析 |\n\n<script>window.unsafeExecuted=true</script>\n[危险链接](javascript:alert)\n[来源](https://example.com/report)',
    executions:[{tool_name:'get_daily_prices',arguments:{stock_code:'600519.SH'},status:'success',duration_ms:1,result:'{"rows":[]}',
     source:{kind:'online_market',executed_at:'2026-10-13T03:00:00Z',latest_trade_date:null,record_count:0,upstream_source:'QA 测试夹具',collected_at:'2026-10-13T03:00:00Z',data_status:'no_data',price_adjustment:'none',warnings:['仅测试展示，不是实际行情。']}}]};
   else{status=404;data={detail:'QA route missing: '+p};}
   if(p==='/api/v1/risk/tasks/1/process'){
    const assessment={rule_version:'market_attention_v1',risk_level:'unknown',basis:['隔离测试：趋势与量能依据展示，不代表真实行情。']};
    for(const item of data.items){if(item.event_id)item.analysis_id=2;item.coverage.sectors='partial';item.market_assessment=assessment;}
    autoEvent.result.market_assessment=assessment;
   }
   await route.fulfill({status,contentType:'application/json',headers:status===429?{'Retry-After':'30'}:{},body:JSON.stringify(data)});
  });
  await page.goto('http://127.0.0.1:4174');
  await page.locator('#startBtn').click();await page.locator('#auth-email').fill('qa@example.test');await page.locator('#auth-password').fill('qa-password');await page.locator('#auth-submit').click();
  await page.locator('[data-page="risk"]').click();
  await page.getByText('当前筛选下无已保存事件。自动扫描尚未接通；无记录不代表无风险。').waitFor();
  assert.equal(await page.locator('#risk-count-stocks').textContent(),'1');
  await page.locator('[data-select-for="risk-scope"]').click();await page.locator('#risk-scope-theme-menu').waitFor({state:'visible'});
  await page.waitForFunction(()=>!document.querySelector('#risk-scope-theme-menu').getAnimations().some(a=>a.playState==='running'));
  await page.screenshot({path:`docs/visual-qa/risk-theme-dropdown-${label}.png`,fullPage:false});
  await page.getByRole('option',{name:'核心观察',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#risk-scope').value==='1');
  await page.locator('#risk-analyze').click();await page.locator('#risk-title').fill('QA 资料 · 隔离测试');
  await page.locator('[data-select-for="risk-associate"]').click();await page.getByRole('option',{name:'平安银行 · 000001.SZ',exact:true}).click();
  await page.locator('#risk-published').fill('2026-10-01');await page.locator('#risk-url').fill('https://example.com/report');await page.locator('#risk-text').fill('用户测试资料：<img src=x onerror="alert(1)">\n资料内容包含待核实事项。');
  await page.locator('[data-select-for="risk-material-type"]').click();await page.locator('#risk-material-type-theme-menu').waitFor({state:'visible'});
  await page.waitForFunction(()=>!document.querySelector('#risk-material-type-theme-menu').getAnimations().some(a=>a.playState==='running'));
  await page.screenshot({path:`docs/visual-qa/risk-theme-dialog-${label}.png`,fullPage:false});await page.getByRole('option',{name:'公告',exact:true}).click();
  await page.locator('#risk-submit').click();await page.locator('#risk-detail').waitFor({state:'visible'});
  assert((await page.locator('#risk-detail-mode').textContent()).includes('隔离测试模型'));
  assert.equal(await page.locator('#risk-evidence img').count(),0);
  const link=page.locator('#risk-evidence a');assert.equal(await link.getAttribute('rel'),'noopener noreferrer');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no horizontal overflow');
  if(label==='mobile')assert(await page.evaluate(()=>document.querySelector('.risk-detail-actions').getBoundingClientRect().top>=document.querySelector('#risk-detail-title').getBoundingClientRect().bottom),'mobile actions do not cover detail heading');
  await page.screenshot({path:`docs/visual-qa/risk-${label}.png`,fullPage:true});
  await page.locator('#risk-follow').click();await page.getByText('信息不足 · 持续关注',{exact:true}).waitFor();
  await page.locator('#risk-research').click();await page.waitForFunction(()=>document.querySelector('#input-box').value.includes('000001.SZ'));
  await page.locator('#send-button').click();await page.locator('.markdown h2').waitFor();
  assert.equal(await page.locator('.markdown strong').textContent(),'股票资料');
  assert.equal(await page.locator('.markdown ul li').count(),2);assert.equal(await page.locator('.markdown table').count(),1);
  assert.equal(await page.locator('.markdown script').count(),0);assert.equal(await page.locator('.markdown a').count(),1);
  assert.equal(await page.evaluate(()=>Boolean(window.unsafeExecuted)),false);
  assert((await page.locator('.answer-sources').last().textContent()).includes('QA 测试夹具'));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:`docs/visual-qa/assistant-market-markdown-${label}.png`,fullPage:true});
  agentTimeout=true;await page.locator('#input-box').fill('QA 超时测试');await page.locator('#send-button').click();await page.getByText('本次研究未完成',{exact:true}).waitFor();
  assert((await page.locator('#session-meta').textContent()).includes('qa-timeout'));
  assert(!(await page.locator('#session-meta').textContent()).includes('已完成'));
  assert((await page.locator('.answer-sources').last().textContent()).includes('QA 测试夹具'));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:`docs/visual-qa/assistant-timeout-${label}.png`,fullPage:true});
  agentTimeout=false;await page.locator('#input-box').fill('QA 恢复测试');await page.locator('#send-button').click();await page.getByText('本次研究已完成',{exact:true}).waitFor();
  agentResearch=true;await page.locator('#input-box').fill('QA 答案展示');await page.locator('#send-button').click();await page.getByText('隔离测试：研究结论',{exact:true}).waitFor();
  assert.equal(await page.locator('.tool-tag').count(),0);
  assert.equal(await page.locator('.tool-record').count(),0);
  assert.equal(await page.locator('.source-card').count(),0);
  assert.equal(await page.locator('#session-meta').isVisible(),false);
  const latest=page.locator('.message').last();
  assert((await latest.textContent()).includes('行情时间'));assert((await latest.textContent()).includes('前复权'));
  for(const name of ['search_stocks','get_stock_quotes','get_kline_history','calculate_technical_indicators','analyze_price_volume'])assert(!(await latest.textContent()).includes(name));
  await page.evaluate(()=>{const area=document.querySelector('#messages-area');area.scrollTop=area.scrollHeight;});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:`docs/visual-qa/assistant-answer-only-${label}.png`,fullPage:true});
  await page.reload();await page.locator('#startBtn').click();await page.locator('#auth-email').fill('qa@example.test');await page.locator('#auth-password').fill('qa-password');await page.locator('#auth-submit').click();await page.locator('[data-page="risk"]').click();await page.locator('.risk-event').waitFor();await page.locator('.risk-event').click();await page.locator('#risk-detail').waitFor({state:'visible'});
  if(label==='mobile'){await page.locator('#risk-back').click();assert(await page.locator('.risk-events-panel').isVisible());}
  await page.locator('.risk-history-panel summary').click();await page.locator('#risk-history button').first().click();
  await page.getByText('正在查看历史第 1 版；处理状态以当前事件为准，历史结果不可修改。',{exact:true}).waitFor();
  assert.equal(await page.locator('#risk-viewed').isDisabled(),true);assert.equal(await page.locator('#risk-follow').isDisabled(),true);
  if(label==='mobile')await page.locator('#risk-back').click();
  for(const code of [429,503,504]){failure=code;await page.locator('#risk-analyze').click();await page.locator('#risk-text').fill('失败状态测试 '+code);await page.locator('#risk-submit').click();await page.locator('#risk-form-status.error').waitFor();await page.locator('#risk-submit:not([disabled])').waitFor();assert.equal(await page.locator('#risk-submit').isDisabled(),false);await page.locator('#risk-analysis-close').click();}
  await page.locator('#risk-search-input').fill('茅台');await page.getByRole('button',{name:'贵州茅台 · 600519.SH',exact:true}).click();
  await page.locator('#risk-auto-results .btn').first().waitFor();assert.equal(autoTask.scope.kind,'stock');assert.equal(autoTask.scope.symbol,'600519.SH');
  assert((await page.locator('#risk-auto-results').textContent()).includes('市场风险参考：信息不足'));
  assert((await page.locator('#risk-auto-results').textContent()).includes('板块：存在未完成资料'));
  assert((await page.locator('#risk-auto-range').textContent()).includes('不自动加入自选'));
  assert(collectCount>0,'production driver collects before model processing');
  assert((await page.locator('#risk-auto-results').textContent()).includes('首轮判断'));
  assert((await page.locator('#risk-auto-results').textContent()).includes('财报：存在未完成资料'));
  assert((await page.locator('#risk-auto-results').textContent()).includes('公告：读取失败'));
  assert((await page.locator('#risk-auto-results').textContent()).includes('继续全文核查'));
  await page.getByRole('button',{name:'查看分析',exact:true}).click();await page.getByText('QA财报原文夹具',{exact:true}).waitFor();
  assert((await page.locator('#risk-basis').textContent()).includes('趋势与量能依据展示'));
  assert((await page.locator('#risk-detail-mode').textContent()).includes('隔离测试模型'));
  assert((await page.locator('#risk-evidence').textContent()).includes('PDF文件页：5'));
  assert.equal((await page.locator('#input-box').inputValue()).length<=4000,true);
  if(label==='mobile')await page.locator('#risk-back').click();
  await page.locator('#risk-search-input').scrollIntoViewIfNeeded();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:`docs/visual-qa/risk-auto-${label}.png`,fullPage:false});
  await page.locator('#account-button').click();assert.equal(await page.locator('#risk-text').inputValue(),'');assert.equal(await page.locator('#risk-list .risk-event').count(),0);assert.equal(await page.locator('#risk-search-input').inputValue(),'');assert.equal(await page.locator('#risk-auto-results').textContent(),'');
  assert.deepEqual(errors,[],'production bundle has no browser exceptions');
  console.log(`PASS ${label}: production page, login, empty, analysis, safe sources, status, research, reload history, errors, logout, responsive layout`);
  await context.close();
 }
}finally{await browser?.close();await new Promise(r=>server.close(r));}
