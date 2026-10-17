/* Paper trading page: real quotes, simulated fills; every server string is a text node. */
(() => {
 'use strict';
 const $ = id => document.getElementById(id), api = window.apiClient, base = '/paper-trading';
 const sides = {buy:'买入',sell:'卖出'}, types = {limit:'限价',market:'市价'};
 const statuses = {pending:'待成交',filled:'已成交',cancelled:'已撤单',expired:'已失效'};
 const levels = {high:'高风险',medium:'中风险',low:'低风险',unknown:'信息不足'};
 let revision=0, visible=false, accounts=[], accountId=null, side='buy', overview=null;
 let previewData=null, previewVersion=0, previewTimer=null, refreshTimer=null, submitting=false;
 const defaultPreferences={paper_auto_refresh:true,paper_refresh_seconds:15,paper_initial_capital:1000000,paper_commission_rate:0.0003,paper_min_commission:5,paper_order_type:'limit'};
 let preferences={...defaultPreferences};
 let picked=null, searchVersion=0, searchTimer=null, choices=[], active=-1;
 // Held-stock panel: one selected symbol, chart in unadjusted prices so the cost line is comparable.
 const PAGE=8, MARKET='/api/v1/market', periods={minute:'分时',day:'日K',week:'周K',month:'月K'};
 let page=0, selected=null, stockVersion=0, stockController=null, stockQuote=null, stockData=null, stockTrades=[];
 let stockPeriod='minute', stockFetched=0, stockState={count:80,start:null,time:null,hover:false};
 const CODE=/^(?:\d{6}(?:\.(?:sh|sz|bj))?|(?:sh|sz|bj)\d{6})$/i, label=s=>s.name+' '+s.symbol;
 const node=(tag,cls='',text)=>{const n=document.createElement(tag);n.className=cls;if(text!==undefined&&text!==null)n.textContent=String(text);return n;};
 const num=v=>v===null||v===undefined||v===''||!Number.isFinite(Number(v))?null:Number(v);
 const money=v=>num(v)===null?'—':num(v).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
 const pct=v=>num(v)===null?'—':(num(v)>0?'+':'')+(num(v)*100).toFixed(2)+'%';
 const signed=v=>num(v)===null?'—':(num(v)>0?'+':'')+money(v);
 const tone=v=>num(v)>0?'market-up':num(v)<0?'market-down':'market-flat';
 const time=v=>v?new Date(v).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'—';
 const clock=v=>new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(v));
 const big=v=>num(v)===null?'—':num(v)>=1e8?money(num(v)/1e8)+' 亿':num(v)>=1e4?money(num(v)/1e4)+' 万':money(v);
 const status=(text,error=false)=>{for(const id of ['paper-status','paper-order-status']){$(id).textContent=text;$(id).className='paper-note'+(error?' error':'');}};
 async function request(path,options={}){
  const mine=revision,data=await api.request(base+path,{timeout:15000,...options});
  if(mine!==revision)throw Object.assign(Error('账号已变化'),{name:'StaleResponseError'});
  return data;
 }
 const quiet=error=>error.name==='StaleResponseError';
 function cell(row,text,cls=''){const td=node('td',cls,text);row.append(td);return td;}
 function empty(body,cols,text){const tr=node('tr');const td=node('td','paper-empty',text);td.colSpan=cols;tr.append(td);body.replaceChildren(tr);}

 async function loadAccounts(){
  const data=await request('/accounts');accounts=data.accounts||[];
  $('paper-account').replaceChildren(...accounts.map(a=>{const o=node('option','',a.name+' · 初始 '+money(a.initial_capital));o.value=String(a.id);return o;}));
  if(!accounts.some(a=>a.id===accountId))accountId=accounts[0]?.id ?? null;
  if(accountId!==null)$('paper-account').value=String(accountId);
  $('paper-empty-state').hidden=accounts.length>0;$('paper-workspace').hidden=!accounts.length;
 }
 function metric(id,value,cls=''){$(id).textContent=value;$(id).className=cls;}
 function renderOverview(){
  const o=overview;if(!o)return;
  metric('paper-total',money(o.total_assets));metric('paper-return',pct(o.total_return),tone(o.total_return));
  const d=o.day||{};
  $('paper-day-label').textContent=d.is_today===false&&d.date?'最近交易日盈亏（'+d.date+'）':'今日盈亏';
  metric('paper-day-pnl',d.complete?signed(d.pnl):'—',d.complete?tone(d.pnl):'');
  metric('paper-day-return',d.complete?pct(d.return)+(d.closed_pnl&&num(d.closed_pnl)?' · 含已清仓 '+signed(d.closed_pnl):''):'部分持仓缺少当日行情，暂不计算',d.complete?tone(d.return):'paper-muted');
  metric('paper-available',money(o.available_cash));metric('paper-frozen','冻结 '+money(o.frozen_cash));
  metric('paper-market-value',money(o.market_value));
  $('paper-market-state').textContent=(o.market_open?'交易时段 · 委托按实时行情撮合':'非交易时段 · 可查看，不能成交')+(o.valuation_complete?'':' · 部分持仓使用最近成交价估值')+' · 更新 '+time(o.checked_at);
  renderPositions();
 }
 function renderPositions(){
  const body=$('paper-positions'),list=overview?.positions||[],pages=Math.max(1,Math.ceil(list.length/PAGE));
  page=Math.min(page,pages-1);
  $('paper-pager').hidden=pages<2;$('paper-page-label').textContent='第 '+(page+1)+' / '+pages+' 页 · 共 '+list.length+' 只';
  $('paper-page-prev').disabled=page===0;$('paper-page-next').disabled=page>=pages-1;
  if(!list.length){empty(body,10,'暂无持仓，从左侧下单开始模拟。');return;}
  body.replaceChildren();
  for(const p of list.slice(page*PAGE,page*PAGE+PAGE)){
   const on=p.symbol===selected?.symbol,tr=node('tr',on?'selected':''),name=node('button','paper-link',p.name);name.type='button';name.append(node('small','',p.symbol));
   name.setAttribute('aria-pressed',String(on));name.title='查看K线与持仓详情';
   name.addEventListener('click',()=>selectStock(p.symbol,p.name));
   const td=node('td');td.append(name);tr.append(td);
   cell(tr,p.quantity+' / '+p.sellable+(p.frozen?' (冻结 '+p.frozen+')':''));
   cell(tr,money(p.average_cost));cell(tr,money(p.price)+(p.price_live?'':' *'),p.price_live?'':'paper-muted');
   cell(tr,money(p.market_value));
   const day=cell(tr,p.day_pnl===null||p.day_pnl===undefined?'—':signed(p.day_pnl),tone(p.day_pnl));
   if(p.day_pct!==null&&p.day_pct!==undefined)day.append(node('small','',p.day_suspended?'停牌':pct(p.day_pct)));
   cell(tr,money(p.unrealized_pnl),tone(p.unrealized_pnl));
   cell(tr,pct(p.unrealized_pct),tone(p.unrealized_pct));cell(tr,pct(p.weight));
   const act=node('td','paper-actions'),sellBtn=node('button','btn paper-small','卖出'),ask=node('button','btn paper-small','AI 研究');
   sellBtn.type=ask.type='button';sellBtn.addEventListener('click',()=>pick(p.symbol,'sell',p.name));
   ask.addEventListener('click',()=>window.researchStock?.({name:p.name,symbol:p.symbol}));
   act.append(sellBtn,ask);tr.append(act);body.append(tr);
  }
 }
 const marketCode=s=>s.slice(7).toLowerCase()+s.slice(0,6);
 const held=()=>overview?.positions?.find(p=>p.symbol===selected?.symbol)||null;
 function stopStock(){stockVersion++;stockController?.abort();stockController=null;}
 function clearStock(){
  stopStock();selected=null;stockQuote=null;stockData=null;stockTrades=[];stockFetched=0;
  $('paper-stock-body').hidden=true;$('paper-stock-empty').hidden=false;$('paper-stock-chart').replaceChildren();$('paper-stock-facts').replaceChildren();
  for(const id of ['paper-stock-inspect','paper-stock-note','paper-stock-status'])$(id).textContent='';
  $('paper-stock-refresh').disabled=false;
 }
 // Keep the user's pick across refreshes; fall back to the first holding when it is sold out.
 function syncSelection(){
  const list=overview?.positions||[];
  if(selected&&list.some(p=>p.symbol===selected.symbol)){paintStock();loadStock(false);return;}
  if(list.length){const index=list.findIndex(p=>p.symbol===selected?.symbol);selectStock(list[index<0?0:index].symbol,list[index<0?0:index].name,false);}
  else clearStock();
 }
 function selectStock(symbol,name,reveal=true){
  if(selected?.symbol===symbol){if(reveal)$('paper-stock').scrollIntoView?.({block:'nearest',behavior:'smooth'});return;}
  stopStock();selected={symbol,name};stockQuote=null;stockData=null;stockTrades=[];stockFetched=0;stockState={count:80,start:null,time:null,hover:false};
  const index=(overview?.positions||[]).findIndex(p=>p.symbol===symbol);if(index>=0)page=Math.floor(index/PAGE);
  renderPositions();paintStock();loadStock(true);
  if(reveal)$('paper-stock').scrollIntoView?.({block:'nearest',behavior:'smooth'});
 }
 function fact(list,k,v,cls=''){const d=node('div');d.append(node('dt','',k),node('dd',cls,v));list.append(d);}
 function paintStock(loading=false){
  if(!selected)return;
  const q=stockQuote,p=held(),facts=$('paper-stock-facts');
  $('paper-stock-empty').hidden=true;$('paper-stock-body').hidden=false;
  $('paper-stock-name').textContent=q?.name||p?.name||selected.name||selected.symbol;$('paper-stock-code').textContent=selected.symbol;
  const change=num(q?.change_percent)===null?null:num(q.change_percent)/100;
  metric('paper-stock-price',money(q?.price??p?.price),tone(change));
  metric('paper-stock-change',q?signed(q.change)+' / '+pct(change):'—',tone(change));
  facts.replaceChildren();
  for(const [k,v] of [['今开',money(q?.open)],['昨收',money(q?.previous_close)],['最高',money(q?.high)],['最低',money(q?.low)],['成交量（手）',big(q?.volume_lots)],['成交额（元）',big(q?.amount_yuan)]])fact(facts,k,v);
  if(p){
   fact(facts,'持仓 / 可卖',p.quantity+' / '+p.sellable+' 股');fact(facts,'成本价',money(p.average_cost));
   fact(facts,'持仓市值',money(p.market_value));fact(facts,'仓位',pct(p.weight));
   fact(facts,'浮动盈亏',signed(p.unrealized_pnl)+' · '+pct(p.unrealized_pct),tone(p.unrealized_pnl));
   fact(facts,'今日盈亏',p.day_pnl===null||p.day_pnl===undefined?'—':signed(p.day_pnl)+(p.day_suspended?' · 停牌':''),tone(p.day_pnl));
  }
  for(const b of document.querySelectorAll('[data-paper-period]')){const on=b.dataset.paperPeriod===stockPeriod;b.className='paper-stock-tab'+(on?' active':'');b.setAttribute('aria-pressed',String(on));}
  $('paper-stock-zoom').hidden=stockPeriod==='minute';
  const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const day=stockData?.trade_date||q?.quote_time?.slice(0,10);
  $('paper-stock-status').textContent=loading?'正在获取真实行情…':q?.stale||stockData?.stale?'连接异常 · 数据已标记过期':day&&day!==today?'最近交易日 '+day+' · 当前无当日数据':q?'行情时间 '+time(q.quote_time):'';
  const notes=[];if(stockData?.error)notes.push(stockData.error);
  if(p)notes.push('金色虚线：持仓成本 '+money(p.average_cost)+'（仅在图表价格区间内显示）· B / S：本账户买入 / 卖出成交。');
  notes.push(stockPeriod==='minute'?'白线：价格 · 金线：成交均价。':periods[stockPeriod]+'为不复权价格，与成本价同口径 · 均线白/粉/黄：MA5/10/20 · 量线白/粉：MA5/10。');
  $('paper-stock-note').textContent=notes.join(' ');
  const host=$('paper-stock-chart');
  if(!stockData){host.replaceChildren();host.textContent=loading?'正在获取真实行情…':'暂无图表数据';$('paper-stock-inspect').textContent='';return;}
  const marks=stockTrades.filter(t=>t.symbol===selected.symbol).map(t=>({date:t.trade_date,time:clock(t.executed_at),side:t.side}));
  window.MarketChart?.render(host,{period:stockPeriod,data:stockData,state:stockState,levels:p?[{price:p.average_cost,label:'成本'}]:[],marks,onInspect:text=>{$('paper-stock-inspect').textContent=text;}});
 }
 async function loadStock(force){
  if(!selected||accountId===null)return;
  stopStock();
  const mine=++stockVersion,rev=revision,id=accountId,symbol=selected.symbol,code=marketCode(symbol),frame=stockPeriod;
  const controller=new AbortController();stockController=controller;const timer=setTimeout(()=>controller.abort(),18000);
  const chartDue=force||!stockData||Date.now()-stockFetched>=30000,signal=controller.signal;
  if(force)paintStock(true);$('paper-stock-refresh').disabled=true;
  const market=path=>api.request(MARKET+path,{signal,timeout:18000});
  try{
   const [quote,series,trades]=await Promise.allSettled([
    market('/quotes?symbols='+code),
    chartDue?market(frame==='minute'?'/minutes/'+code:'/klines/'+code+'?period='+frame+'&adjustment=none'):Promise.resolve(null),
    api.request(base+'/accounts/'+id+'/trades?'+new URLSearchParams({symbol,limit:'200'}),{signal,timeout:15000})]);
   if(mine!==stockVersion||rev!==revision||selected?.symbol!==symbol||stockPeriod!==frame)return;
   const found=quote.status==='fulfilled'?quote.value.quotes?.find(q=>q.symbol===symbol||q.code===code):null;
   stockQuote=found?{...found,stale:found.stale||quote.value.stale}:stockQuote?{...stockQuote,stale:true}:null;
   if(chartDue){
    stockFetched=Date.now();const v=series.value;
    if(series.status==='fulfilled'&&v?.code===code&&(frame==='minute'?v.points?.length:v.period===frame&&v.bars?.length))stockData=v;
    else stockData=stockData?{...stockData,stale:true,error:'图表更新失败，保留已有真实数据。'}:{error:series.reason?.message||v?.error||'源暂无数据'};
   }
   if(trades.status==='fulfilled')stockTrades=trades.value.trades||[];
   paintStock();
   if(!found)$('paper-stock-status').textContent=quote.reason?.message||'报价获取失败 · 图表以源记录为准';
  }finally{clearTimeout(timer);if(mine===stockVersion){stockController=null;$('paper-stock-refresh').disabled=false;}}
 }
 function changePeriod(next){if(next===stockPeriod||!selected)return;stopStock();stockPeriod=next;stockData=null;stockFetched=0;stockState={count:80,start:null,time:null,hover:false};paintStock(true);loadStock(true);}
 function moveChart(action){
  const n=stockData?.bars?.length||0;if(!n||stockPeriod==='minute')return;
  if(action==='in'||action==='out')stockState.count=Math.min(n,Math.max(15,Math.round(stockState.count*(action==='in'?.7:1.4))));
  else{const start=stockState.start??Math.max(0,n-stockState.count);stockState.start=Math.min(Math.max(0,n-stockState.count),Math.max(0,start+(action==='prev'?-1:1)*Math.max(1,Math.floor(stockState.count/2))));}
  stockState.time=null;stockState.hover=false;paintStock();
 }
 function renderOrders(orders){
  const body=$('paper-orders');if(!orders.length){empty(body,7,'暂无委托。');return;}
  body.replaceChildren();
  for(const o of orders){
   const tr=node('tr');cell(tr,time(o.created_at));cell(tr,o.name+' '+o.symbol);
   cell(tr,sides[o.side]+' · '+types[o.order_type],o.side==='buy'?'market-up':'market-down');
   cell(tr,o.quantity);cell(tr,o.limit_price?money(o.limit_price):'市价');cell(tr,statuses[o.status]||o.status);
   const act=node('td');
   if(o.status==='pending'){const b=node('button','btn paper-small','撤单');b.type='button';b.addEventListener('click',()=>cancel(o.order_id,b));act.append(b);}
   tr.append(act);body.append(tr);
  }
 }
 function renderTrades(trades){
  const body=$('paper-trades');if(!trades.length){empty(body,7,'暂无成交。');return;}
  body.replaceChildren();
  for(const t of trades){
   const tr=node('tr');cell(tr,time(t.executed_at));cell(tr,t.name+' '+t.symbol);
   cell(tr,sides[t.side],t.side==='buy'?'market-up':'market-down');cell(tr,t.quantity+' @ '+money(t.price));
   cell(tr,money(t.amount));
   cell(tr,money(num(t.commission)+num(t.stamp_duty)+num(t.transfer_fee)));
   cell(tr,t.realized_pnl===null?'—':money(t.realized_pnl),tone(t.realized_pnl));body.append(tr);
  }
 }
 function renderAlerts(data){
  const list=$('paper-alerts');list.replaceChildren();
  for(const a of data.alerts){
   const item=node('div','paper-alert '+a.level);item.append(node('span','risk-badge '+a.level,levels[a.level]||a.level),node('strong','',a.name+' '+a.symbol),node('p','',a.message));
   if(a.kind==='risk_event'){const b=node('button','btn paper-small','查看风险事件');b.type='button';b.addEventListener('click',()=>window.selectWorkspacePage?.('risk'));item.append(node('small','','来自风险监控 · '+time(a.analyzed_at)),b);}
   list.append(item);
  }
  if(!data.alerts.length)list.append(node('p','paper-note','当前持仓没有触发风险提示。'));
  if(data.unanalyzed.length)list.append(node('p','paper-note','近 '+data.lookback_days+' 天未做风险分析：'+data.unanalyzed.join('、')+'。可在风险监控中分析。'));
 }
 function chart(series){
  const box=$('paper-chart');box.replaceChildren();
  if(series.length<2){box.append(node('p','paper-note','目前只有 '+series.length+' 个估值点。每个交易日 15:05 记录日终快照，满两个点后显示收益曲线。'));return;}
  const ns='http://www.w3.org/2000/svg',w=640,h=180,pad=8;
  const values=series.flatMap(p=>[num(p.account_return),num(p.benchmark_return)]);
  const lo=Math.min(0,...values),hi=Math.max(0,...values),span=hi-lo||1;
  const x=i=>pad+i*(w-2*pad)/(series.length-1),y=v=>h-pad-(v-lo)*(h-2*pad)/span;
  const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 '+w+' '+h);svg.setAttribute('role','img');
  svg.setAttribute('aria-label','账户收益与沪深300收益对比');
  const line=(key,cls)=>{const p=document.createElementNS(ns,'polyline');p.setAttribute('points',series.map((s,i)=>x(i).toFixed(1)+','+y(num(s[key])).toFixed(1)).join(' '));p.setAttribute('class',cls);svg.append(p);};
  const zero=document.createElementNS(ns,'line');zero.setAttribute('x1',pad);zero.setAttribute('x2',w-pad);zero.setAttribute('y1',y(0));zero.setAttribute('y2',y(0));zero.setAttribute('class','paper-zero');svg.append(zero);
  line('benchmark_return','paper-line-benchmark');line('account_return','paper-line-account');box.append(svg);
 }
 function renderPerformance(p){
  const facts=[['累计收益',pct(p.total_return)],['最大回撤',pct(p.max_drawdown===null?null:-num(p.max_drawdown))],['夏普比率',p.sharpe??'样本不足（需 5 个日收益）'],['年化波动',p.volatility===null?'样本不足（需 5 个日收益）':pct(p.volatility)],['胜率',p.win_rate===null?'暂无平仓（卖出后统计）':pct(p.win_rate)],['已实现盈亏',money(p.realized_pnl)],['盈亏比',p.profit_factor??'—'],['累计费用',money(p.total_fees)]];
  $('paper-metrics').replaceChildren(...facts.map(([k,v])=>{const d=node('div');d.append(node('dt','',k),node('dd','',v));return d;}));
  const b=p.benchmark;
  $('paper-benchmark').textContent=b.available?'对比沪深300（基准日 '+b.base_date+'，收盘 '+money(b.base_close)+'）：超额收益 '+pct(b.excess_return)+(b.stale?' · 指数数据已标记过期':''):'沪深300对比暂不可用：'+(b.reason||'');
  chart(b.series||[]);
  $('paper-performance-note').textContent=(p.notes||[]).join(' ')+(p.incomplete_snapshot_days?' 有 '+p.incomplete_snapshot_days+' 天快照使用了非当日价格。':'');
 }
 async function refresh({full=true}={}){
  if(accountId===null)return;
  const id=accountId;
  try{
   overview=await request('/accounts/'+id);if(id!==accountId)return;renderOverview();syncSelection();
   if(overview.matched_now)status('有 '+overview.matched_now+' 笔挂单已按实时行情成交。');
   const [orders,trades]=await Promise.all([request('/accounts/'+id+'/orders?limit=30'),request('/accounts/'+id+'/trades?limit=30')]);
   if(id!==accountId)return;renderOrders(orders.orders);renderTrades(trades.trades);
   if(full){
    const [perf,alerts]=await Promise.all([request('/accounts/'+id+'/performance'),request('/accounts/'+id+'/risk-alerts')]);
    if(id!==accountId)return;renderPerformance(perf);renderAlerts(alerts);
   }
  }catch(error){if(!quiet(error))status(error.message,true);}
  schedule();
 }
 function schedule(){
  clearTimeout(refreshTimer);refreshTimer=null;
  // Polling only while visible and in session; matching also runs server-side every minute.
  if(preferences.paper_auto_refresh&&visible&&overview?.market_open&&!document.hidden)refreshTimer=setTimeout(()=>refresh({full:false}),preferences.paper_refresh_seconds*1000);
 }

 // Name search uses the public catalog; a typed 6-digit code works without picking a candidate.
 function symbolValue(){const v=$('paper-symbol').value.trim();if(picked&&v===label(picked))return picked.symbol;return CODE.test(v)?v:'';}
 function closeList(){searchVersion++;clearTimeout(searchTimer);choices=[];active=-1;$('paper-symbol-results').replaceChildren();$('paper-symbol-results').hidden=true;$('paper-symbol').setAttribute('aria-expanded','false');$('paper-symbol').setAttribute('aria-activedescendant','');}
 function choose(stock){picked=stock;$('paper-symbol').value=label(stock);closeList();queuePreview();}
 function highlight(index){active=index;choices.forEach((c,i)=>{c.el.className='paper-option'+(i===index?' active':'');c.el.setAttribute('aria-selected',String(i===index));});$('paper-symbol').setAttribute('aria-activedescendant',index>=0?choices[index].el.id:'');}
 async function searchStocks(query){
  const mine=++searchVersion,rev=revision,list=$('paper-symbol-results');
  try{
   const data=await api.request('/stocks/search?'+new URLSearchParams({q:query.slice(0,20),limit:'8'}),{public:true,timeout:8000});
   if(mine!==searchVersion||rev!==revision)return;
   choices=(data.results||[]).map((s,i)=>{const el=node('div','paper-option');el.id='paper-symbol-option-'+i;el.setAttribute('role','option');el.append(node('span','',s.name),node('small','',s.symbol));
    // mousedown keeps focus in the input, so blur does not close the list before the pick.
    el.addEventListener('mousedown',e=>{e.preventDefault();choose(s);});return {stock:s,el};});
   list.replaceChildren(...(choices.length?choices.map(c=>c.el):[node('div','paper-option-empty','未找到匹配的股票，可直接输入 6 位代码。')]));
   list.hidden=false;$('paper-symbol').setAttribute('aria-expanded',String(choices.length>0));highlight(choices.length?0:-1);
  }catch(error){if(mine!==searchVersion||quiet(error)||error.name==='AbortError')return;list.replaceChildren(node('div','paper-option-empty',error.message));list.hidden=false;}
 }
 function symbolInput(){picked=null;const q=$('paper-symbol').value.trim();closeList();queuePreview();if(q)searchTimer=setTimeout(()=>searchStocks(q),250);}
 function setSide(next){
  side=next;for(const b of document.querySelectorAll('[data-paper-side]')){const on=b.dataset.paperSide===side;b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on));}
  $('paper-submit').textContent=sides[side];$('paper-submit').className='btn primary paper-submit '+side;queuePreview();
 }
 function pick(symbol,nextSide,name){picked=name?{symbol,name}:null;$('paper-symbol').value=name?label(picked):symbol;closeList();setSide(nextSide||side);$('paper-quantity').focus();}
 function queuePreview(){clearTimeout(previewTimer);previewTimer=setTimeout(loadPreview,300);}
 async function loadPreview(){
  const symbol=symbolValue(),version=++previewVersion;previewData=null;renderPreview();
  if(!symbol||accountId===null){if($('paper-symbol').value.trim())$('paper-preview').replaceChildren(node('p','paper-note','从候选列表选择股票，或直接输入 6 位代码。'));return;}
  const q=new URLSearchParams({symbol,side,quantity:String(Math.max(0,parseInt($('paper-quantity').value,10)||0))});
  if($('paper-type').value==='limit'&&num($('paper-price').value))q.set('price',Number($('paper-price').value).toFixed(2));
  $('paper-preview').replaceChildren(node('p','paper-note','正在读取真实行情…'));
  try{const data=await request('/accounts/'+accountId+'/preview?'+q);if(version!==previewVersion)return;previewData=data;renderPreview();}
  catch(error){if(version!==previewVersion||quiet(error))return;$('paper-preview').replaceChildren(node('p','paper-note error',error.message));}
 }
 function renderPreview(){
  const p=previewData,box=$('paper-preview');$('paper-submit').disabled=submitting;$('paper-submit').title='';$('paper-risk-ack-wrap').hidden=true;$('paper-risk-ack').checked=false;
  if(!p){box.replaceChildren();return;}
  const head=node('div','paper-quote');head.append(node('strong','',p.name+' '+p.symbol),node('span',tone(num(p.price)-num(p.previous_close)),money(p.price)));
  const rows=[['板块',p.board+' · 涨跌幅 ±'+(num(p.limit_pct)*100).toFixed(0)+'%'],['涨停 / 跌停',money(p.upper_limit)+' / '+money(p.lower_limit)],['交易单位',p.min_quantity+' 股起，'+p.step+' 股递增'],['可用资金',money(p.available_cash)],[side==='buy'?'最多可买':'可卖 / 持仓',side==='buy'?p.max_buy+' 股':p.sellable+' / '+p.holding+' 股'],['行情时间',time(p.quote_time)]];
  if(p.estimate)rows.push(['成交金额',money(p.estimate.amount)],['佣金 / 印花税 / 过户费',money(p.estimate.commission)+' / '+money(p.estimate.stamp_duty)+' / '+money(p.estimate.transfer_fee)],[side==='buy'?'预计支出':'预计到账',money(p.estimate.net)]);
  const dl=node('dl','paper-facts');for(const [k,v] of rows){const d=node('div');d.append(node('dt','',k),node('dd','',v));dl.append(d);}
  box.replaceChildren(head,dl);
  for(const text of [p.market_problem,p.quantity_problem])if(text)box.append(node('p','paper-note error',text));
  $('paper-submit').disabled=Boolean(p.market_problem);$('paper-submit').title=p.market_problem||'';
  if(p.risk_event){
   const r=node('div','paper-alert '+p.risk_event.risk_level);r.append(node('span','risk-badge '+p.risk_event.risk_level,levels[p.risk_event.risk_level]),node('p','',p.risk_event.summary),node('small','','风险监控 · '+time(p.risk_event.analyzed_at)));box.append(r);
   $('paper-risk-ack-wrap').hidden=!p.risk_event.requires_ack;
  }
 }
 async function submit(event){
  event.preventDefault();if(submitting||accountId===null)return;
  const type=$('paper-type').value,body={symbol:symbolValue(),side,order_type:type,quantity:parseInt($('paper-quantity').value,10)};
  if(!body.symbol){status('请从候选列表选择股票，或输入 6 位代码。',true);return;}
  if(!(body.quantity>0)){status('请填写数量。',true);return;}
  if(previewData?.market_problem){status('无法下单：'+previewData.market_problem,true);return;}
  if(type==='limit'){if(!num($('paper-price').value)){status('限价单需要委托价格。',true);return;}body.limit_price=Number($('paper-price').value).toFixed(2);}
  if(previewData?.risk_event?.requires_ack){if(!$('paper-risk-ack').checked){status('请先确认已阅读该股的高风险提示。',true);return;}body.acknowledged_risk_event_id=previewData.risk_event.id;}
  submitting=true;$('paper-submit').disabled=true;const id=accountId;
  try{
   const data=await request('/accounts/'+id+'/orders',{method:'POST',body});
   status(data.trade?sides[side]+'成交 '+data.trade.quantity+' 股 @ '+money(data.trade.price)+'，费用 '+money(num(data.trade.commission)+num(data.trade.stamp_duty)+num(data.trade.transfer_fee))+'。':'委托已挂单，资金/股份已冻结；行情触及委托价时按实时价成交，收盘未成交自动失效。');
   $('paper-quantity').value='';await refresh();queuePreview();
  }catch(error){if(error.status===409&&error.message.includes('高风险'))queuePreview();if(!quiet(error))status(error.unknownOutcome?'连接中断，委托结果待确认，请刷新后核对，勿重复提交。':error.message,true);}
  finally{submitting=false;$('paper-submit').disabled=Boolean(previewData?.market_problem);}
 }
 async function cancel(orderId,button){
  button.disabled=true;
  try{await request('/orders/'+encodeURIComponent(orderId)+'/cancel',{method:'POST'});status('已撤单，冻结资金/股份已释放。');await refresh({full:false});}
  catch(error){button.disabled=false;if(!quiet(error))status(error.message,true);}
 }
 async function createAccount(event){
  event.preventDefault();
  const name=$('paper-new-name').value.trim(),capital=num($('paper-new-capital').value),commission=num($('paper-new-commission').value),minimum=num($('paper-new-min-commission').value);
  if(!name||capital===null||commission===null||minimum===null){status('请填写账户名称、初始资金与佣金参数。',true);return;}
  $('paper-create').disabled=true;
  try{const account=await request('/accounts',{method:'POST',body:{name,initial_capital:capital.toFixed(2),commission_rate:commission.toFixed(6),min_commission:minimum.toFixed(2)}});accountId=account.id;$('paper-new-name').value='';$('paper-create-dialog').close();status('模拟账户已创建。');await loadAccounts();await refresh();}
  catch(error){if(!quiet(error))status(error.message,true);}finally{$('paper-create').disabled=false;}
 }
 async function start(){
  try{await loadAccounts();await refresh();}catch(error){if(!quiet(error))status(error.message,true);}
 }

 $('paper-account').addEventListener('change',()=>{accountId=Number($('paper-account').value);overview=null;page=0;clearStock();refresh();queuePreview();});
 $('paper-page-prev').addEventListener('click',()=>{if(page>0){page--;renderPositions();}});
 $('paper-page-next').addEventListener('click',()=>{page++;renderPositions();});
 for(const b of document.querySelectorAll('[data-paper-period]'))b.addEventListener('click',()=>changePeriod(b.dataset.paperPeriod));
 for(const [id,action] of [['paper-stock-zoom-in','in'],['paper-stock-zoom-out','out'],['paper-stock-earlier','prev'],['paper-stock-later','next']])$(id).addEventListener('click',()=>moveChart(action));
 $('paper-stock-refresh').addEventListener('click',()=>loadStock(true));
 for(const [id,next] of [['paper-stock-buy','buy'],['paper-stock-sell','sell']])$(id).addEventListener('click',()=>{if(selected)pick(selected.symbol,next,stockQuote?.name||held()?.name||selected.name);});
 if(typeof ResizeObserver!=='undefined')new ResizeObserver(()=>{if(visible&&selected&&stockData)paintStock();}).observe($('paper-stock-chart'));
 for(const b of document.querySelectorAll('[data-paper-side]'))b.addEventListener('click',()=>setSide(b.dataset.paperSide));
 for(const id of ['paper-quantity','paper-price'])$(id).addEventListener('input',queuePreview);
 $('paper-symbol').addEventListener('input',symbolInput);
 $('paper-symbol').addEventListener('blur',closeList);
 $('paper-symbol').addEventListener('keydown',e=>{
  if(e.key==='Escape'){closeList();return;}
  if(!choices.length)return;
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();highlight((active+(e.key==='ArrowDown'?1:choices.length-1))%choices.length);}
  else if(e.key==='Enter'&&active>=0){e.preventDefault();choose(choices[active].stock);}
 });
 $('paper-type').addEventListener('change',()=>{$('paper-price').disabled=$('paper-type').value==='market';queuePreview();});
 $('paper-max').addEventListener('click',()=>{if(previewData){$('paper-quantity').value=String(side==='buy'?previewData.max_buy:previewData.sellable);queuePreview();}});
 $('paper-use-price').addEventListener('click',()=>{if(previewData?.price){$('paper-price').value=Number(previewData.price).toFixed(2);queuePreview();}});
 $('paper-order-form').addEventListener('submit',submit);
 $('paper-create-form').addEventListener('submit',createAccount);
 for(const b of [$('paper-open-create'),...document.querySelectorAll('[data-paper-create]')])b.addEventListener('click',()=>{for(const [id,key] of [['paper-new-capital','paper_initial_capital'],['paper-new-commission','paper_commission_rate'],['paper-new-min-commission','paper_min_commission']])$(id).value=String(preferences[key]);$('paper-create-dialog').showModal?.();});
 $('paper-refresh').addEventListener('click',()=>refresh());
 document.addEventListener('visibilitychange',()=>{if(visible&&!document.hidden)refresh({full:false});else schedule();});

 window.paperTrading={
  applyPreferences(p){preferences={...preferences,...p};if(!$('paper-symbol').value&&!$('paper-quantity').value){$('paper-type').value=preferences.paper_order_type;$('paper-price').disabled=preferences.paper_order_type==='market';previewVersion++;previewData=null;$('paper-preview').replaceChildren();}schedule();},
  setVisible(next){const was=visible;visible=Boolean(next);if(visible&&!was)start();else if(!visible)schedule();},
  pick,
  reset(){revision++;previewVersion++;preferences={...defaultPreferences};$('paper-type').value='limit';$('paper-price').disabled=false;picked=null;closeList();clearStock();page=0;stockPeriod='minute';$('paper-pager').hidden=true;clearTimeout(previewTimer);clearTimeout(refreshTimer);visible=false;accounts=[];accountId=null;overview=null;previewData=null;submitting=false;
   for(const id of ['paper-positions','paper-orders','paper-trades','paper-alerts','paper-preview','paper-metrics','paper-chart','paper-account'])$(id).replaceChildren();
   for(const id of ['paper-symbol','paper-quantity','paper-price','paper-new-name'])$(id).value='';
   $('paper-create-dialog').close();$('paper-empty-state').hidden=true;$('paper-workspace').hidden=true;
   $('paper-submit').disabled=false;status('');$('paper-benchmark').textContent='';
   for(const id of ['paper-total','paper-return','paper-day-pnl','paper-day-return','paper-available','paper-frozen','paper-market-value'])metric(id,'—');}
 };
})();
