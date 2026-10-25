import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.hidden=false;this.disabled=false;this.textContent='';this.value='';this.files=[];this.attributes={};this.classList={toggle(){}};}
 append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this.children=nodes;this.textContent='';}
 addEventListener(type,fn){this.listeners[type]=fn;} setAttribute(name,value){this.attributes[name]=value;} focus(){} click(){return this.listeners.click?.({});}
}
const content=node=>[node.textContent,...node.children.map(content)].join('\n');
const report=(overrides={})=>({success:true,company_name:'测试公司',source:{kind:'uploaded',filename:'sample.pdf',sha256:'a'.repeat(64),page_count:2},indicators:{revenue:0,net_profit:12.5,total_assets:null},ratios:{},risks:[],report:{score:null,recommendation:'信息不足',rule_checks:[{name:'资产负债率',status:'not_evaluable'}]},quality:{completeness:{found:2,total:9,missing:[{key:'total_assets',label:'总资产'}]},citations:{state:'located_unverified',located:1,total:2,items:[{label:'收入',page:1,quote:'原文收入为0',start:0,end:7}]},model:{state:'not_run',available:true,case_count:5,scope:'固定PDF的五项事实',reason:''}},...overrides});
const pdf=(name='sample.pdf',size=24)=>({name,size,type:'application/pdf',arrayBuffer:async()=>new TextEncoder().encode('%PDF-fixture').buffer});
function fixture(request=async()=>report()){
 const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
 get('analysis-result-container').append(...['analysis-result-company','analysis-source-meta','analysis-demo-note','analysis-indicators','analysis-evidence','analysis-risks','analysis-cases'].map(get));
 const events={},listeners=[],calls=[];let user={id:1};
 const context={console,AbortController,Uint8Array,Date,setInterval:()=>1,clearInterval(){},btoa:value=>Buffer.from(value,'binary').toString('base64'),window:{apiClient:{get session(){return{user};},subscribe(fn){listeners.push(fn);},async request(path,options){calls.push([path,options]);return request(path,options);}},addEventListener(type,fn){events[type]=fn;}},document:{getElementById:get,createElement:tag=>new Element(tag)}};
 vm.createContext(context);if(fs.existsSync('frontend/analysis-workbench.js'))vm.runInContext(fs.readFileSync('frontend/analysis-workbench.js','utf8'),context);
 return{get,calls,panel:context.window.analysisWorkbench,clear(){events['private-session-cleared']?.();},change(next){user=next;listeners.forEach(fn=>fn({user}));}};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('invalid or oversized selection never uploads and clears the previous file',async()=>{
 const f=fixture();assert.equal(typeof f.panel?.chooseFile,'function');
 f.panel.chooseFile(pdf());f.panel.chooseFile(pdf('oversized.pdf',20*1024*1024+1));await f.panel.upload();
 assert.equal(f.calls.length,0);assert(f.get('analysis-error').textContent.includes('20'));assert.equal(f.get('analysis-upload-btn').disabled,true);
 f.panel.chooseFile(pdf('notes.txt'));await f.panel.upload();assert.equal(f.calls.length,0);assert(f.get('analysis-error').textContent.includes('PDF'));
});

test('upload uses authenticated JSON contract and suppresses duplicate submissions',async()=>{
 let finish;const f=fixture(()=>new Promise(resolve=>finish=resolve));assert(f.panel);
 f.panel.chooseFile(pdf());f.get('analysis-company-name').value=' 公司 A ';
 const pending=f.panel.upload();await tick();await f.panel.upload();assert.equal(f.calls.length,1);
 const [path,options]=f.calls[0];assert.equal(path,'/api/analysis/upload');assert.equal(options.method,'POST');
 assert.deepEqual(JSON.parse(JSON.stringify(options.body)),{filename:'sample.pdf',company_name:'公司 A',content_base64:'JVBERi1maXh0dXJl'});
 assert(options.signal);assert.equal(f.get('analysis-progress').hidden,false);assert(f.get('analysis-stage').textContent.includes('上传与解析'));
 finish(report());await pending;assert.equal(f.get('analysis-progress').hidden,true);assert.equal(f.get('analysis-upload-btn').disabled,false);
});

test('file changes and cancellation abort transport and ignore late private responses',async()=>{
 let finish;const f=fixture(()=>new Promise(resolve=>finish=resolve));assert(f.panel);
 f.panel.chooseFile(pdf());const old=f.panel.upload();await tick();const signal=f.calls[0][1].signal;
 f.panel.chooseFile(pdf('new.pdf'));assert.equal(signal.aborted,true);finish(report({company_name:'旧文件私密公司'}));await old;
 assert(!content(f.get('analysis-result-container')).includes('旧文件私密公司'));assert.equal(f.get('analysis-file-name').textContent,'new.pdf');
 const cancelled=f.panel.upload();await tick();f.panel.cancel();assert.equal(f.calls[1][1].signal.aborted,true);
 finish(report());await cancelled;assert.equal(f.get('analysis-result-container').hidden,true);assert(f.get('analysis-status').textContent.includes('取消'));
});

test('upload failures stay inline and an explicit retry sends one new request',async()=>{
 let count=0;const f=fixture(async()=>{if(++count===1)throw Error('PDF无法解析，请更换文档。');return report();});assert(f.panel);
 f.panel.chooseFile(pdf());await f.panel.upload();assert(f.get('analysis-error').textContent.includes('PDF无法解析'));assert.equal(f.get('analysis-retry').hidden,false);
 await f.get('analysis-retry').click();assert.equal(count,2);assert.equal(f.get('analysis-error').hidden,true);
});

test('missing rule scores and unrun model scores remain unknown while zero amounts stay zero',async()=>{
 const f=fixture(async()=>report({company_name:'<img src=x onerror=alert(1)>'}));assert(f.panel);
 f.panel.chooseFile(pdf('<svg onload=alert(1)>.pdf'));await f.panel.upload();
 assert(f.get('analysis-rule-score').textContent.includes('不可评分'));assert(f.get('analysis-model-score').textContent.includes('未运行'));
 assert.equal(f.get('analysis-completeness-score').textContent,'2 / 9');assert(content(f.get('analysis-result-container')).includes('<img src=x onerror=alert(1)>'));
 const metrics=content(f.get('analysis-indicators'));assert(metrics.includes('\n0\n'));assert(metrics.includes('12.5'));assert(metrics.includes('单位与期间待核对'));assert(!metrics.includes('亿元'));
 assert(content(f.get('analysis-evidence')).includes('仅原文定位'));assert(content(f.get('analysis-evidence')).includes('原文收入为0'));
 assert.equal(f.calls.length,1,'upload must never automatically spend model quota');
});

test('demo and unmatched PDFs cannot trigger model evaluation',async()=>{
 const demo=report({source:{kind:'demo',sha256:'a'.repeat(64),filename:'演示.pdf'},quality:{...report().quality,model:{available:true,case_count:5}}});
 const f=fixture(async()=>demo);assert(f.panel);await f.panel.demo();assert.equal(f.calls[0][0],'/api/analysis/test');assert.equal(f.get('analysis-evaluate-btn').disabled,true);
 await f.panel.evaluate();assert.equal(f.calls.length,1);assert(content(f.get('analysis-result-container')).includes('演示'));
 const g=fixture(async()=>report({quality:{...report().quality,model:{available:false,reason:'未匹配固定语料'}}}));g.panel.chooseFile(pdf());await g.panel.upload();await g.panel.evaluate();assert.equal(g.calls.length,1);assert.equal(g.get('analysis-evaluate-btn').disabled,true);
});

test('explicit model evaluation keeps requested denominator, dimension zeros, errors and evidence',async()=>{
 let finish;const f=fixture(async path=>path.endsWith('/evaluate')?new Promise(resolve=>finish=resolve):report());assert(f.panel);
 f.panel.chooseFile(pdf());await f.panel.upload();assert.equal(f.get('analysis-evaluate-btn').disabled,false);
 const pending=f.panel.evaluate();await f.panel.evaluate();assert.equal(f.calls.length,2);assert.equal(f.calls[1][0],'/api/analysis/evaluate');assert.equal(f.calls[1][1].body.source_sha256,'a'.repeat(64));
 finish({state:'incomplete',requested:5,scored:1,passed:0,integrity_ok:false,acceptance_ok:false,cases:[{id:'case-1',metric:'revenue',period:'2025',scores:{identity:1,value:0,evidence:0,abstention:null,contract:1},task_error:'任务超时',output:{status:'ok',value:0,unit:'元',citations:[{page:0,quote:'<b>收入0</b>',start:0,end:8}]}}],usage:{total_tokens:0},scope:'五项事实',cost:null});await pending;
 assert.equal(f.get('analysis-model-score').textContent,'0 / 5 通过');const cases=content(f.get('analysis-cases'));assert(cases.includes('0 元'));assert(cases.includes('数值：0'));assert(cases.includes('拒答：未评分'));assert(cases.includes('任务超时'));assert(cases.includes('<b>收入0</b>'));assert(cases.includes('第 0 页'));
 assert(cases.includes('整例通过：1'));assert(!cases.includes('格式：'));
 assert(f.get('analysis-eval-summary').textContent.includes('不完整'));assert(f.get('analysis-eval-summary').textContent.includes('1 / 5'));assert(f.get('analysis-eval-meta').textContent.includes('0'));assert(f.get('analysis-eval-meta').textContent.includes('费用未提供'));
});

test('unit equivalence is safe explanatory text and never upgrades strict scores',async()=>{
 const evaluation={state:'completed',requested:2,scored:2,passed:0,integrity_ok:true,acceptance_ok:false,cases:[
  {id:'eps',metric:'基本每股收益',scores:{identity:true,value:false,evidence:true,abstention:true,contract:false},output:{status:'supported',value:'5.66',unit:'元/股',citations:[]},unit_note:{status:'equivalent',model_unit:'元/股',reference_unit:'元'}},
  {id:'bad-unit',metric:'营业收入',scores:{identity:true,value:false,evidence:true,abstention:true,contract:false},output:{status:'supported',value:'5.66',unit:'百万元',citations:[]},unit_note:{status:'different',model_unit:'百万元',reference_unit:'<img src=x onerror=alert(1)>'}}
 ]};
 const before=JSON.stringify(evaluation),f=fixture(async path=>path.endsWith('/evaluate')?evaluation:report());
 f.panel.chooseFile(pdf());await f.panel.upload();await f.panel.evaluate();
 assert.equal(f.get('analysis-model-score').textContent,'0 / 2 通过');
 const cases=content(f.get('analysis-cases'));
 assert(cases.includes('单位写法等价'));assert(cases.includes('严格评分保持原样'));
 assert(cases.includes('元/股'));assert(cases.includes('<img src=x onerror=alert(1)>'));
 assert(cases.includes('整例通过：false'));assert.equal(JSON.stringify(evaluation),before);
 function walk(node){assert.notEqual(String(node.tagName).toLowerCase(),'img');for(const child of node.children||[])walk(child);}
 walk(f.get('analysis-cases'));
});

test('private session reset clears drafts and a late response cannot unlock a new operation',async()=>{
 const finishes=[];const f=fixture(()=>new Promise(resolve=>finishes.push(resolve)));assert(f.panel);
 f.panel.chooseFile(pdf());f.get('analysis-company-name').value='私密公司';const old=f.panel.upload();await tick();
 f.change({id:2});assert.equal(f.get('analysis-company-name').value,'');assert.equal(f.get('analysis-file-name').textContent,'');
 f.panel.chooseFile(pdf('current.pdf'));const current=f.panel.upload();await tick();finishes[0](report({company_name:'上个账号'}));await old;
 assert.equal(f.get('analysis-upload-btn').disabled,true);assert(!content(f.get('analysis-result-container')).includes('上个账号'));
 finishes[1](report());await current;f.clear();assert.equal(f.get('analysis-result-container').hidden,true);assert.equal(f.get('analysis-file-input').value,'');
});

test('model transport uncertainty never offers a retry or sends a second paid request',async()=>{
 const f=fixture(async path=>{if(path.endsWith('/evaluate'))throw Object.assign(Error('连接中断，结果待确认'),{unknownOutcome:true});return report();});assert(f.panel);
 f.panel.chooseFile(pdf());await f.panel.upload();await f.panel.evaluate();
 assert.equal(f.get('analysis-model-score').textContent,'结果待确认');assert.equal(f.get('analysis-retry').hidden,true);assert.equal(f.get('analysis-evaluate-btn').disabled,true);
 await f.panel.evaluate();assert.equal(f.calls.length,2);
});

test('stopping model waiting preserves uncertainty and ignores a late result',async()=>{
 let finish;const f=fixture(async path=>path.endsWith('/evaluate')?new Promise(resolve=>finish=resolve):report());assert(f.panel);
 f.panel.chooseFile(pdf());await f.panel.upload();const pending=f.panel.evaluate();f.panel.cancel();
 assert(f.get('analysis-status').textContent.includes('可能已消耗额度'));assert.equal(f.get('analysis-evaluate-btn').disabled,true);
 finish({state:'completed',passed:5,requested:5,scored:5,cases:[]});await pending;
 assert.equal(f.get('analysis-model-score').textContent,'结果待确认');await f.panel.evaluate();assert.equal(f.calls.length,2);
});

test('session reset removes sensitive result text as well as hiding its container',async()=>{
 const f=fixture(async()=>report({report:{score:0,recommendation:'私密风险建议',action:'私密操作建议',rule_checks:[]}}));assert(f.panel);
 f.panel.chooseFile(pdf());await f.panel.upload();assert.equal(f.get('analysis-rule-score').textContent,'0 / 100');f.clear();
 assert.equal(f.get('analysis-rule-recommendation').textContent,'');assert.equal(f.get('analysis-rule-action').textContent,'');assert.equal(f.get('analysis-rule-score').textContent,'');
});

test('quota or deadline errors retain partial evaluation cases and the full denominator',async()=>{
 const f=fixture(async path=>{if(path.endsWith('/evaluate'))throw Object.assign(Error('模型限额已用尽'),{status:429,partial:{state:'incomplete',requested:5,scored:2,passed:1,integrity_ok:false,acceptance_ok:false,cases:[{id:'partial-case',metric:'revenue',scores:{value:1},output:{value:42,unit:'元',citations:[]}}]}});return report();});assert(f.panel);
 f.panel.chooseFile(pdf());await f.panel.upload();await f.panel.evaluate();
 assert.equal(f.get('analysis-model-score').textContent,'1 / 5 通过');assert(content(f.get('analysis-cases')).includes('42 元'));assert(f.get('analysis-error').textContent.includes('限额'));
 assert.equal(f.get('analysis-evaluate-btn').disabled,true);assert.equal(f.get('analysis-retry').hidden,true);await f.panel.evaluate();assert.equal(f.calls.length,2);
});
