/* Selection-driven risk tasks. No model requests on page entry or search typing. */
(() => {
 'use strict';
 const $=id=>document.getElementById(id),api=window.apiClient;
 const labels={queued:'等待继续',running:'正在分析',completed:'分析完成',partial_failed:'分析完成 · 存在待处理资料',failed:'分析未完成',cancelled:'已停止',pending:'等待处理',unconfirmed:'结果待核对'};
 const coverage={available:'已完成',processing:'正在处理',partial:'存在未完成资料',no_data:'未返回资料',failed:'读取失败',not_connected:'未读取'};
 let version=0,searchVersion=0,visible=false,task=null,externalSymbol='',timer=null,searchTimer=null,busy=false,selection=null;
 const node=(tag,cls,text)=>{const n=document.createElement(tag);n.className=cls||'';if(text!==undefined)n.textContent=text;return n;};
 const status=(text,error=false)=>{$('risk-auto-status').textContent=text;$('risk-auto-status').className='risk-note'+(error?' error':'');};
 async function request(path,options={},mine=version){
  const data=await api.request(path,{timeout:12000,...options});
  if(mine!==version)throw Object.assign(Error('范围已变化'),{name:'StaleResponseError'});
  return data;
 }
 function currentSelection(){
  return externalSymbol?{scope:'stock',symbol:externalSymbol}:$('risk-stock-filter').value?{scope:'stock',symbol:$('risk-stock-filter').value}:$('risk-scope').value?{scope:'group',group_id:Number($('risk-scope').value)}:{scope:'all'};
 }
 function render(){
  $('risk-metric-label').textContent=externalSymbol?'当前分析股票数':'监控股票数';
  $('risk-auto-results').replaceChildren();
  $('risk-auto-stop').disabled=!task||task.status==='cancelled'||(!busy&&!task.items.some(i=>i.status==='pending'||i.status==='running'));
  $('risk-auto-resume').disabled=busy||!task||!task.items.some(i=>['pending','failed','cancelled'].includes(i.status));
  $('risk-auto-repeat').disabled=busy;
  $('risk-auto-refresh').disabled=busy;
  if(!task)return;
  $('risk-scan-state').textContent=`${busy?'正在处理':labels[task.status]||'状态未知'} · ${task.processed} / ${task.total} 只`;
  $('risk-data-state').textContent='最近分析：'+new Date(task.updated_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+' · 以下按股票列出实际覆盖；不是定时扫描。';
  for(const item of task.items){
   const row=node('article','risk-auto-item');row.append(node('strong','',item.name+' · '+item.symbol),node('span','risk-note',busy&&item.status==='pending'?'正在处理当前阶段':labels[item.status]||'状态未知'));
   if(item.answer){row.append(node('h3','',item.answer.analysis_scope==='preliminary'?'首轮判断':'综合结论'));for(const line of item.answer.inferences||[])row.append(node('p','',line));if(item.answer.analysis_scope==='preliminary')row.append(node('p','risk-note','基于当前行情与已读资料；全文核查可按需继续。'));}
   else if(item.recent_findings){row.append(node('h3','','已读资料发现（阶段结果）'));for(const line of item.recent_findings.inferences||[])row.append(node('p','',line));}
   const p=item.progress;
   if(p){const phases={market:'正在获取行情与板块依据',overview:'正在生成首轮判断',paused:'首轮判断已完成，全文核查待按需继续',listing:'分页获取披露清单',extract:'提取文档全文',review:'分批阅读全文',reduce:'合并各批发现',ready:'生成综合结论',done:'全文任务完成'};row.append(node('p','risk-note',(phases[p.phase]||p.phase)+(p.documents?` · 资料 ${p.extracted}/${p.documents} 份 · ${p.pages} 页 · 已阅读 ${p.batches} 批、${p.read_characters} 字`:'')));const errors=p.errors||[],kinds={reports:'财报清单',announcements:'公告清单'};for(const error of errors.slice(0,5))row.append(node('p','risk-note error',(error.title||kinds[error.kind]||error.kind)+'：'+error.message));if(errors.length>5)row.append(node('p','risk-note error',`另有 ${errors.length-5} 项资料未完成，继续全文核查时会重试。`));}
   row.append(node('p','risk-note',['market','sectors','reports','announcements'].map((key,i)=>['行情','板块','财报','公告'][i]+'：'+(coverage[item.coverage?.[key]]||'未读取')).join(' · ')));
   const assessment=item.market_assessment;
   if(assessment?.rule_version){row.append(node('p','risk-note','市场风险参考：'+({low:'低风险',medium:'中风险',high:'高风险',unknown:'信息不足'}[assessment.risk_level]||'信息不足')+' · 财报/公告覆盖独立核实'));for(const basis of assessment.basis||[])row.append(node('p','',basis));}
   if(item.error)row.append(node('p','risk-note error',item.error));
   if(item.id&&p?.can_deepen){const b=node('button','btn','继续全文核查');b.type='button';b.disabled=busy;b.addEventListener('click',()=>itemAction(item,'deepen'));row.append(b);}
   else if(item.id&&p&&['listing','extract','review','reduce','ready'].includes(p.phase)){const b=node('button','btn','先汇总已有资料');b.type='button';b.disabled=busy||item.status==='running';b.addEventListener('click',()=>itemAction(item,'overview'));row.append(b);}
   if(item.event_id){const b=node('button','btn','查看分析');b.type='button';b.addEventListener('click',()=>item.analysis_id?window.riskWorkbench.openAnalysis(item.analysis_id):window.riskWorkbench.openDetail(item.event_id));row.append(b);}
   else for(const fact of item.facts||[])row.append(node('p','',fact));
   $('risk-auto-results').append(row);
  }
 }
 async function itemAction(item,action){
  if(busy||!task)return;const mine=++version;busy=true;render();
  try{task=await request(`/risk/tasks/${task.id}/items/${item.id}/${action}`,{method:'POST',body:{}},mine);await drive(mine);}catch(e){if(mine===version)status(e.message,true);}finally{if(mine===version){busy=false;render();}}
 }
 async function drive(mine){
  busy=true;render();status('正在获取资料并整理分析，请勿重复操作。');
  try{
   while(task&&visible&&mine===version&&!['cancelled'].includes(task.status)&&task.items.some(i=>['pending','running'].includes(i.status))){
    if(task.items.some(i=>i.status==='running')){
     status('已有股票正在处理，等待完成后可继续剩余项。');break;
    }
    const pending=task.items.find(i=>i.status==='pending'),phase=pending?.progress?.phase;
    const operation=['market','listing','extract'].includes(phase)?'collect':'process';
    try{task=await request(`/risk/tasks/${task.id}/${operation}`,{method:'POST',body:{},timeout:650000},mine);render();}
    catch(e){const seconds=Number(e.retryAfter);if(e.status===429&&seconds>0&&seconds<=60&&mine===version&&visible){status(`等待模型额度 ${seconds} 秒，已保存全文阅读位置…`);await new Promise(resolve=>setTimeout(resolve,seconds*1000));if(mine!==version||!visible)return;continue;}throw e;}
   }
   if(mine!==version)return;
   status(task.status==='queued'?'任务已保存，点击“继续未完成项”恢复；离开页面后尚未开始的股票会等待继续。':(labels[task.status]||'处理结束')+'；结果已保存，可查看各股票的事实、原文与缺失资料。');
   await window.riskWorkbench.refresh();if(mine===version)render();
  }catch(e){if(mine===version)status(e.unknownOutcome?'响应中断，结果待确认；点击刷新进度核对，请勿重复分析。':e.message,true);}
  finally{if(mine===version){busy=false;render();}}
 }
 async function begin(force=false){
  if(!visible)return;
  const mine=++version;busy=false;task=null;selection=currentSelection();render();
  status('正在创建当前范围的分析任务…');
  try{
   task=await request('/risk/tasks',{method:'POST',body:{...selection,days:Number($('risk-auto-days').value||90),force,request_id:crypto.randomUUID()}},mine);
   if(mine!==version)return;render();await drive(mine);
  }catch(e){if(mine===version)status(e.message,true);}
 }
 function schedule(){
  clearTimeout(timer);version++;busy=false;
  status('范围已选择，即将自动分析…');
  timer=setTimeout(()=>{if(visible)begin();},700);
 }
 async function search(){
  const mine=++searchVersion,q=$('risk-search-input').value.trim();$('risk-search-results').replaceChildren();
  if(!q)return;
  try{
   const data=await api.request('/stocks/search?'+new URLSearchParams({q,limit:'8'}),{timeout:10000});if(mine!==searchVersion)return;
   if(!data.results.length)$('risk-search-results').append(node('p','risk-note','未找到股票，请核对名称或代码。'));
   for(const s of data.results){const b=node('button','risk-search-option',s.name+' · '+s.symbol);b.type='button';b.addEventListener('click',async()=>{
    window.riskAuto.pauseSelection();const epoch=version;
    searchVersion++;externalSymbol=s.symbol;$('risk-search-input').value=s.name+' · '+s.symbol;$('risk-search-results').replaceChildren();
    $('risk-auto-range').textContent='当前为搜索单股：'+s.name+' · '+s.symbol+'（不自动加入自选）';
    await window.riskWorkbench.filterChanged();if(epoch===version&&visible)begin();
   });$('risk-search-results').append(b);}
  }catch(e){if(mine===searchVersion)$('risk-search-results').append(node('p','risk-note error',e.message));}
 }
 $('risk-search-input').addEventListener('input',()=>{searchVersion++;clearTimeout(searchTimer);searchTimer=setTimeout(search,300);});
 $('risk-auto-days').addEventListener('change',schedule);
 $('risk-auto-repeat').addEventListener('click',()=>begin(true));
 $('risk-auto-resume').addEventListener('click',async()=>{
  if(busy||!task)return;const mine=++version;busy=true;render();
  try{task=await request(`/risk/tasks/${task.id}/resume`,{method:'POST',body:{}},mine);await drive(mine);}catch(e){if(mine===version)status(e.message,true);}finally{if(mine===version){busy=false;render();}}
 });
 $('risk-auto-stop').addEventListener('click',async()=>{
  if(!task)return;const mine=++version;busy=false;clearTimeout(timer);
  try{task=await request(`/risk/tasks/${task.id}/cancel`,{method:'POST',body:{}},mine);render();status('已停止未开始项；正在处理的股票完成后仍会保存。');}catch(e){if(mine===version)status(e.message,true);}
 });
 $('risk-auto-refresh').addEventListener('click',async()=>{
  if(!task||busy)return;const mine=version;
  try{task=await request(`/risk/tasks/${task.id}`,{},mine);render();status('任务状态已刷新，可继续未完成项。');}catch(e){if(mine===version)status(e.message,true);}
 });
 window.riskAuto={external:()=>externalSymbol,schedule,renderCurrent:render,
  restoreScope(){if(!task||busy)return;if(task.scope?.kind==='group'&&Array.from($('risk-scope').children).some(o=>o.value===String(task.scope.group_id)))$('risk-scope').value=String(task.scope.group_id);},
  pauseSelection(){version++;busy=false;task=null;clearTimeout(timer);render();},
  clearExternal(){externalSymbol='';$('risk-auto-range').textContent='当前为自选范围；选择分组或股票后自动分析。';},
  async setVisible(value){const entering=value&&!visible;visible=value;if(!value){version++;busy=false;clearTimeout(timer);}if(!entering)return;
   const mine=version;try{const data=await request('/risk/tasks',{},mine);if(data.items.length){task=data.items[0];if(task.scope?.kind==='stock'){externalSymbol=task.scope.symbol;$('risk-search-input').value=externalSymbol;$('risk-auto-range').textContent='已恢复单股分析：'+externalSymbol+'（不自动加入自选）';}window.riskAuto.restoreScope();render();status('已恢复最近分析任务。未开始项需要点击继续；打开页面不会新增模型请求。');await window.riskWorkbench.filterChanged();}}catch(e){if(mine===version)status('任务历史暂不可用：'+e.message,true);}
  },
  reset(){version++;searchVersion++;visible=false;busy=false;task=null;externalSymbol='';selection=null;clearTimeout(timer);clearTimeout(searchTimer);
   $('risk-search-input').value='';$('risk-search-results').replaceChildren();$('risk-auto-results').replaceChildren();$('risk-auto-days').value='90';$('risk-auto-range').textContent='';status('');render();
  }
 };
})();
