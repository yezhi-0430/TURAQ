/* Independent stock dialog: cancel obsolete requests and pause when hidden/closed. */
(() => {
 'use strict';
 const el=id=>document.getElementById(id),API='/api/v1/market';
 const dialog=el('stock-detail'),tabs=[...document.querySelectorAll('[data-period]')];
 const labels={minute:'分时',day:'日K',week:'周K',month:'月K'};
 const adjustments={none:'不复权',qfq:'前复权',hfq:'后复权'},views=new Map();
 let adjustment='none';
 const fmt=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v))?Number(v).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
 const signed=v=>fmt(v)==='—'?'—':(Number(v)>0?'+':'')+fmt(v)+'%';
 const stamp=v=>v?v.replace('T',' ').replace('+08:00','').replace(/\.\d+$/,''):'—';
 const compact=v=>fmt(v)==='—'?'—':Number(v)>=1e8?fmt(Number(v)/1e8)+' 亿':Number(v)>=1e4?fmt(Number(v)/1e4)+' 万':fmt(v);
 let code=null,period='minute',quote=null,data=null,timer=null,controller=null,revision=0,chartFetched=0,returnFocus=null,previousOverflow='',loading=false;
 let state={count:80,start:null,time:null,hover:false};
 const current=()=>dialog.open&&!document.hidden&&Boolean(code);
 function stop(){revision++;clearTimeout(timer);timer=null;controller?.abort();controller=null;loading=false;}
 function node(tag,text,cls=''){const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;}
 function paint(){
  el('detail-adjustment-wrap').hidden=period==='minute';
  el('detail-adjustment').value=adjustment;
  el('detail-adjustment').disabled=/^(sh000|sh950|sz399|bj899)/.test(code||'');
  for(const tab of tabs){tab.setAttribute('aria-selected',String(tab.dataset.period===period));tab.className='detail-tab'+(tab.dataset.period===period?' active':'');}
  el('detail-price').textContent=fmt(quote?.price);el('detail-percent').textContent=signed(quote?.change_percent);
  const tone=Number(quote?.change_percent)>0?'market-up':Number(quote?.change_percent)<0?'market-down':'market-flat';
  el('detail-price').className=tone;el('detail-percent').className=tone;
  if(quote?.name)el('detail-name').textContent=quote.name;
  el('detail-facts').replaceChildren();
  for(const [label,value] of [['今开',fmt(quote?.open)],['昨收',fmt(quote?.previous_close)],['最高',fmt(quote?.high)],['最低',fmt(quote?.low)],['成交量（手）',compact(quote?.volume_lots)],['成交额（元）',compact(quote?.amount_yuan)]]){
   const n=document.createElement('div');n.append(node('dt',label),node('dd',value));el('detail-facts').append(n);
  }
  const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const day=data?.trade_date||quote?.quote_time?.slice(0,10),old=day&&day!==today;
  el('detail-status').textContent=loading?'正在获取真实行情…':quote?.stale||data?.stale?'连接异常 · 数据已标记过期':old?'最近交易日行情 · 当前无当日数据':'以源行情时间为准';
  const notices=[];if(quote?.stale)notices.push('报价更新失败，保留旧报价。');if(data?.error)notices.push(data.error);
  if(period!=='minute')notices.push(labels[period]+' · '+adjustments[adjustment]+'价格 · 涨跌幅按上一根同口径K线收盘价计算。'+(['week','month'].includes(period)?'最后一根可能为尚未结束的本周/本月。':''));
  if(period!=='minute')notices.push('均线：白 MA5 · 粉 MA10 · 黄 MA20（同口径收盘价）；量线：白 MA5 · 粉 MA10。');
  if(data?.latest_bar_source==='daily_aggregation')notices.push('最新月K由同口径真实日线汇总。');
  if(period==='minute')notices.push('白线：价格 · 金线：成交均价 · 首个量柱包含开盘累计量；缺失分钟的量合并在下一条源记录。');
  if(old)notices.push('当前图表交易日 '+day+'，休市期间保留最近交易日记录。');
  el('detail-notice').textContent=notices.join(' ');
  el('detail-times').textContent='来源：腾讯财经公开行情 · 行情时间 '+stamp(quote?.quote_time)+' · 图表获取 '+stamp(data?.fetched_at);
  el('detail-range').hidden=period==='minute';
  const n=(data?.bars||[]).length;el('detail-range-label').textContent=period==='minute'?'':`共 ${n} 根 · 当前最多 ${state.count} 根`;
  window.MarketChart.render(el('detail-chart'),{period,data,state,onInspect:text=>{el('detail-inspect').textContent=text;}});
 }
 function schedule(){clearTimeout(timer);if(current()&&el('detail-auto').checked)timer=setTimeout(()=>refresh(),(window.settingsCenter?.preferences.market_refresh_seconds||10)*1000);}
 async function request(path,signal){return window.apiClient.request(API+path,{signal});}
 async function refresh(force=false){
  if(!current())return;
  if(loading){if(!force)return;stop();}
  clearTimeout(timer);loading=true;const mine=revision,target=code,frame=period,basis=adjustment;
  controller=new AbortController();const signal=controller.signal,abort=controller;const timeout=setTimeout(()=>abort.abort(),18000);
  el('detail-status').textContent='正在获取真实行情…';el('detail-refresh').disabled=true;
  const updateChart=force||!data||Date.now()-chartFetched>=30000;
  try{
   const responses=await Promise.allSettled([request('/quotes?symbols='+target,signal),updateChart?request(frame==='minute'?'/minutes/'+target:'/klines/'+target+'?period='+frame+'&adjustment='+basis,signal):Promise.resolve(null)]);
   if(mine!==revision||!current())return;
   const [snapshot,series]=responses;
   const found=snapshot.status==='fulfilled'?snapshot.value.quotes?.find(q=>q.code===target):null;
   quote=found?{...found,stale:found.stale||snapshot.value.stale}:quote?{...quote,stale:true}:null;
   if(updateChart){
    chartFetched=Date.now();
    if(series.status==='fulfilled'&&series.value?.code===target&&(frame==='minute'||(series.value.period===frame&&series.value.adjustment===basis))){
     if((frame==='minute'?series.value.points:series.value.bars)?.length)data=series.value;
     else data=data?{...data,stale:true,error:series.value.error||'源暂无数据'}:series.value;
    }else data={...data,stale:true,error:series.reason?.message||'图表更新失败，保留已有真实数据。'};
   }
   loading=false;paint();if(!found)el('detail-status').textContent=snapshot.reason?.message||'报价获取失败 · 图表以源记录为准';
   if(data)views.set(frame+':'+(frame==='minute'?'none':basis),{data,chartFetched,state:{...state}});
  }finally{
   clearTimeout(timeout);
   if(mine===revision){loading=false;controller=null;el('detail-refresh').disabled=false;schedule();}
  }
 }
 function open(symbol,name){
  stop();if(!dialog.open){returnFocus=document.activeElement;previousOverflow=document.body.style.overflow;dialog.showModal();document.body.style.overflow='hidden';}
  dialog.scrollTop=0;
  const prefs=window.settingsCenter?.preferences;
  views.clear();adjustment=prefs?.chart_adjustment||'none';if(/^(sh000|sh950|sz399|bj899)/.test(symbol))adjustment='none';
  el('detail-auto').checked=prefs?.market_auto_refresh??true;
  code=symbol;period=prefs?.chart_period||'minute';quote=null;data=null;chartFetched=0;state={count:80,start:null,time:null,hover:false};
  el('detail-name').textContent=name||symbol;el('detail-symbol').textContent=symbol.slice(2)+'.'+symbol.slice(0,2).toUpperCase();
  paint();refresh(true);
 }
 function close(){if(dialog.open)dialog.close();}
 dialog.addEventListener('close',()=>{stop();const opener=returnFocus?.getAttribute('data-code');const focus=opener?document.querySelector?.('.stock-select[data-code="'+opener+'"]'):returnFocus;code=null;document.body.style.overflow=previousOverflow;el('detail-refresh').disabled=false;(focus||el('market-symbol'))?.focus();});
 el('detail-close').addEventListener('click',close);
 dialog.addEventListener('click',event=>{if(event.target!==dialog)return;const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)close();});
 function changeView(nextPeriod,nextAdjustment){
  const previousState={...state},samePeriod=nextPeriod===period;
  if(data)views.set(period+':'+(period==='minute'?'none':adjustment),{data,chartFetched,state:previousState});
  stop();period=nextPeriod;adjustment=nextAdjustment;
  const cached=views.get(period+':'+(period==='minute'?'none':adjustment));
  data=cached?.data||null;chartFetched=cached?.chartFetched||0;
  state={...(samePeriod?previousState:cached?.state||{count:80,start:null,time:null}),hover:false};
  paint();refresh(true);
 }
 for(const tab of tabs)tab.addEventListener('click',()=>{if(tab.dataset.period!==period)changeView(tab.dataset.period,adjustment);});
 el('detail-adjustment').addEventListener('change',()=>{const value=el('detail-adjustment').value;if(period!=='minute'&&adjustments[value]&&value!==adjustment)changeView(period,value);});
 el('detail-refresh').addEventListener('click',()=>refresh(true));
 el('detail-auto').addEventListener('change',()=>{clearTimeout(timer);if(el('detail-auto').checked)refresh();});
 document.addEventListener('visibilitychange',()=>{stop();if(current())refresh(true);});
 for(const [id,action] of [['detail-zoom-in','in'],['detail-zoom-out','out'],['detail-previous','prev'],['detail-next','next']])el(id).addEventListener('click',()=>{
  const n=data?.bars?.length||0;if(!n)return;
  if(action==='in'||action==='out'){state.count=Math.min(n,Math.max(15,Math.round(state.count*(action==='in'?.7:1.4))));}
  else {const start=state.start??Math.max(0,n-state.count);state.start=Math.min(Math.max(0,n-state.count),Math.max(0,start+(action==='prev'?-1:1)*Math.max(1,Math.floor(state.count/2))));}
  state.time=null;state.hover=false;paint();
 });
 if(typeof ResizeObserver!=='undefined')new ResizeObserver(()=>{if(dialog.open)paint();}).observe(el('detail-chart'));
 window.marketDetail={open,close,reset(){stop();close();code=null;quote=null;data=null;views.clear();el('detail-chart').replaceChildren();el('detail-facts').replaceChildren();el('detail-name').textContent='证券详情';el('detail-symbol').textContent='';el('detail-price').textContent='—';el('detail-percent').textContent='—';el('detail-inspect').textContent='';el('detail-times').textContent='';el('detail-notice').textContent='';el('detail-status').textContent='请登录后查看';}};
})();
