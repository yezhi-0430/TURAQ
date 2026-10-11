import { installComponentAPI } from './component-api-fixture.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
class Element {
 constructor(){this.children=[];this.listeners={};this.value='';this.textContent='';}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
 addEventListener(n,fn){this.listeners[n]=fn;}
 setAttribute(){} focus(){} showModal(){this.open=true;} close(){this.open=false;}
}
const els=new Map(),get=id=>{if(!els.has(id))els.set(id,new Element());return els.get(id);};
let groups=[],members=new Map(),next=1,invalidations=0,researched=null;
const context={console,AbortController,setTimeout,clearTimeout,window:{marketDashboard:{invalidateWatchlist(){invalidations++;}},researchStock(s){researched=s;}},document:{getElementById:get,createElement:()=>new Element(),querySelectorAll:()=>[]},fetch:async(url,options)=>{
 const path=new URL(url).pathname,method=options.method,body=options.body?JSON.parse(options.body):null;
 let value=null,status=200;
 if(path==='/api/v1/watchlists'){
  if(method==='POST'){value={id:next++,name:body.name};groups.push(value);members.set(value.id,[]);status=201;}else value=groups;
 }else if(path==='/api/v1/stocks/search'){value={results:[{symbol:'000001.SZ',code:'sz000001',name:'平安银行',market:'SZ'}],total:1};}
 else if(path==='/api/v1/market/quotes'){value={quotes:[{code:'sz000001',symbol:'000001.SZ',name:'平安银行',kind:'stock',quote_time:'2026-10-09T16:15:00+08:00'}]};}
 else{const m=path.match(/watchlists\/(\d+)(?:\/stocks(?:\/(.+))?)?$/);assert(m);const id=Number(m[1]);if(path.includes('/stocks')){if(method==='POST'){members.get(id).push(body);value=body;status=201;}else if(method==='DELETE'){members.set(id,members.get(id).filter(s=>s.symbol!==decodeURIComponent(m[2])));status=204;}else value=members.get(id);}else if(method==='PATCH'){groups.find(g=>g.id===id).name=body.name;value=groups.find(g=>g.id===id);}else if(method==='DELETE'){groups=groups.filter(g=>g.id!==id);members.delete(id);status=204;}}
 return{ok:true,status,json:async()=>JSON.parse(JSON.stringify(value))};
}};
installComponentAPI(context);vm.createContext(context);vm.runInContext(fs.readFileSync('frontend/watchlist.js','utf8'),context);
const event={preventDefault(){}};const flush=async()=>{for(let i=0;i<4;i++)await new Promise(r=>setImmediate(r));};
context.window.watchlistManager.setVisible(true);await flush();
get('watch-group-name').value='核心';await get('watch-create').listeners.submit(event);assert.equal(groups[0].name,'核心');assert.equal(get('watch-title').textContent,'核心');
get('watch-query').value='000001';await get('watch-search').listeners.submit(event);assert.equal(get('watch-results').children.length,1);
await get('watch-results').children[0].children[1].listeners.click();await flush();assert.equal(members.get(1).length,1);
get('watch-members').children[0].children[0].listeners.click();assert.equal(researched.symbol,'000001.SZ');
get('watch-rename').listeners.click();get('watch-rename-value').value='长期';await get('watch-dialog-form').listeners.submit(event);assert.equal(groups[0].name,'长期');
await get('watch-members').children[0].children[1].children[0].listeners.click();await flush();assert.equal(members.get(1).length,0);
get('watch-delete').listeners.click();assert(get('watch-dialog-description').textContent.includes('长期'));await get('watch-dialog-form').listeners.submit(event);assert.equal(groups.length,0);assert.equal(invalidations,5);
console.log('PASS: create, catalog lookup, add, research handoff, rename, remove, delete confirmation, market invalidation');
// A saved mutation with a failed refresh must never look like an empty group.
get('watch-group-name').value='失败恢复';await get('watch-create').listeners.submit(event);
get('watch-query').value='000001';await get('watch-search').listeners.submit(event);
const workingFetch=context.fetch;
context.fetch=async(url,options)=>{if(options.method==='GET' && /watchlists\/\d+\/stocks$/.test(url))throw Error('refresh failed');return workingFetch(url,options);};
await get('watch-results').children[0].children[1].listeners.click();await flush();
assert(get('watch-status').textContent.includes('刷新失败'));
assert(get('watch-members').children[0].textContent.includes('加载失败'));
console.log('PASS: saved mutation preserves refresh-failure state');
// A completed write from an old account must not repopulate status or groups.
context.fetch=workingFetch;
let completeOldWrite;
context.fetch=async(url,options)=>options.method==='POST'&&url.endsWith('/watchlists')?new Promise(resolve=>completeOldWrite=()=>resolve({ok:true,status:201,json:async()=>({id:99,name:'old account group'})})):workingFetch(url,options);
get('watch-group-name').value='old account group';const oldMutation=get('watch-create').listeners.submit(event);
context.window.watchlistManager.reset();completeOldWrite();await oldMutation;await flush();
assert.equal(get('watch-status').textContent,'','old mutation cannot write status after account reset');
assert.equal(get('watch-groups').children.length,0,'old mutation cannot load groups after account reset');
console.log('PASS: stale mutation cannot restore account state');
