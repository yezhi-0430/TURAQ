/* Account-scoped settings. No credentials or private preferences in browser storage. */
(() => {
 'use strict';
 const personalFields = [
  ['default_page','workspace','默认进入页面','select','agent',[['agent','AI 研究助手'],['dashboard','行情驾驶舱'],['watchlist','自选管理'],['risk','风险监控'],['trading','模拟交易'],['settings','系统设置']],'下次登录首次进入工作台时生效。'],
  ['density','workspace','界面密度','select','comfortable',[['comfortable','舒适'],['compact','紧凑']],'调整工作台卡片与表格的留白。'],
  ['reduce_motion','workspace','减少界面动画','boolean',false,null,'关闭页面切换与装饰动画。'],
  ['watchlist_sort','workspace','自选股票排序','select','default',[['default','添加顺序'],['name','股票名称'],['symbol','证券代码']],'适用于自选管理的组内列表。'],
  ['market_auto_refresh','market','自动刷新行情','boolean',true,null,'应用到行情驾驶舱和行情详情；后台标签页暂停刷新。'],
  ['market_refresh_seconds','market','行情刷新间隔','number-select',10,[[10,'10 秒'],[30,'30 秒'],[60,'60 秒']],'报价按此间隔刷新，图表至少间隔 30 秒。'],
  ['chart_period','market','默认图表周期','select','minute',[['minute','分时'],['day','日 K'],['week','周 K'],['month','月 K']],'下次打开行情详情时生效。'],
  ['chart_adjustment','market','默认复权方式','select','none',[['none','不复权'],['qfq','前复权'],['hfq','后复权']],'适用于个股 K 线，指数保持不复权。'],
  ['research_send_key','research','发送快捷键','select','enter',[['enter','Enter 发送'],['ctrl_enter','Ctrl / ⌘ + Enter 发送']],'Shift + Enter 始终换行。'],
  ['research_max_rounds','research','研究轮数上限','number',15,[1,15,1],'每次新请求的最大工具研究轮数，仍受全站额度约束。'],
  ['risk_level','research','默认风险等级筛选','select','all',[['all','全部等级'],['high','高风险'],['medium','中风险'],['low','低风险'],['unknown','信息不足']],'保存后应用到风险监控列表。'],
  ['risk_status','research','默认处理状态筛选','select','all',[['all','全部状态'],['unread','未查看'],['viewed','已查看'],['following','持续关注']],'只改变列表筛选，不修改已保存的风险结论。'],
  ['risk_lookback_days','research','公告回溯范围','number-select',90,[[30,'最近 30 个自然日'],[90,'最近 90 个自然日'],[180,'最近 180 个自然日']],'应用到后续发起的股票风险分析。'],
  ['paper_auto_refresh','trading','模拟账户自动刷新','boolean',true,null,'页面可见且开市时自动刷新；后台撮合不受此开关影响。'],
  ['paper_refresh_seconds','trading','账户刷新间隔','number-select',15,[[15,'15 秒'],[30,'30 秒'],[60,'60 秒']],'用于持仓、委托和成交刷新。'],
  ['paper_initial_capital','trading','新账户初始资金（元）','number',1000000,[10000,100000000,0.01],'仅作为新建账户的初始值，不改变现有账户。'],
  ['paper_commission_rate','trading','新账户佣金费率','number',0.0003,[0,0.003,0.000001],'0.0003 表示万分之三；印花税等继续按交易规则计算。'],
  ['paper_min_commission','trading','新账户最低佣金（元）','number',5,[0,100,0.01],'仅影响新建账户，现有成交与账本保持原值。'],
  ['paper_order_type','trading','默认委托类型','select','limit',[['limit','限价委托'],['market','市价委托']],'作为委托表单初始值，每笔交易仍需确认提交。']
 ];
 const defaults=Object.fromEntries(personalFields.map(f=>[f[0],f[4]]));
 function validatePreferences(value){
  if(!value||typeof value!=='object'||Array.isArray(value))throw Error('配置必须为有效的设置对象。');
  if(Object.keys(value).some(key=>!Object.hasOwn(defaults,key)))throw Error('配置包含无法识别或不允许导入的字段。');
  const result={...defaults,...value};
  for(const [key,,label,type,,constraint] of personalFields){
   const v=result[key];
   if(type==='boolean'&&typeof v!=='boolean')throw Error(label+'必须为开关值。');
   if((type==='select'||type==='number-select')&&!constraint.some(([option])=>option===v))throw Error(label+'的选项无效。');
   if(type==='number'&&(typeof v!=='number'||!Number.isFinite(v)||v<constraint[0]||v>constraint[1]||(constraint[2]===1&&!Number.isInteger(v))))throw Error(label+'超出允许范围。');
  }
  return result;
 }
 function importPreferences(raw){
  if(typeof raw!=='string'||raw.length>65536)throw Error('配置文件须为不超过 64 KB 的 JSON。');
  let data;try{data=JSON.parse(raw);}catch{throw Error('无法读取 JSON，请选择导出的个人配置文件。');}
  if(data?.kind!=='turaq-personal-settings'||data.schema_version!==1)throw Error('文件类型或版本不兼容，请使用个人配置导出文件。');
  if(!data.preferences)throw Error('文件缺少个人配置。');
  return validatePreferences(data.preferences);
 }
 function shouldSend(event,key){return event.key==='Enter'&&!event.isComposing&&!event.shiftKey&&(key!=='ctrl_enter'||Boolean(event.ctrlKey||event.metaKey));}
 function sortStocks(items,sort){const copy=[...items];if(sort==='name'||sort==='symbol')copy.sort((a,b)=>String(a[sort]||'').localeCompare(String(b[sort]||''),'zh-CN'));return copy;}
 window.SettingsRules={defaults,validatePreferences,importPreferences,exportPreferences:preferences=>({kind:'turaq-personal-settings',schema_version:1,preferences:validatePreferences(preferences)}),shouldSend,sortStocks};
 if(typeof document==='undefined')return;
 const $=id=>document.getElementById(id),api=window.apiClient,host=$('settings-page');
 if(!host)return;
 const adminFields=[
  ['model_enabled','model','启用模型服务','boolean',true,null,'关闭后拒绝新的模型请求，历史结果仍可查看。'],
  ['model_provider','model','模型供应商','select','qwen',[['qwen','Qwen 在线模型'],['fake','离线测试模型']],'离线模式用于验证流程，不生成真实研究结论。'],
  ['model_name','model','模型名称','text','qwen-plus',null,'例如 qwen-plus；模型名称需由当前服务支持。'],
  ['agent_max_output_tokens','model','研究助手输出上限','number',4096,[1,8192,1],'每次模型调用的输出 token 上限。'],
  ['risk_max_output_tokens','model','风险摘要输出上限','number',1024,[1,8192,1],'用于短资料风险摘要。'],
  ['risk_document_output_tokens','model','全文阅读输出上限','number',4096,[1,8192,1],'用于财报及公告全文分批阅读。'],
  ['model_max_output_tokens','model','通用模型输出上限','number',1024,[1,8192,1],'未指定业务用途时采用的输出预算。'],
  ['model_user_daily_limit','limits','单用户 24 小时调用上限','number',20,[1,10000,1],'滚动时间窗口，按实际模型调用计数。'],
  ['model_user_minute_limit','limits','单用户每分钟调用上限','number',2,[1,1000,1],'约束研究与风险分析中的模型调用。'],
  ['model_site_daily_limit','limits','全站 24 小时调用上限','number',200,[1,100000,1],'全站共享额度；调整限额不清空已有用量。'],
  ['market_user_minute_limit','limits','单用户行情请求 / 分钟','number',120,[1,10000,1],'行情读取的后端请求预算。'],
  ['market_ip_minute_limit','limits','单 IP 行情请求 / 分钟','number',240,[1,10000,1],'同一网络出口共享此预算。'],
  ['catalog_ip_minute_limit','limits','单 IP 股票搜索 / 分钟','number',120,[1,10000,1],'股票名称与代码查询的请求预算。'],
  ['paper_max_accounts','limits','每位用户模拟账户上限','number',10,[1,100,1],'仅限制新建账户，不删除已存在的账户。'],
  ['model_http_timeout_seconds','runtime','普通模型单次请求超时（秒）','number',30,[1,30,1],'单次 HTTP 请求的等待上限。'],
  ['model_total_timeout_seconds','runtime','普通研究总时限（秒）','number',60,[1,120,1],'整个研究请求的总处理时限。'],
  ['risk_document_http_timeout_seconds','runtime','全文模型请求超时（秒）','number',120,[1,300,1],'用于较长的文档阅读请求。'],
  ['risk_document_total_timeout_seconds','runtime','全文阅读总时限（秒）','number',180,[1,600,1],'单个全文处理阶段的总时限。'],
  ['risk_document_chunk_chars','runtime','全文阅读分批字符数','number',120000,[20000,250000,1000],'对后续处理的文档分批生效。']
 ];
 const tabs=[['workspace','工作台偏好','01'],['market','行情与图表','02'],['research','研究与风险','03'],['trading','模拟交易','04'],['security','账号与安全','05'],['model','模型服务','A1'],['limits','配额与访问','A2'],['runtime','运行与诊断','A3'],['audit','变更记录','A4']];
 const titles={workspace:['让工作台适合你的习惯','个人设置随账号保存，下次登录自动载入。'],market:['从熟悉的行情视角开始','刷新频率、图表周期和复权口径统一管理。'],research:['研究节奏，由你设定','配置输入习惯与默认筛选，研究结论仍基于实际资料。'],trading:['为下一次模拟做好准备','新账户参数与委托默认值，不改动历史交易。'],security:['管理你的账号与登录','密码修改后所有登录失效，其他会话可单独退出。'],model:['配置全站模型服务','仅管理员可修改。保存后用于后续请求，进行中的请求保留原配置。'],limits:['控制服务用量与访问频率','全站策略由后端执行，普通用户无法通过个人设置绕过。'],runtime:['查看运行状态，调整处理预算','诊断展示配置状态与数据库连通性，不产生付费模型调用。'],audit:['每一次修改都有记录','记录全站配置修改人、时间与变更字段；密钥只记录更新动作。']};
 let preferences={...defaults},personal=null,globalConfig=null,loading=null,adminLoading=null,userId=null,knownRole=null,generation=0,busy=false,tab='workspace',personalDirty=false,adminDirty=false,visible=false,auditOffset=0;
 const isAdmin=()=>Boolean(api.session.user?.is_admin),isGlobal=()=>['model','limits','runtime','audit'].includes(tab);
 const node=(tag,cls='',text)=>{const n=document.createElement(tag);n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 function button(label,action,cls='btn'){const b=node('button',cls,label);b.type='button';b.addEventListener('click',action);return b;}
 function note(text,error=false){$('settings-status').textContent=text;$('settings-status').className='settings-status'+(error?' error':'');}
 function build(){
  host.innerHTML=`<div class="settings-summary"><div><span class="eyebrow">YOUR WORKSPACE / PREFERENCES</span><h2>每一处设置，都为你的研究服务</h2><p id="settings-account-line"></p></div><span class="settings-role" id="settings-role"></span></div>
   <div class="settings-layout"><nav id="settings-nav" class="settings-nav" aria-label="设置分类"></nav><div class="settings-body"><header class="settings-section-heading"><span class="eyebrow" id="settings-scope"></span><h2 id="settings-title"></h2><p id="settings-subtitle"></p></header>
   <p id="settings-status" class="settings-status" role="status" aria-live="polite"></p>
   <form id="settings-personal-form"><div id="settings-personal-fields"></div></form><form id="settings-admin-form" hidden><div id="settings-admin-fields"></div></form>
   <section id="settings-security" hidden></section><section id="settings-secrets" hidden></section><section id="settings-diagnostics" hidden></section><section id="settings-audit" hidden></section>
   <footer class="settings-footer" id="settings-footer"><div><strong id="settings-dirty"></strong><small id="settings-version"></small></div><div class="settings-footer-actions"><button type="button" class="btn" id="settings-reload">重新加载</button><button type="button" class="btn" id="settings-reset">恢复默认</button><button type="button" class="btn primary" id="settings-save">保存设置</button></div></footer>
   <div class="settings-transfer" id="settings-transfer"><span>配置备份</span><button type="button" class="settings-link" id="settings-export">导出 JSON</button><button type="button" class="settings-link" id="settings-import">导入个人配置</button><input id="settings-file" type="file" accept=".json,application/json" hidden></div>
   </div></div><dialog id="settings-confirm-dialog" class="settings-dialog" aria-labelledby="settings-confirm-title"><h2 id="settings-confirm-title">确认操作</h2><p id="settings-confirm-text"></p><div class="settings-footer-actions"><button class="btn" type="button" id="settings-confirm-cancel">取消</button><button class="btn primary" type="button" id="settings-confirm-ok">确认</button></div></dialog>`;
  for(const [id,label,num] of tabs){const b=button('',()=>selectTab(id),'settings-nav-item');b.dataset.settingsTab=id;b.append(node('span','settings-tab-number',num),node('span','',label));$('settings-nav').append(b);}
  for(const [label,fields,target,prefix] of [['personal',personalFields,'settings-personal-fields','pref'],['admin',adminFields,'settings-admin-fields','global']]){
   for(const group of new Set(fields.map(f=>f[1]))){const box=node('section','settings-fields');box.dataset.settingsGroup=group;box.setAttribute('aria-label',titles[group][0]);for(const field of fields.filter(f=>f[1]===group))box.append(fieldRow(field,prefix));$(target).append(box);}
   $('settings-'+label+'-form').addEventListener('input',()=>{if(label==='personal')personalDirty=true;else adminDirty=true;controls();});
   $('settings-'+label+'-form').addEventListener('change',()=>{if(label==='personal')personalDirty=true;else adminDirty=true;controls();});
   $('settings-'+label+'-form').addEventListener('submit',e=>{e.preventDefault();save();});
  }
  buildSecurity();buildSecrets();
  $('settings-save').addEventListener('click',save);
  $('settings-reset').addEventListener('click',async()=>{if(!await confirmAction(isGlobal()?'恢复所有全站配置为部署默认值？确认后会填入表单，点击保存后才会生效。':'恢复所有个人设置为默认值？确认后会填入表单，点击保存后才会生效。'))return;fill(isGlobal()?adminFields:personalFields,isGlobal()?'global':'pref',isGlobal()?globalConfig.defaults:personal.defaults);if(isGlobal())adminDirty=true;else personalDirty=true;note('已填入默认值，检查后点击“保存设置”。');controls();});
  $('settings-reload').addEventListener('click',async()=>{if((isGlobal()?adminDirty:personalDirty)&&!await confirmAction('重新加载将放弃本地未保存的修改，继续吗？'))return;await (isGlobal()?loadAdmin(true):ensureLoaded(true));});
  $('settings-export').addEventListener('click',()=>{const global=isGlobal(),data=global?{kind:'turaq-global-settings',schema_version:1,values:globalConfig.values}:window.SettingsRules.exportPreferences(preferences);download(data,global?'turaq-global-settings.json':'turaq-personal-settings.json');note('已导出已保存的配置，不包含未保存的草稿、账号信息和密钥。');});
  $('settings-import').addEventListener('click',()=>$('settings-file').click());
  $('settings-file').addEventListener('change',async()=>{const file=$('settings-file').files[0];$('settings-file').value='';if(!file)return;const mine=generation;try{if(file.size>65536)throw Error('配置文件不能超过 64 KB。');const next=importPreferences(await file.text());if(mine!==generation)return;fill(personalFields,'pref',next);personalDirty=true;note('已导入个人配置草稿。请检查各分类，然后保存。');controls();}catch(e){if(mine===generation)note(e.message,true);}});
  window.addEventListener('beforeunload',event=>{if(personalDirty||adminDirty){event.preventDefault();event.returnValue='';}});
 }
 function fieldRow([key,,label,type,value,constraint,help],prefix){
  const row=node('div','settings-field'+(type==='boolean'?' settings-toggle':'')),copy=node('div','settings-field-copy'),caption=node('label','',label);caption.htmlFor=prefix+'-'+key;copy.append(caption,node('p','',help));row.append(copy);
  let input;if(type==='select'||type==='number-select'){input=node('select');for(const [val,text] of constraint){const o=node('option','',text);o.value=String(val);input.append(o);}}
  else {input=node('input');input.type=type==='boolean'?'checkbox':type==='number'?'number':'text';if(type==='number'){[input.min,input.max,input.step]=constraint.map(String);input.inputMode='decimal';}if(type==='text')input.maxLength=120;}
  input.id=prefix+'-'+key;input.name=key;if(type==='boolean'){input.checked=value;input.setAttribute('role','switch');}else {input.value=String(value);input.required=true;}
  input.setAttribute('aria-describedby',prefix+'-'+key+'-help');copy.lastChild.id=prefix+'-'+key+'-help';row.append(input);return row;
 }
 function fill(fields,prefix,data){for(const [key,,,type] of fields){const input=$(prefix+'-'+key);if(type==='boolean')input.checked=Boolean(data[key]);else input.value=String(data[key]??'');}}
 function read(fields,prefix){return Object.fromEntries(fields.map(([key,,,type])=>{const el=$(prefix+'-'+key);return [key,type==='boolean'?el.checked:type==='number'||type==='number-select'?Number(el.value):el.value.trim()];}));}
 function controls(){
  const global=isGlobal(),loaded=global?Boolean(globalConfig):Boolean(personal),dirty=global?adminDirty:personalDirty,pending=global?Boolean(adminLoading):Boolean(loading);
  for(const id of ['settings-save','settings-reset','settings-export'])$(id).disabled=busy||pending||!loaded;
  $('settings-reload').disabled=busy||pending; $('settings-import').disabled=busy||Boolean(loading)||!personal;
  $('settings-save').disabled=busy||pending||!loaded||!dirty;
  for(const [id,ready,waiting] of [['settings-personal-form',personal,loading],['settings-admin-form',globalConfig,adminLoading]])$(id).querySelectorAll('input,select').forEach(el=>el.disabled=busy||Boolean(waiting)||!ready);
  $('settings-dirty').textContent=busy?'正在处理…':pending?'正在加载配置…':!loaded?'等待配置载入':dirty?'有未保存的修改':'所有设置已保存';
  $('settings-version').textContent=loaded?(global?'全站配置':'个人配置')+' · 版本 '+(global?globalConfig.version:personal.version):'加载失败时可点击重新加载';
  host.setAttribute('aria-busy',String(busy||pending));
  renderSecretState();
 }
 async function selectTab(next){
  if(['model','limits','runtime','audit'].includes(next)&&!isAdmin())return;
  tab=next;
  for(const b of $('settings-nav').children){const active=b.dataset.settingsTab===tab;b.classList.toggle('active',active);b.setAttribute('aria-current',active?'page':'false');b.hidden=['model','limits','runtime','audit'].includes(b.dataset.settingsTab)&&!isAdmin();}
  $('settings-title').textContent=titles[tab][0];$('settings-subtitle').textContent=titles[tab][1];$('settings-scope').textContent=isGlobal()?'ADMIN / 全站管理':'PERSONAL / 仅对你的账号生效';
  $('settings-personal-form').hidden=isGlobal()||tab==='security';$('settings-admin-form').hidden=!['model','limits','runtime'].includes(tab);
  for(const box of host.querySelectorAll('[data-settings-group]'))box.hidden=box.dataset.settingsGroup!==tab;
  for(const [id,show] of [['security',tab==='security'],['secrets',tab==='model'],['diagnostics',tab==='runtime'],['audit',tab==='audit']])$('settings-'+id).hidden=!show;
  $('settings-footer').hidden=['security','audit'].includes(tab);$('settings-transfer').hidden=['security','audit'].includes(tab);$('settings-import').hidden=isGlobal();
  note('');controls();
  if(isGlobal())await loadAdmin();
  if(tab==='security')await loadSessions();
  if(tab==='audit'){auditOffset=0;await loadAudit();}
 }
 function apply(data){
  preferences=validatePreferences(data);
  document.documentElement.dataset.density=preferences.density;document.documentElement.dataset.reduceMotion=String(preferences.reduce_motion);
  for(const name of ['marketDashboard','watchlistManager','riskWorkbench','paperTrading'])window[name]?.applyPreferences?.(preferences);
  const hint=$('research-key-hint');if(hint)hint.textContent=preferences.research_send_key==='enter'?'Enter 发送 · Shift + Enter 换行':'Ctrl / ⌘ + Enter 发送 · Enter 换行';
  window.dispatchEvent(new CustomEvent('preferences-changed',{detail:{...preferences}}));
 }
 async function ensureLoaded(force=false){
  if(!api.session.user)return null;
  if(personal&&!force)return personal;
  if(loading)return loading;
  const mine=generation,id=api.session.user.id;userId=id;knownRole=isAdmin();
  loading=(async()=>{try{const data=await api.request('/settings');if(mine!==generation||api.session.user?.id!==id)return null;personal=data;personalDirty=false;apply(data.preferences);fill(personalFields,'pref',data.preferences);$('settings-account-line').textContent=api.session.user.email+' · 配置随账号同步';$('settings-role').textContent=isAdmin()?'管理员工作台':'个人工作台';note('个人设置已载入。');return data;}catch(e){if(mine===generation)note('个人设置加载失败：'+e.message,true);return null;}finally{if(mine===generation){loading=null;controls();}}})();
  controls();return loading;
 }
 async function loadAdmin(force=false){
  if(!isAdmin())return null;if(globalConfig&&!force)return globalConfig;if(adminLoading)return adminLoading;
  const mine=generation;
  adminLoading=(async()=>{try{const data=await api.request('/admin/settings');if(mine!==generation||!isAdmin())return null;globalConfig=data;adminDirty=false;fill(adminFields,'global',data.values);renderDiagnostics();renderSecretState();return data;}catch(e){if(mine===generation)note('全站设置加载失败：'+e.message,true);return null;}finally{if(mine===generation){adminLoading=null;controls();}}})();controls();return adminLoading;
 }
 async function save(){
  if(busy)return;const global=isGlobal(),current=global?globalConfig:personal;if(!current||(global?adminLoading:loading))return;
  const form=$(global?'settings-admin-form':'settings-personal-form');
  // Hidden categories are validated too; reveal the category containing an invalid field.
  const invalid=[...form.querySelectorAll('input,select')].find(el=>!el.checkValidity());
  if(invalid){await selectTab(invalid.closest('[data-settings-group]').dataset.settingsGroup);invalid.reportValidity();return;}
  let values;try{values=global?read(adminFields,'global'):validatePreferences(read(personalFields,'pref'));}catch(e){note(e.message,true);return;}
  if(global&&!await confirmAction('保存后将影响所有用户的新请求。确认应用这份全站配置吗？'))return;
  const mine=generation;busy=true;controls();form.querySelectorAll('input,select').forEach(el=>el.disabled=true);
  try{
   const data=await api.request(global?'/admin/settings':'/settings',{method:'PUT',body:{version:current.version,[global?'values':'preferences']:values}});
   if(mine!==generation)return;
   if(global){globalConfig=data;adminDirty=false;fill(adminFields,'global',data.values);renderDiagnostics();renderSecretState();$('model-mode').textContent=!data.values.model_enabled?'模型调用已关闭':data.values.model_provider==='qwen'?'Qwen 在线模型':'隔离测试模型';}
   else{personal=data;personalDirty=false;fill(personalFields,'pref',data.preferences);apply(data.preferences);}
   note(global?'全站配置已保存，后续请求将使用新配置。':'个人设置已保存并应用。');
  }catch(e){if(mine===generation)note(e.status===409?'配置已在其他页面被修改。你的草稿已保留，请记下修改，再重新加载最新版本。':e.message,true);}
  finally{if(mine===generation){busy=false;form.querySelectorAll('input,select').forEach(el=>el.disabled=false);controls();}}
 }
 function download(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=node('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 let resolveConfirmation=null;
 function confirmAction(text){
  if(resolveConfirmation)return Promise.resolve(false);
  $('settings-confirm-text').textContent=text;$('settings-confirm-dialog').showModal();
  return new Promise(resolve=>{resolveConfirmation=resolve;});
 }
 function finishConfirmation(value){$('settings-confirm-dialog').close();const resolve=resolveConfirmation;resolveConfirmation=null;resolve?.(value);}
 function buildSecurity(){
  const box=$('settings-security');box.innerHTML=`<section class="settings-card"><h3>账号信息</h3><dl id="settings-profile" class="settings-facts"></dl></section><section class="settings-card"><h3>修改密码</h3><p class="settings-help">遵循现有账号规则：6–15 个字符，空格不会被自动裁剪。修改成功后需要重新登录。</p><form id="settings-password-form" class="settings-password-form"><label>当前密码<input id="settings-current-password" type="password" autocomplete="current-password" required maxlength="1024"></label><label>新密码<input id="settings-new-password" type="password" autocomplete="new-password" required minlength="6" maxlength="15"></label><label>确认新密码<input id="settings-repeat-password" type="password" autocomplete="new-password" required minlength="6" maxlength="15"></label><button class="btn primary" type="submit" id="settings-password-save">更新密码</button></form></section><section class="settings-card"><div class="settings-card-heading"><h3>有效登录会话</h3><button type="button" class="btn" id="settings-sessions-refresh">刷新</button></div><p class="settings-help">时间按 Asia/Shanghai 展示；系统不会将登录凭据发送到页面。</p><div id="settings-sessions"></div><button type="button" class="btn settings-danger" id="settings-revoke-others">退出其他所有会话</button></section>`;
  $('settings-password-form').addEventListener('submit',async e=>{
   e.preventDefault();if(busy)return;const current=$('settings-current-password').value,next=$('settings-new-password').value;
   if(next!==$('settings-repeat-password').value){note('两次输入的新密码不一致。',true);return;}
   if(!window.AuthRules.validPassword(next)){note('新密码必须为 6–15 个字符。',true);return;}
   if(!await confirmAction('修改密码将退出包括当前登录在内的所有会话。确认继续吗？'))return;
   const mine=generation;busy=true;$('settings-password-save').disabled=true;
   try{await api.request('/settings/password',{method:'POST',body:{current_password:current,new_password:next}});if(mine!==generation)return;api.invalidate();await api.bootstrap();window.account.show('login');$('auth-status').textContent='密码已更新，所有旧会话已退出，请使用新密码登录。';}
   catch(error){if(mine===generation)note(error.message,true);}
   finally{for(const id of ['settings-current-password','settings-new-password','settings-repeat-password'])$(id).value='';if(mine===generation){busy=false;$('settings-password-save').disabled=false;controls();}}
  });
  $('settings-sessions-refresh').addEventListener('click',loadSessions);
  $('settings-revoke-others').addEventListener('click',async()=>{if(busy||!await confirmAction('退出该账号的其他所有登录会话？当前会话会保留。'))return;const mine=generation;busy=true;$('settings-revoke-others').disabled=true;try{const data=await api.request('/settings/sessions/revoke-others',{method:'POST',body:{}});if(mine!==generation)return;note(data.detail||'其他会话已退出。');await loadSessions();}catch(e){if(mine===generation)note(e.message,true);}finally{if(mine===generation){busy=false;$('settings-revoke-others').disabled=false;controls();}}});
 }
 const date=value=>value?new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'未记录';
 async function loadSessions(){
  if(!api.session.user)return;const mine=generation;const profile=$('settings-profile');profile.replaceChildren();for(const [key,value] of [['登录邮箱',api.session.user.email],['账号权限',isAdmin()?'管理员':'普通用户'],['时区','Asia/Shanghai（北京时间）']]){const item=node('div');item.append(node('dt','',key),node('dd','',value));profile.append(item);}
  $('settings-sessions').textContent='正在读取有效会话…';$('settings-sessions-refresh').disabled=true;
  try{const data=await api.request('/settings/sessions');if(mine!==generation)return;const box=$('settings-sessions');box.replaceChildren();for(const session of data.sessions){const row=node('div','settings-session');row.append(node('strong','',session.current?'当前会话':'其他登录会话'),node('span','', '最近活动 '+date(session.last_seen_at)),node('small','', '到期 '+date(session.expires_at)));box.append(row);}if(!data.sessions.length)box.textContent='暂无有效会话。';}
  catch(e){if(mine===generation)$('settings-sessions').textContent=e.message;}
  finally{if(mine===generation)$('settings-sessions-refresh').disabled=false;}
 }
 function buildSecrets(){
  $('settings-secrets').innerHTML=`<section class="settings-card"><h3>模型 API 密钥</h3><p id="settings-secret-state" class="settings-help"></p><form id="settings-secret-form" class="settings-secret-form"><label>更新密钥<input id="settings-api-key" type="password" autocomplete="new-password" maxlength="4096" placeholder="输入新密钥；不会回显已保存的密钥"></label><button type="submit" class="btn" id="settings-secret-save">加密保存密钥</button><button type="button" class="btn" id="settings-secret-clear">恢复部署密钥</button></form><p class="settings-help">密钥单独保存，不进入配置导出或变更详情。恢复部署密钥会移除数据库中的覆盖值。</p></section>`;
  $('settings-secret-form').addEventListener('submit',e=>{e.preventDefault();const value=$('settings-api-key').value;if(!value.trim()){note('请输入新密钥；恢复部署值请使用旁边的按钮。',true);return;}saveSecret(value);});
  $('settings-secret-clear').addEventListener('click',()=>saveSecret(''));
 }
 function renderSecretState(){const state=globalConfig?.secrets?.dashscope_api_key;const editable=Boolean(state?.editable);$('settings-secret-state').textContent=(state?.configured?'已有密钥配置，原文不会显示。':'尚未配置模型密钥。')+(editable?' 支持加密在线更新。':' 在线更新需要先在部署环境配置 SETTINGS_ENCRYPTION_KEY（Fernet 密钥）并重启服务。');for(const id of ['settings-api-key','settings-secret-save','settings-secret-clear'])$(id).disabled=!editable||busy||Boolean(adminLoading);}
 async function saveSecret(value){
  if(busy||adminLoading||!globalConfig)return;if(adminDirty){note('请先保存或重新加载全站配置，再更新密钥。',true);return;}
  if(!await confirmAction(value?'更新全站模型密钥？后续请求将使用新密钥。':'移除已保存的密钥覆盖值并恢复部署密钥？'))return;
  const mine=generation;busy=true;controls();for(const id of ['settings-secret-save','settings-secret-clear'])$(id).disabled=true;
  try{const data=await api.request('/admin/settings/secrets',{method:'POST',body:{dashscope_api_key:value,version:globalConfig.version}});if(mine!==generation)return;globalConfig=data;$('settings-api-key').value='';renderDiagnostics();note('密钥配置已更新。');}
  catch(e){if(mine===generation)note(e.message,true);}
  finally{if(mine===generation){busy=false;renderSecretState();controls();}}
 }
 function renderDiagnostics(){
  const box=$('settings-diagnostics');box.replaceChildren();const card=node('section','settings-card');card.append(node('h3','','服务诊断'));const list=node('div','settings-diagnostic-grid');
  for(const item of globalConfig?.diagnostics||[]){const row=node('article','settings-diagnostic'),pill=node('span','settings-diagnostic-state',({ok:'正常',configured:'已配置',unconfigured:'未配置',missing:'未配置',disabled:'已关闭',warning:'需配置',error:'异常'}[item.status]||item.status));row.append(node('h4','',({database:'数据库',model:'模型服务',encryption:'密钥加密',mail:'邮件服务'}[item.name]||item.name)),pill,node('p','settings-help',item.detail));list.append(row);}
  card.append(list,node('p','settings-help','模型、邮件和行情外部服务的配置状态不代表实时网络连通性。'));box.append(card);
 }
 async function loadAudit(){
  if(!isAdmin())return;const mine=generation,offset=auditOffset,box=$('settings-audit');box.textContent='正在读取变更记录…';
  try{const data=await api.request('/admin/settings/audit?limit=20&offset='+offset);if(mine!==generation||offset!==auditOffset)return;box.replaceChildren();for(const item of data.items){const card=node('article','settings-audit-entry');card.append(node('h3','',item.actor_email||'管理员'),node('small','',date(item.created_at)));const changes=node('dl','settings-changes');for(const [key,value] of Object.entries(item.changes||{})){const row=node('div'),field=adminFields.find(f=>f[0]===key);row.append(node('dt','',field?.[2]||key),node('dd','',typeof value==='object'?JSON.stringify(value):String(value)));changes.append(row);}card.append(changes);box.append(card);}if(!data.items.length)box.append(node('p','settings-help','当前页暂无配置变更记录。'));const pager=node('div','settings-footer-actions'),prev=button('上一页',()=>{auditOffset=Math.max(0,auditOffset-20);loadAudit();}),next=button('下一页',()=>{auditOffset+=20;loadAudit();});prev.disabled=offset===0;next.disabled=data.items.length<20;pager.append(prev,node('span','settings-help','第 '+(offset/20+1)+' 页'),next);box.append(pager);}
  catch(e){if(mine===generation){box.replaceChildren(node('p','settings-help',e.message),button('重试',loadAudit));}}
 }
 function reset(){
  generation++;userId=null;knownRole=null;personal=null;globalConfig=null;loading=null;adminLoading=null;busy=false;personalDirty=false;adminDirty=false;visible=false;tab='workspace';preferences={...defaults};
  finishConfirmation(false);fill(personalFields,'pref',defaults);fill(adminFields,'global',Object.fromEntries(adminFields.map(f=>[f[0],f[4]])));
  for(const id of ['settings-current-password','settings-new-password','settings-repeat-password','settings-api-key'])$(id).value='';
  for(const id of ['settings-account-line','settings-role','settings-sessions','settings-profile','settings-audit','settings-diagnostics'])$(id).replaceChildren();
  host.querySelectorAll('input,select,button').forEach(el=>el.disabled=false);
  document.documentElement.dataset.density='comfortable';document.documentElement.dataset.reduceMotion='false';note('');selectTab('workspace');
 }
 build();
 $('settings-confirm-cancel').addEventListener('click',()=>finishConfirmation(false));$('settings-confirm-ok').addEventListener('click',()=>finishConfirmation(true));$('settings-confirm-dialog').addEventListener('cancel',e=>{e.preventDefault();finishConfirmation(false);});
 window.addEventListener('private-session-cleared',reset);
 api.subscribe(session=>{if(userId&&session.user?.id===userId&&knownRole!==Boolean(session.user.is_admin)){const wasVisible=visible;reset();visible=wasVisible;if(wasVisible)ensureLoaded();}});
 window.settingsCenter={
  get preferences(){return {...preferences};},ensureLoaded,reset,
  async setVisible(next){visible=Boolean(next);if(!visible)return;if(userId&&userId!==api.session.user?.id)reset();const loaded=await ensureLoaded(),failure=$('settings-status').textContent;if(visible){await selectTab(tab);if(!loaded&&failure)note(failure,true);}},
 };
 selectTab('workspace');
})();
