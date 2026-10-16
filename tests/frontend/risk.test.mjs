import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Element {
 constructor(){this.children=[];this.listeners={};this.value='';this.textContent='';this.hidden=false;this.checked=false;this.classList={add(){},remove(){}};}
 append(...items){this.children.push(...items);} replaceChildren(...items){this.children=items;}
 addEventListener(n,fn){this.listeners[n]=fn;} setAttribute(){} focus(){} scrollIntoView(){}
 showModal(){this.open=true;} close(){this.open=false;} reset(){}
}
const els=new Map(),get=id=>{if(!els.has(id))els.set(id,new Element());return els.get(id);};
const summary={facts:['<script>alert(1)</script>'],inferences:['推断'],unknowns:['待核实'],sources:['javascript:bad']};
const event={id:1,stock_name:'平安银行',symbol:'000001.SZ',risk_type:'announcement',risk_level:'high',status:'unread',title:'公告',model_mode:'qwen',summary:'风险线索',input_text:'原文',result:summary,evidence:[{title:'资料',verification:'user_provided',url:'javascript:alert(1)',excerpt:'<img onerror=bad>'}],model_sources:['未经核验的来源']};
let calls=[],postCount=0,resolvePost,resolveDetail,resolveList;
const listing={items:[event],total:1,page:1,page_size:10,overview:{monitored_stocks:1,pending:1,high:1,unknown:0},scan:{status:'not_connected'}};
const api={session:{user:{id:1},model_mode:'qwen'},request:async(path,options={})=>{
 calls.push(path);
 if(path==='/watchlists')return [{id:1,name:'核心'}];
 if(path==='/watchlists/1/stocks')return [{symbol:'000001.SZ',name:'平安银行'}];
 if(path.startsWith('/risk/events?'))return resolveList?new Promise(r=>resolveList=r):listing;
 if(path.startsWith('/risk/analyses?'))return {items:[],total:0};
 if(path==='/risk/analyses'){postCount++;return new Promise(r=>resolvePost=r);}
 if(path==='/risk/events/1')return resolveDetail?new Promise(r=>resolveDetail=r):event;
 throw Error(path);
}};
const context={console,URL,URLSearchParams,Date,crypto:{randomUUID:()=> 'request-key'},window:{apiClient:api,selectWorkspacePage:async()=>{}},document:{getElementById:get,createElement:()=>new Element(),querySelectorAll:()=>[]}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/risk.js','utf8'),context);
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
context.window.riskWorkbench.setVisible(true);await flush();
assert.equal(get('risk-count-stocks').textContent,1);
assert(get('risk-scan-state').textContent.includes('等待选择'));
assert.equal(get('risk-list').children.length,1);
await get('risk-list').children[0].listeners.click();
assert.equal(get('risk-evidence').children[0].children.some(n=>n.tagName==='a'),false);
assert(get('risk-facts').children[0].textContent.includes('<script>'));
await get('risk-research').listeners.click();
assert(get('input-box').value.includes('000001.SZ'));
assert(get('input-box').value.includes('风险线索'));
get('risk-text').value='公告';get('risk-title').value='公告';get('risk-material-type').value='announcement';
const ev={preventDefault(){}};
const pending=get('risk-form').listeners.submit(ev);await flush();
await get('risk-form').listeners.submit(ev);assert.equal(postCount,1);
context.window.riskWorkbench.reset();resolvePost(event);await pending;await flush();
assert.equal(get('risk-detail').hidden,true);
assert.equal(get('risk-form-status').textContent,'');
assert.equal(get('risk-text').value,'');
context.window.riskWorkbench.setVisible(true);await flush();
resolveDetail=true;
const oldDetail=get('risk-list').children[0].listeners.click();await flush();
get('risk-stock-filter').value='000001.SZ';await get('risk-stock-filter').listeners.change();
resolveDetail(event);await oldDetail;assert.equal(get('risk-detail').hidden,true,'changed filter ignores late detail');
resolveList=true;
const oldList=get('risk-reload').listeners.click();await flush();
context.window.riskWorkbench.reset();resolveList(listing);await oldList;await flush();
assert.equal(get('risk-list').children.length,0,'reset ignores late list');
const html=fs.readFileSync('frontend/index.html','utf8');
assert(html.includes('id="risk-page"'));assert(html.includes('maxlength="20000"'));
console.log('PASS: workbench, safe evidence, research context, duplicate submission, stale detail/list/analysis, account cleanup');

// A delayed reload after a state write must not reopen the old stock under a new filter.
resolveList=null;resolveDetail=null;
context.window.riskWorkbench.setVisible(true);await flush();
await get('risk-list').children[0].listeners.click();
resolveList=true;
const marking=get('risk-viewed').listeners.click();await flush();const oldReload=resolveList;
resolveList=null;get('risk-stock-filter').value='600000.SH';await get('risk-stock-filter').listeners.change();
oldReload(listing);await marking;await flush();
assert.equal(get('risk-detail').hidden,true,'late status reload must not restore out-of-scope details');

// The same protection applies to the final reload of a completed text analysis.
get('risk-text').value='新的资料';get('risk-title').value='公告';
const analyzing=get('risk-form').listeners.submit(ev);await flush();
resolveList=true;resolvePost(event);await flush();const oldAnalysisReload=resolveList;
resolveList=null;get('risk-stock-filter').value='000001.SZ';await get('risk-stock-filter').listeners.change();
oldAnalysisReload(listing);await analyzing;await flush();
assert.equal(get('risk-detail').hidden,true,'late analysis reload must not restore out-of-scope details');
console.log('PASS: changing scope during post-write reload cannot restore old details');

// One failed group is a partial coverage failure, never an empty watchlist success.
const workingRequest=api.request;
api.request=async(path,opts)=>{
 if(path==='/watchlists')return [{id:1,name:'可用分组'},{id:2,name:'失败分组'}];
 if(path==='/watchlists/2/stocks')throw Error('group unavailable');
 return workingRequest(path,opts);
};
context.window.riskWorkbench.reset();context.window.riskWorkbench.setVisible(true);await flush();
assert(get('risk-scope-status').textContent.includes('部分失败'));
assert.equal(get('risk-stock-filter').children.length,2,'available group remains selectable');
console.log('PASS: partial group failure stays distinct from empty coverage');
