import { installComponentAPI } from './component-api-fixture.mjs';
// DOM/network doubles verify lifecycle without opening a browser or calling a model.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
class Element {
 constructor(){this.children=[];this.listeners={};this.hidden=false;this.checked=true;this.value='';this.attrs={};this.textContent='';}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=[...nodes];this.textContent='';}
 addEventListener(name,fn){this.listeners[name]=fn;}
 setAttribute(name,value){this.attrs[name]=value;}
}
const elements=new Map();const element=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const listeners={},timers=new Map();let timerId=0,calls=[],fail=false,watchStocks=[];
const quote={code:'sh000001',name:'上证指数',price:'3813.79',change:'1.89',change_percent:'0.05',quote_time:'2026-10-09T16:14:00+08:00',fetched_at:'2026-10-11T12:00:00+08:00'};
const context={console,Intl,Date,Map,Set,Number,AbortController,window:{},document:{hidden:false,getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element(),addEventListener:(n,f)=>listeners[n]=f},setTimeout(fn,delay){const id=++timerId;timers.set(id,{fn,delay});return id;},clearTimeout:id=>timers.delete(id),fetch:async(url)=>{calls.push(url);if(fail)throw Error('offline');return{ok:true,json:async()=>url.endsWith('/watchlist')?{stocks:watchStocks}:url.includes('/minutes/')?{trade_date:'2026-10-09',points:[{time:'09:30',price:'3804.09'},{time:'15:00',price:'3813.79'}]}:{quotes:[quote],unavailable:[],stale:false,source:'test',checked_at:'2026-10-11T12:00:00+08:00'}};}};
installComponentAPI(context);vm.createContext(context);vm.runInContext(fs.readFileSync('frontend/market.js','utf8'),context);
const flush=async()=>{for(let i=0;i<6;i++)await new Promise(r=>setImmediate(r));};
assert.equal(calls.length,0,'no network before dashboard opens');
context.window.marketDashboard.setVisible(true);await flush();
// Watchlist completion may queue one immediate refresh; drain it.
for(const [id,t] of [...timers])if(t.delay===0){timers.delete(id);t.fn();}
await flush();
assert(calls.some(x=>x.includes('/quotes?')));
assert.equal(element('market-indices').children.length,4);
assert.equal(element('market-chart').children[0].attrs.role,'img');
assert([...timers.values()].some(t=>t.delay===10000));
context.window.marketDashboard.setVisible(false);assert.equal(timers.size,0,'leaving cancels polling');
context.document.hidden=true;context.window.marketDashboard.setVisible(true);assert.equal(timers.size,0,'hidden tab never polls');
context.document.hidden=false;listeners.visibilitychange();await flush();
fail=true;await element('market-refresh').listeners.click();await flush();assert.equal(element('market-status').textContent,'行情连接失败');assert(element('market-detail-time').textContent.includes('已过期'));
element('market-auto').checked=false;element('market-auto').listeners.change();assert.equal(timers.size,0);
element('market-symbol').value='../../secret';element('market-search').listeners.submit({preventDefault(){}});assert(element('market-search-error').textContent.includes('格式无效'));
context.window.marketDashboard.setVisible(false);
fail=false;watchStocks=[{symbol:'000001.SZ',name:'平安银行'}];
context.window.marketDashboard.invalidateWatchlist();context.window.marketDashboard.setVisible(true);await flush();
assert.equal(element('market-stocks').children.length,1,'new database member syncs');
let opened=0;context.window.marketDetail={open(){opened++;},close(){}};
const row=element('market-stocks').children[0],priceCell=row.children[1];
assert.equal(typeof row.listeners.click,'function','entire stock row opens detail');
row.listeners.click({target:priceCell});assert.equal(opened,1,'clicking price opens detail');
row.listeners.keydown({target:row,key:'Enter',preventDefault(){}});assert.equal(opened,2,'keyboard opens focused row');
row.listeners.click({target:{closest:()=>row.children[0].children[0]}});assert.equal(opened,2,'name button bubbles without a second open');
row.children.at(-1).children[0].listeners.click({stopPropagation(){}});assert.equal(opened,2,'remove stays independent');
watchStocks=[];context.window.marketDashboard.invalidateWatchlist();await flush();
assert.equal(element('market-stocks').children.length,0,'removed database member disappears');
let focusedPreview;
context.window.MarketChart={render(host){
 if(context.document.activeElement===focusedPreview && focusedPreview)
  assert.equal(host.children[0],focusedPreview,'renderer receives existing focused SVG on refresh');
 focusedPreview=new Element();host.replaceChildren(focusedPreview);
}};
await element('market-refresh').listeners.click();await flush();
context.document.activeElement=focusedPreview;
await element('market-refresh').listeners.click();await flush();
context.window.marketDashboard.setVisible(false);
console.log('PASS: lazy load, index rendering, true-series SVG, 10s polling, hidden/exit pause, stale failure, auto-off, invalid search');
