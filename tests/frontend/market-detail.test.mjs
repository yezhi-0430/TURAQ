import { installComponentAPI } from './component-api-fixture.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Element {
 constructor(tag='div'){this.tag=tag;this.children=[];this.listeners={};this.attrs={};this.style={};this.textContent='';this.hidden=false;this.checked=true;this.open=false;}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;this.textContent='';}
 setAttribute(k,v){this.attrs[k]=String(v);}
 getAttribute(k){return this.attrs[k];}
 addEventListener(k,fn){this.listeners[k]=fn;}
 removeEventListener(k){delete this.listeners[k];}
 getBoundingClientRect(){return {left:0,top:0,width:1000,height:460};}
 showModal(){this.open=true;}
 close(){this.open=false;this.listeners.close?.();}
 focus(){this.focused=true;}
}
const elements=new Map(), el=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const tabs=['minute','day','week','month'].map(period=>{const b=new Element('button');b.dataset={period};return b;});
const timers=new Map(), docEvents={};let next=0,calls=[],waitResponse=null,clock=Date.now();
class ClockDate extends Date {static now(){return clock;}}
const data={code:'sh600519',trade_date:'2026-10-09',fetched_at:'2026-10-11T12:00:00+08:00',source:'test',previous_close:'10',points:[{time:'09:30',price:'10',average_price:'10',volume_lots:'10',change_percent:'0.00'},{time:'15:00',price:'12',average_price:'11',volume_lots:'5',change_percent:'20.00'}]};
const bars={...data,adjustment:'none',period:'day',bars:[{date:'2026-10-08',open:'10',close:'11',high:'12',low:'9',volume_lots:'10',change_percent:null},{date:'2026-10-09',open:'11',close:'12',high:'13',low:'10',volume_lots:'20',change_percent:'9.09'}]};
const context={console,Intl,Date:ClockDate,Map,Set,Number,Math,AbortController,window:{},document:{hidden:false,activeElement:new Element(),body:{style:{}},getElementById:el,createElement:t=>new Element(t),createElementNS:(_,t)=>new Element(t),querySelectorAll:()=>tabs,addEventListener:(k,fn)=>docEvents[k]=fn},setTimeout:(fn,delay)=>{timers.set(++next,{fn,delay});return next;},clearTimeout:id=>timers.delete(id),fetch:async(url,{signal}={})=>{calls.push(url);if(waitResponse)return waitResponse(url,signal);return {ok:true,json:async()=>url.includes('/quotes?')?{quotes:[{code:url.includes('sz000001')?'sz000001':'sh600519',name:'贵州茅台',price:'12',change_percent:'20',quote_time:data.fetched_at,fetched_at:data.fetched_at}]}:url.includes('/klines/')?{...bars,period:new URL(url).searchParams.get('period'),adjustment:new URL(url).searchParams.get('adjustment')||'none'}:data};}};
installComponentAPI(context);vm.createContext(context);
assert(fs.existsSync('frontend/market-chart.js'),'interactive chart component must exist');
vm.runInContext(fs.readFileSync('frontend/market-chart.js','utf8'),context);
assert(fs.existsSync('frontend/market-detail.js'),'independent detail component must exist');
vm.runInContext(fs.readFileSync('frontend/market-detail.js','utf8'),context);
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
const find=(root,kind)=>{if(root.attrs['data-kind']===kind)return root;for(const c of root.children){const v=find(c,kind);if(v)return v;}};
const compactHost=new Element();compactHost.getBoundingClientRect=()=>({left:0,top:0,width:390,height:290});
context.window.MarketChart.render(compactHost,{data,state:{}});
assert.equal(compactHost.children[0].attrs.viewBox,'0 0 390 290','chart uses actual height so narrow screens retain readable labels');
context.document.activeElement=compactHost.children[0];
context.window.MarketChart.render(compactHost,{data,state:{}});
assert(compactHost.children[0].focused,'automatic redraw retains keyboard chart focus');
const previewHost=new Element();previewHost.getBoundingClientRect=()=>({left:0,top:0,width:700,height:220});
context.window.MarketChart.render(previewHost,{data,state:{},compact:true});
assert.equal(previewHost.children[0].attrs.viewBox,'0 0 700 220','dashboard preview fits its real container');
assert(!find(previewHost,'volume-bar'),'preview uses its height for price; detail retains volume');
const opener=new Element('button');opener.setAttribute('data-code','sh600519');opener.isConnected=false;
const currentOpener=new Element('button');context.document.activeElement=opener;
context.document.querySelector=selector=>selector.includes('sh600519')?currentOpener:null;
assert.equal(calls.length,0,'no requests before dialog opens');
context.window.marketDetail.open('sh600519','贵州茅台');await flush();
assert(el('stock-detail').open);
assert.equal(el('detail-name').textContent,'贵州茅台');
assert(calls.some(u=>u.endsWith('/minutes/sh600519')));
let chart=el('detail-chart').children[0];
assert(find(chart,'average-line'));
assert(find(chart,'volume-bar'));
chart.listeners.pointermove({clientX:925,clientY:140});
assert.equal(find(chart,'crosshair').attrs.visibility,'visible');
assert(el('detail-inspect').textContent.includes('15:00'));
assert(el('detail-inspect').textContent.includes('20.00%'));
async function pollAfter(ms){clock+=ms;const [id,t]=[...timers].find(([,t])=>t.delay===10000);timers.delete(id);await t.fn();await flush();}
const initialMinutes=calls.filter(u=>u.includes('/minutes/')).length,initialQuotes=calls.filter(u=>u.includes('/quotes?')).length;
await pollAfter(10000);
assert.equal(calls.filter(u=>u.includes('/quotes?')).length,initialQuotes+1,'quotes automatically update after 10 seconds');
assert.equal(calls.filter(u=>u.includes('/minutes/')).length,initialMinutes,'chart does not poll faster than 30 seconds');
assert.equal(find(el('detail-chart').children[0],'crosshair').attrs.visibility,'visible','refresh preserves active inspection');
await pollAfter(20000);
assert.equal(calls.filter(u=>u.includes('/minutes/')).length,initialMinutes+1,'true chart data updates after 30 seconds');
chart=el('detail-chart').children[0];
chart.listeners.pointerleave();
assert.equal(find(chart,'crosshair').attrs.visibility,'hidden');
for(const tab of tabs.slice(1)){
 await tab.listeners.click();await flush();
 assert(calls.some(u=>u.includes('period='+tab.dataset.period)));
 assert(find(el('detail-chart').children[0],'candle'));
}
assert.equal(typeof el('detail-adjustment').listeners.change,'function','adjustment selector is connected');
for(const [value,label] of [['qfq','前复权'],['hfq','后复权'],['none','不复权']]){
 el('detail-adjustment').value=value;await el('detail-adjustment').listeners.change();await flush();
 assert(calls.some(u=>u.includes('period=month')&&u.includes('adjustment='+value)));
 assert(el('detail-notice').textContent.includes(label));
 assert(el('detail-inspect').textContent.includes(label),'hover readout names the price basis');
 assert(!el('detail-notice').textContent.includes('白线'),'K-line notices never include minute legend');
 assert.equal(el('detail-price').textContent,'12.00','latest quote is never replaced by adjusted prices');
}
// Rapid adjustment switching must ignore the previous basis even if it responds last.
const pendingBases=[];waitResponse=(url,signal)=>new Promise(resolve=>pendingBases.push({url,signal,resolve}));
for(const value of ['qfq','hfq']){el('detail-adjustment').value=value;el('detail-adjustment').listeners.change();}
const answerBasis=item=>item.resolve({ok:true,json:async()=>item.url.includes('/quotes?')?{quotes:[{code:'sh600519',name:'贵州茅台',price:'12'}]}:{...bars,period:'month',adjustment:new URL(item.url).searchParams.get('adjustment')}});
pendingBases.slice(2).forEach(answerBasis);await flush();pendingBases.slice(0,2).forEach(answerBasis);await flush();
assert(el('detail-inspect').textContent.includes('后复权'),'late forward-adjusted response cannot overwrite backward basis');
waitResponse=null;el('detail-adjustment').value='none';await el('detail-adjustment').listeners.change();await flush();
el('detail-close').listeners.click();
assert(!el('stock-detail').open);
assert(currentOpener.focused,'closing restores focus to the current stock button after table redraw');
assert.equal(timers.size,0,'close clears all pending timers');
// Deliberately deliver an old response after another stock has opened.
const delayed=[];waitResponse=(url,signal)=>new Promise(resolve=>delayed.push({url,signal,resolve}));
context.window.marketDetail.open('sh600519','贵州茅台');
context.window.marketDetail.open('sz000001','平安银行');
const respond=item=>item.resolve({ok:true,json:async()=>item.url.includes('/quotes?')?{quotes:[{code:item.url.includes('sz000001')?'sz000001':'sh600519',name:item.url.includes('sz000001')?'平安银行':'贵州茅台',price:'12'}]}:{...data,code:item.url.includes('sz000001')?'sz000001':'sh600519'}});
delayed.filter(x=>x.url.includes('sz000001')).forEach(respond);await flush();
delayed.filter(x=>x.url.includes('sh600519')).forEach(respond);await flush();
assert.equal(el('detail-name').textContent,'平安银行','late responses never overwrite current stock');
context.document.hidden=true;docEvents.visibilitychange();
assert.equal(timers.size,0,'hidden page pauses detail requests');
context.window.marketDetail.close();
console.log('PASS: modal, real series, VWAP/volume, crosshair, all K periods, close/hidden pause, late-response isolation');
