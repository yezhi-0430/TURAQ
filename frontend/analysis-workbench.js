/* PDF research stays local to this session; every request uses the shared API client. */
(() => {
 'use strict';
 const $=id=>document.getElementById(id),api=window.apiClient;
 if(!$('analysis-page')||!api)return;
 const limit=20*1024*1024,labels={revenue:'营业收入',net_profit:'净利润',total_assets:'总资产',total_liabilities:'总负债',operating_cash_flow:'经营活动现金流',accounts_receivable:'应收账款',inventory:'存货',current_assets:'流动资产',current_liabilities:'流动负债'};
 let file=null,result=null,evaluationState='not_run',revision=0,busy=null,controller=null,timer=null,started=0,lastAction=null,actor=api.session.user?.id;
 const known=value=>value!==null&&value!==undefined;
 const number=value=>typeof value==='number'&&Number.isFinite(value)?value.toLocaleString('zh-CN',{maximumFractionDigits:8}):known(value)?String(value):'未提取';
 const el=(tag,className,text)=>{const node=document.createElement(tag);if(className)node.className=className;if(known(text))node.textContent=String(text);return node;};
 const set=(id,text)=>{$(id).textContent=text;};
 function clearError(){$('analysis-error').hidden=true;set('analysis-error','');$('analysis-retry').hidden=true;lastAction=null;}
 function showError(error,action){set('analysis-error',error.message||'请求未完成，请稍后再试。');$('analysis-error').hidden=false;lastAction=error.unknownOutcome?null:action;$('analysis-retry').hidden=!lastAction;}
 function canEvaluate(){return !!(result?.source?.kind==='uploaded'&&result.source.sha256&&result.quality?.model?.available&&evaluationState==='not_run');}
 function controls(){
  $('analysis-upload-btn').disabled=!!busy||!file;$('analysis-test-btn').disabled=!!busy;$('analysis-company-name').disabled=!!busy;
  $('analysis-evaluate-btn').disabled=!!busy||!canEvaluate();
  set('analysis-evaluate-btn',evaluationState==='running'?'正在进行模型评测…':evaluationState==='completed'?'本次模型评测已完成':evaluationState==='uncertain'?'评测结果待确认':'运行金标评测 · 使用模型额度');
 }
 function stopClock(){if(timer!==null)clearInterval(timer);timer=null;$('analysis-progress').hidden=true;$('analysis-skeleton').hidden=true;$('analysis-page').setAttribute('aria-busy','false');}
 function discard(){revision++;controller?.abort();controller=null;busy=null;stopClock();controls();}
 function clearResult(){
  result=null;evaluationState='not_run';$('analysis-result-container').hidden=true;$('analysis-empty').hidden=false;
  for(const id of ['analysis-cases','analysis-evidence','analysis-indicators','analysis-risks','analysis-rule-checks'])$(id).replaceChildren();
  for(const id of ['analysis-result-company','analysis-source-meta','analysis-eval-summary','analysis-eval-meta','analysis-rule-score','analysis-rule-recommendation','analysis-rule-action','analysis-completeness-score','analysis-completeness-note','analysis-citation-score','analysis-model-score','analysis-model-note'])set(id,'');
  controls();
 }
 function chooseFile(next){
  discard();clearError();clearResult();file=null;$('analysis-file-input').value='';$('analysis-file-card').hidden=true;set('analysis-file-name','');set('analysis-file-size','');set('analysis-status','');
  if(!next){controls();return;}
  if(!/\.pdf$/i.test(next.name||'')){showError(Error('请选择 PDF 格式的财报。'));controls();return;}
  if(!next.size||next.size>limit){showError(Error('PDF 文件须大于 0 字节且不超过 20 MiB。'));controls();return;}
  file=next;set('analysis-file-name',file.name);set('analysis-file-size',(file.size/1024/1024).toFixed(2)+' MiB · PDF');$('analysis-file-card').hidden=false;controls();
 }
 function stage(label,index){set('analysis-stage',label);for(let i=0;i<3;i++)$('analysis-stage-'+i).classList.toggle('active',i===index);}
 function start(kind){
  busy=kind;controller=new AbortController();clearError();started=Date.now();$('analysis-progress').hidden=false;$('analysis-skeleton').hidden=kind==='evaluate';$('analysis-empty').hidden=true;$('analysis-page').setAttribute('aria-busy','true');
  stage(kind==='evaluate'?'模型提取与金标评分':kind==='demo'?'读取演示结果':'校验与读取 PDF',kind==='upload'?0:1);
  const steps=kind==='evaluate'?['确认金标资料','模型提取与评分','整理逐例结果']:kind==='demo'?['演示资料','读取演示结果','整理结果']:['校验与读取','上传与解析','整理结果'];
  steps.forEach((label,index)=>set('analysis-stage-'+index,'0'+(index+1)+' '+label));
  const elapsed=()=>set('analysis-elapsed','已用 '+Math.floor((Date.now()-started)/1000)+' 秒');elapsed();timer=setInterval(elapsed,1000);controls();return revision;
 }
 function finish(mine){if(mine!==revision)return;busy=null;controller=null;stopClock();controls();$('analysis-empty').hidden=!!result;}
 async function base64(source){const bytes=new Uint8Array(await source.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(binary);}
 async function upload(){
  if(busy||!file)return;clearResult();const mine=start('upload'),source=file,company=$('analysis-company-name').value.trim();
  try{
   const content=await base64(source);if(mine!==revision)return;stage('上传与解析 PDF',1);
   const data=await api.request('/api/analysis/upload',{method:'POST',body:{filename:source.name,company_name:company,content_base64:content},signal:controller.signal,timeout:120000});
   if(mine!==revision)return;stage('整理研究结果',2);render(data);set('analysis-status','解析完成，可展开原文片段核对。');
  }catch(error){if(mine!==revision)return;showError(error,upload);set('analysis-status','本次解析未完成。');}
  finally{finish(mine);}
 }
 async function demo(){
  if(busy)return;clearResult();const mine=start('demo');
  try{const data=await api.request('/api/analysis/test',{signal:controller.signal,timeout:30000});if(mine!==revision)return;stage('整理演示结果',2);render({...data,source:{...data.source,kind:'demo'}});set('analysis-status','正在查看演示资料，不代表已分析你的文件。');}
  catch(error){if(mine===revision)showError(error,demo);}finally{finish(mine);}
 }
 function cancel(){
  const was=busy;if(!was)return;discard();clearError();
  if(was==='evaluate'){evaluationState='uncertain';set('analysis-model-score','结果待确认');set('analysis-model-note','已停止等待；模型可能仍在服务端运行，本页不会重复提交。');}
  set('analysis-status',was==='evaluate'?'已取消等待。模型请求可能已消耗额度，结果待确认。':'已取消本次处理，可更换文件或重新开始。');$('analysis-empty').hidden=!!result;controls();
 }
 function reset(){discard();file=null;clearResult();clearError();$('analysis-file-input').value='';$('analysis-company-name').value='';$('analysis-file-card').hidden=true;set('analysis-file-name','');set('analysis-file-size','');set('analysis-status','');controls();}
 function factCard(label,value){const card=el('div','analysis-indicator');card.append(el('dt','',label),el('dd','',number(value)));return card;}
 function evidenceItem(item){
  const box=el('details','analysis-evidence-item'),summary=el('summary','');summary.append(el('span','',item.label||item.document_id||'原文片段'),el('small','',known(item.page)?'第 '+item.page+' 页':'页码未提供'));
  box.append(summary,el('blockquote','',item.quote||'未提供引用片段'));
  if(known(item.start)||known(item.end))box.append(el('p','analysis-small','原文字符位置 '+(item.start??'未知')+' – '+(item.end??'未知')));return box;
 }
 function render(data){
  if(!data?.success||!data.source||!data.quality)throw Error('分析结果格式不完整，请重新解析。');
  result=data;evaluationState='not_run';$('analysis-empty').hidden=true;$('analysis-result-container').hidden=false;
  const isDemo=data.source.kind==='demo',quality=data.quality,complete=quality.completeness||{},citations=quality.citations||{},model=quality.model||{},report=data.report||{};
  set('analysis-result-company',data.company_name||'未提供公司名称');set('analysis-source-meta',[isDemo?'演示资料':'已上传的 PDF',data.source.filename,known(data.source.page_count)?data.source.page_count+' 页':null].filter(Boolean).join(' · '));
  $('analysis-demo-note').hidden=!isDemo;
  set('analysis-completeness-score',(complete.found??'未知')+' / '+(complete.total??'未知'));
  set('analysis-completeness-note',complete.missing?.length?'待补充：'+complete.missing.map(item=>item.label||item.key).join('、'):'按核心指标字段统计；需核对提取口径。');
  set('analysis-citation-score',(citations.located??'未知')+' / '+(citations.total??'未知')+' 已定位');
  set('analysis-model-score','未运行');set('analysis-model-note',isDemo?'演示资料不提供真实模型评测。':model.available?'已匹配固定 PDF，点击后评测 '+(model.case_count??'指定')+' 个案例。':model.reason||'此 PDF 尚无匹配的固定金标，不能评测。');
  set('analysis-rule-score',typeof report.score==='number'?number(report.score)+' / 100':'不可评分');
  set('analysis-rule-recommendation',report.recommendation||'未形成规则建议');set('analysis-rule-action',report.action||'规则结果需结合完整报表与原文核对。');
  $('analysis-indicators').replaceChildren();for(const [key,label] of Object.entries(labels))$('analysis-indicators').append(factCard(label,data.indicators?.[key]));
  $('analysis-indicators').append(el('p','analysis-small analysis-unit-note','原文数值 · 单位与期间待核对'));
  $('analysis-rule-checks').replaceChildren();for(const check of report.rule_checks||[]){const row=el('div','analysis-rule-row');row.append(el('span','',check.name),el('span',check.status==='triggered'?'analysis-warning':'analysis-small',({passed:'规则通过',triggered:'触发规则',not_evaluable:'资料不足'})[check.status]||'状态未知'));$('analysis-rule-checks').append(row);}
  $('analysis-risks').replaceChildren();for(const risk of data.risks||[]){const row=el('article','analysis-risk');row.append(el('span','analysis-tag',({high:'高风险',medium:'中风险',low:'低风险'})[risk.level]||'风险待定'),el('strong','',risk.name),el('p','analysis-small','提取值 '+number(risk.value)+' · 规则阈值 '+number(risk.threshold)));$('analysis-risks').append(row);}
  if(!data.risks?.length)$('analysis-risks').append(el('p','analysis-small','当前资料未触发风险规则；缺失指标仍需补充核对。'));
  $('analysis-evidence').replaceChildren(el('p','analysis-small','仅原文定位：页码与引句可供复核，尚未对照金标验证准确性。'));
  for(const item of citations.items||[])$('analysis-evidence').append(evidenceItem(item));
  if(!citations.items?.length)$('analysis-evidence').append(el('p','analysis-small','暂无可定位的原文片段。'));
  $('analysis-cases').replaceChildren();set('analysis-eval-summary',model.scope||'模型评测检查同一 PDF 中的事实提取、数值与证据。');set('analysis-eval-meta','');controls();
 }
 async function evaluate(){
  if(busy||!canEvaluate())return;evaluationState='running';const mine=start('evaluate');set('analysis-model-score','评测进行中');set('analysis-model-note','正在对照固定金标，所有请求案例均保留在分母中。');
  try{
   const data=await api.request('/api/analysis/evaluate',{method:'POST',body:{source_sha256:result.source.sha256},signal:controller.signal,timeout:180000});
   if(mine!==revision)return;stage('整理逐例评分',2);renderEvaluation(data);evaluationState='completed';set('analysis-status','模型评测已返回，查看下方逐例评分与引用。');
  }catch(error){
   if(mine!==revision)return;
   if(error.partial){renderEvaluation(error.partial);evaluationState='completed';showError(error);set('analysis-status','评测提前结束，已保留返回的案例与完整请求总数。');}
   else{evaluationState=error.unknownOutcome?'uncertain':'not_run';set('analysis-model-score',error.unknownOutcome?'结果待确认':'评测未完成');set('analysis-model-note',error.unknownOutcome?'请求结果待确认，本页不会重复提交模型评测。':'没有形成模型分数，可在解决错误后重试。');showError(error,evaluate);}
  }finally{finish(mine);}
 }
 function renderEvaluation(data){
  const requested=data.requested??'未知',scored=data.scored??'未知';set('analysis-model-score',(data.passed??'未知')+' / '+requested+' 通过');
  set('analysis-model-note','已评分 '+scored+' / '+requested+' 个案例 · '+(data.acceptance_ok===true?'通过验收':data.acceptance_ok===false?'未通过验收':'验收状态未知'));
  set('analysis-eval-summary',(data.state==='completed'?'评测完成':'评测不完整')+' · 已评分 '+scored+' / '+requested+' · '+(data.integrity_ok===true?'案例完整性通过':data.integrity_ok===false?'案例完整性未通过':'案例完整性未知')+(data.scope?' · '+data.scope:''));
  const usage=data.usage||{};set('analysis-eval-meta',[data.model_mode?'模型模式 '+data.model_mode:null,'Token '+(usage.total_tokens??'未提供'),data.cost==null?'费用未提供':'费用 '+String(data.cost),data.scorer_version?'评分器 '+data.scorer_version:null,data.trace_id?'追踪 '+data.trace_id:null].filter(Boolean).join(' · '));
  $('analysis-cases').replaceChildren();
  for(const entry of data.cases||[]){
   const box=el('details','analysis-case'),summary=el('summary',''),scores=entry.scores||{},output=entry.output||{};
   summary.append(el('span','analysis-case-id',entry.id||'案例'),el('strong','',(labels[entry.metric]||entry.metric||'未提供指标')+(entry.period?' · '+entry.period:'')),el('span',entry.task_error||entry.scoring_error?'analysis-warning':'analysis-small',entry.task_error||entry.scoring_error?'存在错误':'查看评分与证据'));
   box.append(summary);const dimensions=el('div','analysis-dimensions');for(const [key,label] of Object.entries({identity:'身份',value:'数值',evidence:'证据',abstention:'拒答',contract:'整例通过'}))dimensions.append(el('span','',label+'：'+(known(scores[key])?number(scores[key]):'未评分')));box.append(dimensions);
   if(entry.task_error)box.append(el('p','analysis-warning','任务错误：'+entry.task_error));if(entry.scoring_error)box.append(el('p','analysis-warning','评分错误：'+entry.scoring_error));
   box.append(el('p','analysis-case-output','模型输出：'+(known(output.value)?number(output.value)+(output.unit?' '+output.unit:''):'未提供数值')+' · 状态 '+(output.status||'未提供')));
   const unitNote=entry.unit_note;
   if(unitNote&&['equivalent','different'].includes(unitNote.status))box.append(el('p','analysis-small',(unitNote.status==='equivalent'?'单位写法等价：':'单位与参考不同：')+String(unitNote.model_unit??'未提供')+' 与 '+String(unitNote.reference_unit??'未提供')+'；严格评分保持原样。'));
   for(const citation of output.citations||[])box.append(evidenceItem(citation));if(!output.citations?.length)box.append(el('p','analysis-small','本例未返回引用证据。'));$('analysis-cases').append(box);
  }
  if(!data.cases?.length)$('analysis-cases').append(el('p','analysis-small','没有返回逐例结果；请求案例仍保留在总数中。'));
 }
 $('analysis-file-input').addEventListener('change',event=>chooseFile(event.target.files?.[0]));
 $('analysis-dropzone').addEventListener('dragover',event=>{event.preventDefault();$('analysis-dropzone').classList.toggle('dragover',true);});
 $('analysis-dropzone').addEventListener('dragleave',()=>$('analysis-dropzone').classList.toggle('dragover',false));
 $('analysis-dropzone').addEventListener('drop',event=>{event.preventDefault();$('analysis-dropzone').classList.toggle('dragover',false);chooseFile(event.dataTransfer.files?.[0]);});
 $('analysis-clear-file').addEventListener('click',()=>chooseFile(null));$('analysis-upload-btn').addEventListener('click',upload);$('analysis-test-btn').addEventListener('click',demo);$('analysis-cancel').addEventListener('click',cancel);$('analysis-evaluate-btn').addEventListener('click',evaluate);$('analysis-retry').addEventListener('click',()=>lastAction?.());
 api.subscribe(session=>{if(actor!==session.user?.id){actor=session.user?.id;reset();}});window.addEventListener('private-session-cleared',reset);
 window.analysisWorkbench={chooseFile,upload,demo,evaluate,cancel,reset};reset();
})();
