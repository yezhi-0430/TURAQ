// Production bundle, isolated fixture API. Never uses real accounts or paid model calls.
import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/LENOVO/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const sandbox={window:{}};vm.createContext(sandbox);vm.runInContext(fs.readFileSync('frontend/settings.js','utf8'),sandbox);
const defaults=JSON.parse(JSON.stringify(sandbox.window.SettingsRules.defaults));
const adminDefaults={model_enabled:true,model_provider:'fake',model_name:'qwen-plus',model_user_daily_limit:20,model_user_minute_limit:2,model_site_daily_limit:200,model_max_output_tokens:1024,agent_max_output_tokens:4096,risk_max_output_tokens:1024,risk_document_output_tokens:4096,model_http_timeout_seconds:30,model_total_timeout_seconds:60,risk_document_http_timeout_seconds:120,risk_document_total_timeout_seconds:180,risk_document_chunk_chars:120000,market_user_minute_limit:120,market_ip_minute_limit:240,catalog_ip_minute_limit:120,paper_max_accounts:10};
const root=path.resolve('frontend/dist');
const server=createServer((req,res)=>{const file=path.resolve(root,'.'+decodeURIComponent(req.url.split('?')[0]==='/'?'/index.html':req.url.split('?')[0]));if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}try{res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));}catch{res.writeHead(404).end();}});
await new Promise(r=>server.listen(4176,'127.0.0.1',r));
let browser;
try{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 for(const [label,viewport,admin] of [['user-desktop',{width:1440,height:1000},false],['admin-desktop',{width:1440,height:1000},true],['admin-mobile',{width:390,height:844},true]]){
  const context=await browser.newContext({viewport,reducedMotion:'reduce'}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  let user={id:admin?1:2,email:admin?'admin@example.test':'researcher@example.test',is_admin:admin},prefs={...defaults,default_page:'settings'},version=0,values={...adminDefaults},globalVersion=0,failSave=null,secretEditable=false,audits=[],sessions=2,secretWrites=0,delayPersonal=false,delayAdmin=false,releaseRead;
  const session=()=>({user,csrf_token:'fixture-csrf',mail_configured:false,model_mode:values.model_enabled?values.model_provider:'disabled'});
  const personal=()=>({preferences:prefs,defaults,version,account:user});
  const global=()=>({values,defaults:adminDefaults,version:globalVersion,secrets:{dashscope_api_key:{configured:true,editable:secretEditable}},diagnostics:[{name:'database',status:'ok',detail:'数据库 SELECT 1 成功'},{name:'model',status:'configured',detail:'配置状态，未调用模型'},{name:'encryption',status:secretEditable?'ok':'unconfigured',detail:'加密配置状态'},{name:'mail',status:'unconfigured',detail:'尚未配置邮件'}]});
  await page.route('**/api/v1/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname.replace('/api/v1',''),method=req.method(),body=method==='GET'?{}:req.postDataJSON();
   const reply=(data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
   if(p==='/auth/session')return reply(session());
   if(p==='/auth/logout'){user=null;return reply(session());}
   if(p.startsWith('/admin/')&&!user?.is_admin)return reply({detail:'需要管理员权限'},403);
   if(!['GET','HEAD'].includes(method))assert.equal(req.headers()['x-csrf-token'],'fixture-csrf');
   if(p==='/settings'&&method==='GET'){const snapshot=structuredClone(personal());if(delayPersonal)await new Promise(resolve=>releaseRead=resolve);return reply(snapshot);}
   if(p==='/settings'&&method==='PUT'){
    if(failSave){const status=failSave;failSave=null;return reply({detail:status===409?'版本冲突':'测试保存失败'},status);}
    assert.equal(body.version,version);prefs=body.preferences;version++;return reply(personal());
   }
   if(p==='/admin/settings'&&method==='GET'){const snapshot=structuredClone(global());if(delayAdmin)await new Promise(resolve=>releaseRead=resolve);return reply(snapshot);}
   if(p==='/admin/settings'&&method==='PUT'){assert.equal(body.version,globalVersion);audits.unshift({actor_email:user.email,created_at:'2026-10-15T03:00:00Z',changes:{model_enabled:{before:values.model_enabled,after:body.values.model_enabled}}});values=body.values;globalVersion++;return reply(global());}
   if(p==='/admin/settings/secrets'){assert(secretEditable);assert.equal(body.version,globalVersion);secretWrites++;globalVersion++;return reply(global());}
   if(p==='/admin/settings/audit')return reply({items:audits});
   if(p==='/settings/sessions')return reply({sessions:Array.from({length:sessions},(_,i)=>({id:'safe-'+i,current:i===0,last_seen_at:'2026-10-15T03:00:00Z',expires_at:'2026-10-20T03:00:00Z'}))});
   if(p==='/settings/sessions/revoke-others'){sessions=1;return reply({detail:'其他会话已退出',count:1});}
   if(p==='/settings/password'){if(body.current_password!=='oldpass')return reply({detail:'当前密码不正确'},400);user=null;return reply({detail:'密码已修改'});}
   if(p==='/watchlists')return reply([]);
   if(p.startsWith('/market/'))return reply({quotes:[],stocks:[],points:[],source:'fixture',unavailable:[],checked_at:'2026-10-15T03:00:00Z'});
   if(p==='/risk/tasks'||p.startsWith('/risk/events')||p.startsWith('/risk/analyses'))return reply({items:[],total:0});
   if(p.startsWith('/risk/'))return reply({groups:[],stocks:[],counts:{},items:[],total:0});
   if(p==='/paper-trading/accounts')return reply({accounts:[]});
   return reply({detail:'Unmocked '+p},404);
  });
  const enter=async()=>{await page.evaluate(async()=>{await window.account.ready;window.dispatchEvent(new CustomEvent('account-login'));});await page.locator('#settings-page').waitFor({state:'visible'});await page.waitForFunction(()=>document.querySelector('#settings-version').textContent.includes('版本'));};
  const tab=async id=>{await page.locator('[data-settings-tab="'+id+'"]').click();};
  const set=async(id,value)=>{await page.locator('#'+id).evaluate((el,v)=>{if(el.type==='checkbox')el.checked=v;else el.value=String(v);el.dispatchEvent(new Event('change',{bubbles:true}));},value);};
  const save=async()=>{await page.locator('#settings-save').click();if(await page.locator('#settings-confirm-dialog').isVisible())await page.locator('#settings-confirm-ok').click();await page.waitForFunction(()=>document.querySelector('#settings-dirty').textContent==='所有设置已保存');};
  await page.goto('http://127.0.0.1:4176');await enter();
  assert.equal(await page.locator('#settings-role').textContent(),admin?'管理员工作台':'个人工作台');
  assert.equal(await page.locator('[data-settings-tab="model"]').isVisible(),admin);
  await set('pref-density','compact');await set('pref-reduce_motion',true);await save();
  assert.equal(await page.locator('html').getAttribute('data-density'),'compact');assert.equal(prefs.reduce_motion,true);
  delayPersonal=true;await page.locator('#settings-reload').click();
  assert.equal(await page.locator('#pref-density').isDisabled(),true,'reload must lock personal edits');
  assert.equal(await page.locator('#settings-save').isDisabled(),true,'reload cannot race a save');
  while(!releaseRead)await new Promise(r=>setTimeout(r,5));delayPersonal=false;releaseRead();releaseRead=null;
  await page.waitForFunction(()=>!document.querySelector('#pref-density').disabled);
  await tab('market');await set('pref-market_auto_refresh',false);await set('pref-market_refresh_seconds',30);await set('pref-chart_period','week');await set('pref-chart_adjustment','qfq');await save();
  assert.equal(await page.locator('#market-auto').isChecked(),false);
  await tab('research');await set('pref-research_send_key','ctrl_enter');await set('pref-research_max_rounds',7);await set('pref-risk_level','high');await set('pref-risk_status','following');await set('pref-risk_lookback_days',180);await save();
  assert.equal(await page.locator('#risk-level').inputValue(),'high');assert.equal(await page.locator('#risk-handling').inputValue(),'following');assert.equal(await page.locator('#risk-auto-days').inputValue(),'180');
  await tab('trading');await set('pref-paper_initial_capital',250000);await set('pref-paper_commission_rate',0.0001);await set('pref-paper_order_type','market');await save();
  assert.equal(await page.locator('#paper-type').inputValue(),'market');
  await set('pref-paper_initial_capital',350000);failSave=409;await page.locator('#settings-save').click();await page.waitForFunction(()=>document.querySelector('#settings-status').textContent.includes('草稿已保留'));assert.equal(prefs.paper_initial_capital,250000);assert.equal(await page.locator('#pref-paper_initial_capital').inputValue(),'350000');
  await page.locator('#settings-reload').click();await page.locator('#settings-confirm-ok').click();await page.waitForFunction(()=>document.querySelector('#pref-paper_initial_capital').value==='250000');
  await set('pref-paper_initial_capital',450000);failSave=503;await page.locator('#settings-save').click();await page.waitForFunction(()=>document.querySelector('#settings-status').textContent.includes('测试保存失败'));assert.equal(prefs.paper_initial_capital,250000);await save();
  const downloadPromise=page.waitForEvent('download');await page.locator('#settings-export').click();const dl=await downloadPromise;const exported=JSON.parse(fs.readFileSync(await dl.path(),'utf8'));assert.equal(exported.kind,'turaq-personal-settings');assert.equal(exported.preferences.paper_initial_capital,450000);assert(!JSON.stringify(exported).includes('@'));
  const imported={kind:'turaq-personal-settings',schema_version:1,preferences:{...defaults,default_page:'settings',paper_initial_capital:600000}};
  await page.locator('#settings-file').setInputFiles({name:'preferences.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(imported))});await page.waitForFunction(()=>document.querySelector('#settings-status').textContent.includes('草稿'));assert.equal(prefs.paper_initial_capital,450000);await save();assert.equal(prefs.paper_initial_capital,600000);
  await page.reload();await enter();assert.equal(await page.locator('#pref-paper_initial_capital').inputValue(),'600000','saved values survive reload');
  await page.screenshot({path:'docs/visual-qa/settings-'+label+'.png',fullPage:true});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'no horizontal overflow');
  if(admin){
   await tab('model');await page.waitForFunction(()=>!document.querySelector('#global-model_name').disabled);assert.equal(await page.locator('#settings-api-key').isDisabled(),true);
   delayAdmin=true;await page.locator('#settings-reload').click();
   assert.equal(await page.locator('#global-model_name').isDisabled(),true,'reload must lock administrator edits');
   while(!releaseRead)await new Promise(r=>setTimeout(r,5));delayAdmin=false;releaseRead();releaseRead=null;
   await page.waitForFunction(()=>!document.querySelector('#global-model_name').disabled);
   await set('global-model_enabled',false);await save();assert.equal(values.model_enabled,false);assert.equal(await page.locator('#model-mode').textContent(),'模型调用已关闭');
   secretEditable=true;await page.locator('#settings-reload').click();await page.waitForFunction(()=>!document.querySelector('#settings-api-key').disabled);await page.locator('#settings-api-key').fill('synthetic-secret-not-real');await page.locator('#settings-secret-save').click();await page.locator('#settings-confirm-ok').click();await page.waitForFunction(()=>document.querySelector('#settings-status').textContent.includes('密钥配置已更新'));assert.equal(secretWrites,1);assert.equal(await page.locator('#settings-api-key').inputValue(),'');
   await tab('runtime');assert((await page.locator('#settings-diagnostics').textContent()).includes('数据库'));
   await tab('audit');await page.waitForFunction(()=>document.querySelector('#settings-audit').textContent.includes('admin@example.test'));assert(!(await page.locator('#settings-audit').textContent()).includes('synthetic-secret'));
   await tab('model');await page.screenshot({path:'docs/visual-qa/settings-model-'+label+'.png',fullPage:true});
   user={...user,is_admin:false};await page.evaluate(()=>window.apiClient.bootstrap());
   assert.equal(await page.locator('[data-settings-tab="model"]').isVisible(),false,'role downgrade removes privileged settings immediately');
   assert.equal(await page.locator('#settings-admin-form').isVisible(),false);
  }
  await tab('security');await page.waitForFunction(()=>document.querySelectorAll('.settings-session').length===2);await page.locator('#settings-revoke-others').click();await page.locator('#settings-confirm-ok').click();await page.waitForFunction(()=>document.querySelectorAll('.settings-session').length===1);
  await page.locator('#settings-current-password').fill('wrongpass');await page.locator('#settings-new-password').fill('newpass1');await page.locator('#settings-repeat-password').fill('newpass1');await page.locator('#settings-password-save').click();await page.locator('#settings-confirm-ok').click();await page.waitForFunction(()=>document.querySelector('#settings-status').textContent.includes('当前密码不正确'));
  await page.locator('#settings-current-password').fill('oldpass');await page.locator('#settings-new-password').fill('newpass1');await page.locator('#settings-repeat-password').fill('newpass1');await page.locator('#settings-password-save').click();await page.locator('#settings-confirm-ok').click();await page.waitForFunction(()=>document.querySelector('#auth-status').textContent.includes('密码已更新'));
  assert.equal(await page.locator('#app').isVisible(),false);assert.equal(await page.locator('#settings-api-key').inputValue(),'');assert.equal(await page.locator('#pref-paper_initial_capital').inputValue(),'1000000','private drafts reset after session invalidation');
  assert.deepEqual(errors,[]);await context.close();console.log('PASS: '+label+' preferences, persistence, import/export, conflict/errors, role UI, security, layout');
 }
}finally{await browser?.close();await new Promise(r=>server.close(r));}
