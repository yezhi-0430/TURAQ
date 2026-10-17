import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Element {
 constructor(tag=''){this.tagName=tag;this.children=[];this.listeners={};this.value='';this.textContent='';this.hidden=false;this.checked=false;this.disabled=false;this.dataset={};this.attrs={};this.classList={toggle(){},add(){},remove(){}};}
 append(...items){this.children.push(...items);} replaceChildren(...items){this.children=items;}
 addEventListener(n,fn){this.listeners[n]=fn;} setAttribute(k,v){this.attrs[k]=v;} focus(){}
 showModal(){this.open=true;} close(){this.open=false;}
}
const els=new Map(),get=id=>{if(!els.has(id))els.set(id,new Element());return els.get(id);};
const buy=new Element('button'),sell=new Element('button');buy.dataset.paperSide='buy';sell.dataset.paperSide='sell';
const tabs=['minute','day','week','month'].map(k=>{const b=new Element('button');b.dataset.paperPeriod=k;return b;});
const text=n=>[n.textContent,...n.children.map(text)].join(' ');
const overview={id:1,name:'主账户',total_assets:'100000.00',total_return:'0.000000',cash:'100000.00',available_cash:'100000.00',frozen_cash:'0.00',market_value:'0.00',valuation_complete:true,market_open:true,matched_now:0,checked_at:'2026-10-14T02:00:00+00:00',day:{date:'2026-10-14',is_today:true,complete:true,pnl:'-12.30',return:'-0.000123',closed_pnl:'0'},
 positions:[{symbol:'600519.SH',name:'<img src=x onerror=alert(1)>',quantity:100,sellable:0,frozen:0,average_cost:'100.05',price:'101.00',price_live:true,market_value:'10100.00',day_pnl:'-12.30',day_pct:'-0.001229',unrealized_pnl:'94.90',unrealized_pct:'0.009485',weight:'0.1'}]};
const preview={symbol:'600519.SH',name:'贵州茅台',price:'100.00',previous_close:'99.00',quote_time:'2026-10-14T10:00:00+08:00',board:'主板',limit_pct:'0.10',min_quantity:100,step:100,lower_limit:'89.10',upper_limit:'108.90',available_cash:'100000.00',max_buy:900,holding:0,sellable:0,quantity_problem:null,market_problem:null,
 estimate:{amount:'10000.00',commission:'5.00',stamp_duty:'0.00',transfer_fee:'0.10',fees:'5.10',net:'10005.10'},risk_event:{id:7,risk_level:'high',summary:'现金流恶化',analyzed_at:'2026-10-12T00:00:00Z',requires_ack:true}};
let calls=[],posts=[],resolveOverview=null,newAccountBody=null;
const api={request:async(path,options={})=>{
 calls.push(path);
 if(path==='/paper-trading/accounts'&&options.method==='POST'){newAccountBody=options.body;return {id:2,name:'新'};}
 if(path==='/paper-trading/accounts')return {accounts:[{id:1,name:'主账户',initial_capital:'100000.00'}]};
 if(path==='/paper-trading/accounts/1')return resolveOverview?new Promise(r=>{resolveOverview=r;}):overview;
 if(path.startsWith('/paper-trading/accounts/1/orders?'))return {orders:[{order_id:'o-1',name:'贵州茅台',symbol:'600519.SH',side:'buy',order_type:'limit',quantity:100,limit_price:'95.00',status:'pending',created_at:'2026-10-14T02:00:00Z'}]};
 if(path.startsWith('/paper-trading/accounts/1/trades?')&&path.includes('symbol='))return {trades:[{symbol:'600519.SH',side:'buy',trade_date:'2026-10-14',executed_at:'2026-10-14T02:05:00+00:00'}]};
 if(path.startsWith('/paper-trading/accounts/1/trades'))return {trades:[]};
 if(path==='/api/v1/market/quotes?symbols=sh600519'){assert(options.signal,'market requests are abortable');return {quotes:[{code:'sh600519',symbol:'600519.SH',name:'贵州茅台',price:'101.00',change:'1.00',change_percent:'1.00',open:'100.00',previous_close:'100.00',high:'102.00',low:'99.50',volume_lots:'12345',amount_yuan:'125000000',quote_time:'2026-10-14T10:05:00+08:00',stale:false}],stale:false};}
 if(path==='/api/v1/market/minutes/sh600519')return {code:'sh600519',trade_date:'2026-10-14',previous_close:'100.00',points:[{time:'09:30',price:'100.00'},{time:'10:05',price:'101.00'}],stale:false};
 if(path==='/api/v1/market/klines/sh600519?period=day&adjustment=none')return {code:'sh600519',period:'day',adjustment:'none',bars:[{date:'2026-10-14',open:'100',close:'101',high:'102',low:'99.5'}],stale:false};
 if(path==='/paper-trading/accounts/1/performance')return {total_return:'0',max_drawdown:'0',sharpe:null,volatility:null,win_rate:null,realized_pnl:'0',profit_factor:null,total_fees:'0',notes:['n'],benchmark:{available:false,reason:'暂无快照',series:[]}};
 if(path==='/paper-trading/accounts/1/risk-alerts')return {alerts:[{kind:'risk_event',level:'high',symbol:'600519.SH',name:'贵州茅台',message:'现金流恶化',analyzed_at:'2026-10-12T00:00:00Z'}],unanalyzed:[],lookback_days:30};
 if(path.startsWith('/paper-trading/accounts/1/preview?'))return preview;
 if(path.startsWith('/stocks/search?')){assert.equal(options.public,true);return {results:[{symbol:'600519.SH',name:'贵州茅台'},{symbol:'600000.SH',name:'浦发银行'}]};}
 if(path==='/paper-trading/accounts/1/orders'){posts.push(options.body);return new Promise(r=>setTimeout(()=>r({order:{},trade:{quantity:100,price:'100.00',commission:'5.00',stamp_duty:'0.00',transfer_fee:'0.10'}}),5));}
 if(path==='/paper-trading/orders/o-1/cancel')return {status:'cancelled'};
 throw Error(path);
}};
let charts=[];
const context={console,URLSearchParams,Number,Math,Date,setTimeout,clearTimeout,AbortController,
 window:{apiClient:api,selectWorkspacePage:async()=>{},MarketChart:{render:(host,opts)=>charts.push(opts)}},
 document:{hidden:false,getElementById:get,createElement:t=>new Element(t),createElementNS:(_,t)=>new Element(t),querySelectorAll:s=>s==='[data-paper-side]'?[buy,sell]:s==='[data-paper-period]'?tabs:[],addEventListener(){}}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/paper-trading.js','utf8'),context);
const flush=async(ms=0)=>{for(let i=0;i<10;i++)await new Promise(r=>setTimeout(r,ms));};
const pt=context.window.paperTrading;

pt.setVisible(true);await flush();
assert.equal(get('paper-workspace').hidden,false);
assert.equal(get('paper-total').textContent,'100,000.00');
const row=get('paper-positions').children[0];
assert(text(row).includes('<img src=x onerror=alert(1)>'),'names render as text');
assert.equal(get('paper-orders').children.length,1);
let researched=null;context.window.researchStock=s=>{researched=s;};
await row.children[9].children[1].listeners.click();
assert.equal(researched.symbol,'600519.SH','position hands off to the research assistant');
assert.equal(get('paper-day-pnl').textContent,'-12.30');assert.equal(get('paper-day-pnl').className,'market-down');
assert.equal(get('paper-day-label').textContent,'今日盈亏');
assert(text(row.children[5]).includes('-12.30')&&text(row.children[5]).includes('-0.12%'),'per-position day P&L');
assert(text(get('paper-alerts')).includes('现金流恶化'));

// Held-stock panel: the first holding is shown automatically with its real quote, cost line and fills.
assert.equal(get('paper-stock-body').hidden,false);assert.equal(get('paper-stock-empty').hidden,true);
assert.equal(get('paper-stock-code').textContent,'600519.SH');
assert.equal(get('paper-stock-price').textContent,'101.00');assert.equal(get('paper-stock-price').className,'market-up');
assert(text(get('paper-stock-facts')).includes('125.00 亿')===false&&text(get('paper-stock-facts')).includes('1.25 亿'),'amount in 亿');
assert(text(get('paper-stock-facts')).includes('100.05')&&text(get('paper-stock-facts')).includes('100 / 0 股'),'position facts');
let last=charts.at(-1);
assert.equal(last.period,'minute');assert.equal(last.levels[0].price,'100.05');assert.equal(last.levels[0].label,'成本');
assert.deepEqual({...last.marks[0]},{date:'2026-10-14',time:'10:05',side:'buy'},'fill marked at Beijing time');
assert(calls.some(c=>c.startsWith('/paper-trading/accounts/1/trades?')&&c.includes('symbol=600519.SH')));
assert.equal(row.className,'selected');
tabs[1].listeners.click();await flush();
last=charts.at(-1);assert.equal(last.period,'day');assert.equal(get('paper-stock-zoom').hidden,false);
assert(calls.includes('/api/v1/market/klines/sh600519?period=day&adjustment=none'),'K line uses unadjusted prices, same basis as cost');
get('paper-stock-sell').listeners.click();assert.equal(get('paper-submit').textContent,'卖出');get('paper-stock-buy').listeners.click();assert.equal(get('paper-symbol').value,'贵州茅台 600519.SH');assert.equal(get('paper-submit').textContent,'买入');
const holdings=overview.positions;
assert.equal(get('paper-pager').hidden,true,'one page hides the pager');
assert(text(get('paper-metrics')).includes('样本不足'),'no fake sharpe');

get('paper-symbol').value='600519';get('paper-quantity').value='100';get('paper-type').value='market';
get('paper-symbol').listeners.input();await flush(40);
assert(calls.some(c=>c.startsWith('/paper-trading/accounts/1/preview?')&&c.includes('quantity=100')));
assert(text(get('paper-preview')).includes('10,005.10'),'fee preview shows net cost');
assert.equal(get('paper-risk-ack-wrap').hidden,false);

const ev={preventDefault(){}};
// Name lookup: typing a name searches the catalog, keyboard picks a candidate, preview uses its code.
get('paper-symbol').value='茅台';get('paper-symbol').listeners.input();await flush(40);
assert(calls.some(c=>c.startsWith('/stocks/search?')&&c.includes(encodeURIComponent('茅台'))));
assert(!calls.some(c=>c.includes('preview?symbol=%E8')),'a bare name is never sent as a symbol');
assert.equal(get('paper-symbol-results').children.length,2);
assert.equal(get('paper-symbol').attrs['aria-expanded'],'true');
get('paper-symbol').listeners.keydown({key:'ArrowDown',preventDefault(){}});
get('paper-symbol').listeners.keydown({key:'ArrowUp',preventDefault(){}});
get('paper-symbol').listeners.keydown({key:'Enter',preventDefault(){}});
assert.equal(get('paper-symbol').value,'贵州茅台 600519.SH');
assert.equal(get('paper-symbol-results').hidden,true);
await flush(40);
assert(calls.at(-1).startsWith('/paper-trading/accounts/1/preview?')&&calls.at(-1).includes('symbol=600519.SH'));
await get('paper-order-form').listeners.submit(ev);
assert.equal(posts.length,0,'high risk requires acknowledgement');
assert(get('paper-status').textContent.includes('高风险'));
get('paper-risk-ack').checked=true;
const first=get('paper-order-form').listeners.submit(ev);
await get('paper-order-form').listeners.submit(ev);
await first;await flush();
assert.equal(posts.length,1,'duplicate submit ignored');
assert.equal(posts[0].acknowledged_risk_event_id,7);
assert.equal(posts[0].order_type,'market');assert.equal(posts[0].limit_price,undefined);
assert(get('paper-status').textContent.includes('成交 100 股'));

await get('paper-orders').children[0].children[6].children[0].listeners.click();
assert(calls.includes('/paper-trading/orders/o-1/cancel'));

get('paper-max').listeners.click();assert.equal(get('paper-quantity').value,'900');
preview.market_problem='当前不在交易时段（工作日 9:30-11:30、13:00-15:00）';
get('paper-quantity').listeners.input();await flush(40);
assert.equal(get('paper-submit').disabled,true,'closed market disables the order button');
const before=posts.length;await get('paper-order-form').listeners.submit(ev);
assert.equal(posts.length,before);
assert(get('paper-order-status').textContent.includes('不在交易时段'),'reason shown next to the button');
preview.market_problem=null;get('paper-quantity').listeners.input();await flush(40);
assert.equal(get('paper-submit').disabled,false);

// Pagination: 8 per page, page survives refresh and clamps when holdings shrink.
overview.positions=Array.from({length:19},(_,i)=>({...holdings[0],symbol:String(600000+i).padStart(6,'0')+'.SH',name:'股票'+i}));
await get('paper-refresh').listeners.click();await flush();
assert.equal(get('paper-pager').hidden,false);assert.equal(get('paper-positions').children.length,8);
assert.equal(get('paper-page-label').textContent,'第 1 / 3 页 · 共 19 只');
assert.equal(get('paper-stock-code').textContent,'600000.SH','sold-out pick falls back to the first holding');
get('paper-page-next').listeners.click();get('paper-page-next').listeners.click();
assert.equal(get('paper-positions').children.length,3);assert.equal(get('paper-page-next').disabled,true);
await get('paper-refresh').listeners.click();await flush();
assert.equal(get('paper-page-label').textContent,'第 3 / 3 页 · 共 19 只','page kept across refresh');
overview.positions=overview.positions.slice(0,10);await get('paper-refresh').listeners.click();await flush();
assert.equal(get('paper-page-label').textContent,'第 2 / 2 页 · 共 10 只','page clamps when holdings shrink');
get('paper-page-next').listeners.click();get('paper-positions').children[1].children[0].children[0].listeners.click();await flush();
assert.equal(get('paper-stock-code').textContent,'600009.SH');assert.equal(get('paper-positions').children[1].className,'selected');
overview.positions=overview.positions.slice(0,3);await get('paper-refresh').listeners.click();await flush();
assert.equal(get('paper-page-label').textContent,'第 1 / 1 页 · 共 3 只');assert.equal(get('paper-pager').hidden,true);
overview.positions=holdings;

resolveOverview=true;const late=get('paper-refresh').listeners.click();await flush();
pt.reset();resolveOverview({...overview,total_assets:'1.00'});await late;await flush();
assert.equal(get('paper-positions').children.length,0,'reset ignores late account data');
assert.notEqual(get('paper-total').textContent,'1.00');
assert.equal(get('paper-workspace').hidden,true);
assert.equal(get('paper-stock-body').hidden,true,'reset clears the stock panel');
pt.applyPreferences({paper_auto_refresh:false,paper_refresh_seconds:60,paper_initial_capital:250000,paper_commission_rate:0.0001,paper_min_commission:2,paper_order_type:'market'});
get('paper-open-create').listeners.click();
assert.equal(get('paper-new-capital').value,'250000');
assert.equal(get('paper-new-commission').value,'0.0001');
assert.equal(get('paper-type').value,'market');
get('paper-new-name').value='个性化账户';
resolveOverview=null;
await get('paper-create-form').listeners.submit({preventDefault(){}});await flush();
assert.equal(newAccountBody.commission_rate,'0.000100');
assert.equal(newAccountBody.min_commission,'2.00');
assert.equal(newAccountBody.initial_capital,'250000.00');
get('paper-symbol').value='600519';get('paper-quantity').value='100';get('paper-type').value='limit';
pt.applyPreferences({paper_auto_refresh:false,paper_refresh_seconds:60,paper_order_type:'market'});
assert.equal(get('paper-type').value,'limit','saving defaults must preserve an existing order draft');
pt.reset();
get('paper-open-create').listeners.click();
assert.equal(get('paper-new-capital').value,'1000000','logout clears previous account creation preferences');
pt.reset();

const html=fs.readFileSync('frontend/index.html','utf8');
assert(html.includes('id="trading-page"')&&html.includes('./paper-trading.js'));
assert(!html.includes('模拟交易<small>筹备中</small>'));
assert(fs.readFileSync('frontend/vite.config.js','utf8').includes('paper-trading'));
console.log('PASS: paper trading render, preview, risk acknowledgement, duplicate submit, cancel, stale reset');
