import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class E{
 constructor(){this.listeners={};this.children=[];this.value='';this.hidden=false;this.disabled=false;this.textContent='';}
 addEventListener(n,f){this.listeners[n]=f;}append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;}setAttribute(){}
}
function fixture(){
 const els=new Map(),get=id=>{if(!els.has(id))els.set(id,new E());return els.get(id);},calls=[],timers=[];
 let processResolve;
 const task={id:1,status:'queued',days:90,total:1,processed:0,scope:{kind:'stock',symbol:'600519.SH'},items:[{symbol:'600519.SH',name:'贵州茅台',status:'pending',facts:[],coverage:{}}]};
 const ctx={console,URLSearchParams,AbortController,crypto:{randomUUID:()=> 'key'},setTimeout:f=>{timers.push(f);return timers.length;},clearTimeout:id=>{timers[id-1]=null;},window:{apiClient:{request:async(path,opts)=>{calls.push([path,opts]);if(path.startsWith('/stocks/search'))return {results:[{symbol:'600519.SH',name:'贵州茅台'}]};if(path==='/risk/tasks')return opts?.method==='POST'?task:{items:[]};if(path.endsWith('/process'))return new Promise(r=>processResolve=r);return task;}},riskWorkbench:{refresh:async()=>{},openDetail:async()=>{},filterChanged:async()=>{}}},document:{getElementById:get,createElement:()=>new E()}};
 vm.createContext(ctx);if(fs.existsSync('frontend/risk-auto.js'))vm.runInContext(fs.readFileSync('frontend/risk-auto.js','utf8'),ctx);
 return {ctx,get,calls,run:async()=>{const fn=timers.shift();if(fn)await fn();},finish:()=>processResolve({...task,status:'completed',processed:1,items:[{...task.items[0],status:'completed',event_id:1}]} )};
}
const flush=async()=>{for(let i=0;i<10;i++)await new Promise(r=>setImmediate(r));};
test('search only reads candidates; selecting an external stock starts an isolated task',async()=>{
 const f=fixture();assert(f.ctx.window.riskAuto,'automatic risk controller exists');
 await f.ctx.window.riskAuto.setVisible(true);
 f.get('risk-search-input').value='茅台';f.get('risk-search-input').listeners.input();await f.run();
 assert.equal(f.calls.filter(([p,o])=>p==='/risk/tasks'&&o?.method==='POST').length,0);
 await f.get('risk-search-results').children[0].listeners.click();await flush();
 const create=f.calls.find(([p,o])=>p==='/risk/tasks'&&o.method==='POST');assert.equal(create[1].body.scope,'stock');assert.equal(create[1].body.symbol,'600519.SH');
 assert.equal(f.ctx.window.riskAuto.external(),'600519.SH');assert(!f.calls.some(([p])=>p.includes('/watchlists')));
 f.ctx.window.riskAuto.reset();f.finish();await flush();assert.equal(f.get('risk-auto-results').children.length,0);
});
test('opening the page loads history without starting model processing',async()=>{
 const f=fixture();assert(f.ctx.window.riskAuto);await f.ctx.window.riskAuto.setVisible(true);await flush();
 assert(!f.calls.some(([p,o])=>p.endsWith('/process')||o?.method==='POST'));
});
test('logout during the candidate filter read cannot create a task afterwards',async()=>{
 const f=fixture();await f.ctx.window.riskAuto.setVisible(true);
 f.get('risk-search-input').value='茅台';f.get('risk-search-input').listeners.input();await f.run();
 let release;f.ctx.window.riskWorkbench.filterChanged=()=>new Promise(r=>release=r);
 const pending=f.get('risk-search-results').children[0].listeners.click();await flush();
 f.ctx.window.riskAuto.reset();release();await pending;await flush();
 assert.equal(f.calls.filter(([p,o])=>p==='/risk/tasks'&&o?.method==='POST').length,0);
});
test('busy task blocks unordered progress refresh and pauses synchronously on scope change',async()=>{
 const f=fixture();await f.ctx.window.riskAuto.setVisible(true);
 f.get('risk-search-input').value='茅台';f.get('risk-search-input').listeners.input();await f.run();
 const choosing=f.get('risk-search-results').children[0].listeners.click();await flush();
 assert.equal(f.get('risk-auto-refresh').disabled,true);
 assert.equal(typeof f.ctx.window.riskAuto.pauseSelection,'function');
 f.ctx.window.riskAuto.pauseSelection();f.finish();await choosing;await flush();
 assert.equal(f.get('risk-auto-results').children.length,0);
});
test('resume invalidates an older idle refresh before it returns',async()=>{
 const f=fixture();await f.ctx.window.riskAuto.setVisible(true);
 f.ctx.window.apiClient.request=async()=>({items:[{id:1,status:'queued',total:1,processed:0,items:[{symbol:'600519.SH',name:'茅台',status:'pending'}],updated_at:'2026-10-13T00:00:00Z'}]});
 await f.ctx.window.riskAuto.setVisible(false);await f.ctx.window.riskAuto.setVisible(true);
 let oldResolve,resumeResolve;
 f.ctx.window.apiClient.request=async(path)=>path.endsWith('/resume')?new Promise(r=>resumeResolve=r):new Promise(r=>oldResolve=r);
 const old=f.get('risk-auto-refresh').listeners.click();await flush();const resume=f.get('risk-auto-resume').listeners.click();await flush();
 oldResolve({id:1,status:'failed',items:[],processed:0,total:1});await old;
 assert.equal(f.get('risk-auto-results').children.length,1);
 f.ctx.window.riskAuto.reset();resumeResolve({id:1,status:'queued',items:[],processed:0,total:1});await resume;
});

test('durable reading advances collection before model phases and stops after synthesis',async()=>{
 const f=fixture(),steps=['market','listing','extract','review','ready','done'];let cursor=0;
 const task=()=>({id:1,status:cursor===5?'completed':'queued',total:1,processed:cursor===5?1:0,updated_at:'2026-10-14T00:00:00Z',items:[{symbol:'600519.SH',name:'隔离测试',status:cursor===5?'completed':'pending',coverage:{},progress:{phase:steps[cursor],documents:2,extracted:cursor>=3?2:0,pages:4,batches:cursor>=4?1:0,read_characters:cursor>=4?800:0}}]});
 f.ctx.window.apiClient.request=async(path,opts)=>{f.calls.push([path,opts]);if(path==='/risk/tasks')return opts?.method==='POST'?task():{items:[]};cursor++;return task();};
 await f.ctx.window.riskAuto.setVisible(true);await f.get('risk-auto-repeat').listeners.click();
 assert.deepEqual(f.calls.filter(([p])=>p.includes('/tasks/1/')).map(([p])=>p.split('/').at(-1)),['collect','collect','collect','process','process']);
 assert.equal(f.get('risk-auto-repeat').disabled,false);
});

test('first answer stops before full reading and renders the useful conclusion',async()=>{
 const f=fixture(),steps=['market','overview','paused'];let cursor=0;
 const task=()=>({id:1,status:cursor===2?'completed':'queued',total:1,processed:cursor===2?1:0,updated_at:'2026-10-14T00:00:00Z',items:[{id:7,symbol:'600519.SH',name:'隔离测试',status:cursor===2?'completed':'pending',coverage:{},answer:cursor===2?{analysis_scope:'preliminary',inferences:['短期趋势偏弱，量能尚未确认企稳。']}:null,progress:{phase:steps[cursor],documents:0,extracted:0,pages:0,batches:0,read_characters:0,can_deepen:cursor===2}}]});
 f.ctx.window.apiClient.request=async(path,opts)=>{f.calls.push([path,opts]);if(path==='/risk/tasks')return opts?.method==='POST'?task():{items:[]};cursor++;return task();};
 await f.ctx.window.riskAuto.setVisible(true);await f.get('risk-auto-repeat').listeners.click();
 assert.deepEqual(f.calls.filter(([p])=>p.includes('/tasks/1/')).map(([p])=>p.split('/').at(-1)),['collect','process']);
 const texts=n=>[n.textContent,...n.children.flatMap(texts)];
 const rendered=texts(f.get('risk-auto-results')).join(' ');
 assert(rendered.includes('短期趋势偏弱，量能尚未确认企稳。'));
 assert(rendered.includes('继续全文核查'));
});
