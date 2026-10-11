/* Read-only market UI. No generated prices, curves or market-wide statistics. */
(() => {
 'use strict';
 const el = id => document.getElementById(id);
 const API = '/api/v1/market';
 const indices = [['sh000001','上证指数'],['sz399001','深证成指'],['sz399006','创业板指'],['sh000300','沪深300']];
 const quotes = new Map(), trends = new Map(), stocks = new Map();
 const chartStates = new Map();
 let selected = 'sh000001', visible = false, busy = false, timer = null, controller = null;
 let failures = 0, queued = false, initialized = false, revision = 0;
 const databaseCodes = new Set(), manualCodes = new Set();
 let watchlistVersion = 0;
 const nf = new Intl.NumberFormat('zh-CN', {maximumFractionDigits:2, minimumFractionDigits:2});
 function node(tag, cls, text) { const n = document.createElement(tag); n.className = cls || ''; if(text !== undefined)n.textContent = text; return n; }
 function validNumber(v) {return v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));}
 function num(v) {return validNumber(v) ? nf.format(Number(v)) : '—';}
 function signed(v, suffix='') {return validNumber(v) ? (Number(v)>0?'+':'')+num(v)+suffix : '—';}
 function tone(v) {return !validNumber(v)||Number(v)===0?'market-flat':Number(v)>0?'market-up':'market-down';}
 function compact(v) {if(!validNumber(v))return '—';const n=Number(v);return Math.abs(n)>=1e8?num(n/1e8)+' 亿':Math.abs(n)>=1e4?num(n/1e4)+' 万':num(n);}
 function stamp(v) {if(!v)return '—';return v.replace('T',' ').replace('+08:00','').replace(/\.\d+$/,'');}
 function canonical(value) {
  let s=value.trim().toLowerCase();
  if(/^\d{6}\.(sh|sz|bj)$/.test(s))s=s.slice(-2)+s.slice(0,6);
  if(/^\d{6}$/.test(s)){const prefix=s.startsWith('92')||/^[48]/.test(s)?'bj':/^6/.test(s)?'sh':/^[03]/.test(s)?'sz':null;if(!prefix)throw Error('请输入完整代码，如 000001.SZ');s=prefix+s;}
  if(!/^(sh|sz|bj)\d{6}$/.test(s))throw Error('代码格式无效，请输入 000001.SZ 或 SH600519');
  return s;
 }
 function name(code) {return quotes.get(code)?.name || indices.find(i=>i[0]===code)?.[1] || stocks.get(code) || code;}
 function current() {return visible && !document.hidden;}
 function banner(text) {el('market-banner').textContent=text;el('market-banner').hidden=!text;}
 async function request(path, signal) {
  return window.apiClient.request(API+path,{signal});
 }
 function render() {
  el('market-indices').replaceChildren();
  for(const [code,label] of indices){
   const q=quotes.get(code),button=node('button','index-card'+(selected===code?' selected':''));button.type='button';button.setAttribute('aria-pressed',String(selected===code));
   const head=node('header');head.append(node('span','',label),node('small','',code.toUpperCase()));
   button.append(head,node('div','index-price',num(q?.price)),node('div','index-change '+tone(q?.change_percent),signed(q?.change)+'  /  '+signed(q?.change_percent,'%')),node('div','index-time',q?(q.stale?'连接异常 · ':'行情 ')+stamp(q.quote_time):'等待真实行情'));
   button.addEventListener('click',()=>choose(code));el('market-indices').append(button);
  }
  el('market-stocks').replaceChildren();el('market-stock-empty').hidden=stocks.size>0;
  for(const [code,label] of stocks){
   const q=quotes.get(code),tr=node('tr','market-stock-row'+(selected===code?' selected':''));
   const openStock=()=>{window.marketDetail?.open(code,q?.name||label);choose(code);};
   tr.setAttribute('tabindex','0');tr.setAttribute('data-code',code);tr.setAttribute('aria-label',(q?.name||label)+'，查看行情详情');
   tr.addEventListener('click',event=>{if(event.target.closest?.('button'))return;openStock();});
   tr.addEventListener('keydown',event=>{if(event.target===tr&&['Enter',' '].includes(event.key)){event.preventDefault();openStock();}});
   const cell=node('td'),button=node('button','stock-select',q?.name || label);button.type='button';button.setAttribute('aria-haspopup','dialog');button.setAttribute('data-code',code);button.append(node('small','',code.slice(2)+'.'+code.slice(0,2).toUpperCase()));button.addEventListener('click',openStock);cell.append(button);tr.append(cell);
   for(const [value,cls] of [[num(q?.price),tone(q?.change_percent)],[signed(q?.change_percent,'%'),tone(q?.change_percent)],[signed(q?.change),tone(q?.change)],[compact(q?.volume_lots),''],[compact(q?.amount_yuan),''],[q?(q.stale?'旧数据 · ':'')+stamp(q.quote_time):'暂无行情','muted']])tr.append(node('td',cls,value));
   const removeCell=node('td'),remove=node('button','stock-remove','×');remove.type='button';remove.setAttribute('aria-label','从当前行情表移除 '+label);remove.addEventListener('click',event=>{event.stopPropagation?.();stocks.delete(code);manualCodes.delete(code);if(selected===code)selected='sh000001';render();draw();});removeCell.append(remove);tr.append(removeCell);el('market-stocks').append(tr);
  }
  const q=quotes.get(selected);
  el('market-chart-title').textContent=name(selected)+' · 分时走势';el('market-detail-symbol').textContent=selected.slice(2)+'.'+selected.slice(0,2).toUpperCase();
  el('market-chart-meta').replaceChildren(node('strong',tone(q?.change_percent),num(q?.price)),node('span',tone(q?.change_percent),signed(q?.change_percent,'%')));
  el('market-facts').replaceChildren();
  for(const [label,value] of [['今开',num(q?.open)],['昨收',num(q?.previous_close)],['最高',num(q?.high)],['最低',num(q?.low)],['成交量（手）',compact(q?.volume_lots)],['成交额（元）',compact(q?.amount_yuan)]]){const group=node('div');group.append(node('dt','',label),node('dd','',value));el('market-facts').append(group);}
  el('market-detail-time').textContent=q?'行情时间 '+stamp(q.quote_time)+'\n获取时间 '+stamp(q.fetched_at)+(q.stale?' · 连接异常，数据可能已过期':''):'暂无可用快照；不以 0 代替缺失价格。';
 }
 function svg(tag,attrs,text){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n;}
 function draw(){
  const data=trends.get(selected),box=el('market-chart');
  if(!data?.points?.length){box.replaceChildren();box.textContent=data?.error || '正在加载真实分时…';el('market-chart-caption').textContent='未取得分时数据时不绘制曲线。';return;}
  if(window.MarketChart){
   if(!chartStates.has(selected))chartStates.set(selected,{});
   window.MarketChart.render(box,{period:'minute',data,compact:true,state:chartStates.get(selected),onInspect:text=>{el('market-chart-caption').textContent=(data.stale?'旧分时 · ':'')+text;}});
   return;
  }
  box.replaceChildren();
  const pts=data.points.filter(p=>validNumber(p.price)),prices=pts.map(p=>Number(p.price));
  if(!pts.length){box.textContent='暂无有效分时价格';return;}
  const minutes=t=>{const [h,m]=t.split(':').map(Number);return h*60+m;};
  const lo=Math.min(...prices),hi=Math.max(...prices),pad=Math.max((hi-lo)*.15,lo*.001,.01),low=lo-pad,high=hi+pad;
  const first=minutes(pts[0].time),last=minutes(pts.at(-1).time),x=t=>52+(minutes(t)-first)/Math.max(last-first,1)*630,y=p=>18+(high-p)/(high-low)*174;
  const chart=svg('svg',{viewBox:'0 0 700 225',role:'img','aria-label':name(selected)+' '+data.trade_date+' 真实分时走势'});
  for(let i=0;i<4;i++){const value=low+(high-low)*i/3,yy=y(value);chart.append(svg('line',{x1:52,x2:682,y1:yy,y2:yy,stroke:'#ffffff0c'}),svg('text',{x:45,y:yy+3,'text-anchor':'end',fill:'#a2a99f','font-size':10},num(value)));}
  let path='';pts.forEach((p,i)=>{const gap=i>0 && minutes(p.time)-minutes(pts[i-1].time)>5;path+=(i===0||gap?'M':'L')+x(p.time).toFixed(2)+' '+y(Number(p.price)).toFixed(2)+' ';});
  chart.append(svg('path',{d:path,fill:'none',stroke:'#d2ba85','stroke-width':1.8,'stroke-linejoin':'round'}));
  const end=pts.at(-1);chart.append(svg('circle',{cx:x(end.time),cy:y(Number(end.price)),r:3,fill:'#d2ba85'}));
  for(const i of [...new Set([0,Math.floor((pts.length-1)/2),pts.length-1])])chart.append(svg('text',{x:x(pts[i].time),y:218,'text-anchor':i===0?'start':i===pts.length-1?'end':'middle',fill:'#a2a99f','font-size':10},pts[i].time));
  box.append(chart);el('market-chart-caption').textContent=(data.stale?'分时更新失败 · 保留旧数据。 ':'')+'交易日期 '+data.trade_date+' · '+pts.length+' 个源记录 · 最后记录 '+end.time+' · 北京时间；缺口不插值。';
 }
 function schedule(delay=10000){clearTimeout(timer);if(current()&&el('market-auto').checked)timer=setTimeout(refresh,delay);}
 async function refresh(){
  if(!current())return;
  if(busy){queued=true;return;}
  clearTimeout(timer);busy=true;queued=false;el('market-refresh').disabled=true;
  const mine=revision,code=selected;controller=new AbortController();const signal=controller.signal;const timeout=setTimeout(()=>controller.abort(),20000);
  el('market-status').textContent='正在获取行情…';
  try{
   const codes=[...new Set([...indices.map(i=>i[0]),...stocks.keys()])];
   const results=await Promise.allSettled([request('/quotes?symbols='+encodeURIComponent(codes.join(',')),signal),request('/minutes/'+code,signal)]);
   if(mine!==revision||!current())return;
   const [snap,trend]=results;
   if(trend.status==='fulfilled')trends.set(code,trend.value);else {const previous=trends.get(code);trends.set(code,{...previous,stale:true,error:'分时请求失败，请稍后重试'});}
   if(snap.status==='rejected')throw snap.reason;
   const data=snap.value;
   if(!Array.isArray(data.quotes))throw Error('行情响应格式无效');
   for(const c of codes){const q=quotes.get(c);if(q)quotes.set(c,{...q,stale:true});}
   for(const q of data.quotes)quotes.set(q.code,q);
   const missing=data.unavailable || [];
   failures=data.stale?failures+1:0;
   const dates=[...new Set(data.quotes.map(q=>q.quote_time?.slice(0,10)).filter(Boolean))];
   const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
   const old=dates.some(d=>d!==today);
   el('market-status').textContent=data.stale?'连接异常 · 数据可能已过期':old?'最近交易日行情 · 非当日实时成交':'已连接 · 以源行情时间为准';
   const notices=[];if(data.error)notices.push(data.error);if(missing.length)notices.push('未取得行情：'+missing.join('、'));if(old)notices.push('当前返回 '+dates.join(' / ')+' 行情，请以源时间为准。');
   if(!old&&!data.stale){const age=data.quotes.some(q=>Date.now()-Date.parse(q.quote_time)>120000);if(age)notices.push('部分报价超过 2 分钟未更新，可能处于休市、停牌或源延迟状态。');}
   banner(notices.join(' '));el('market-fetched').textContent='来源 '+data.source+' · 检查时间 '+stamp(data.checked_at);
   render();draw();
  }catch(error){
   if(mine!==revision||!current())return;
   failures++;for(const [c,q] of quotes)quotes.set(c,{...q,stale:true});
   el('market-status').textContent='行情连接失败';banner(error.message+' 已有价格已标记为旧数据。');render();draw();
  }finally{
   clearTimeout(timeout);busy=false;controller=null;el('market-refresh').disabled=false;
   if(current()){if(queued||mine!==revision){queued=false;timer=setTimeout(refresh,0);}else schedule(Math.min(60000,10000*2**Math.min(failures,3)));}
  }
 }
 function choose(code){revision++;selected=code;render();draw();refresh();}
 async function loadWatchlist(){
  const version = ++watchlistVersion;
  const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),8000);
  try{
   const data=await request('/watchlist',abort.signal);if(version!==watchlistVersion)return;let rejected=0;
   if(!data.error){for(const code of databaseCodes)if(!manualCodes.has(code))stocks.delete(code);databaseCodes.clear();}
   for(const stock of data.stocks || []){try{const c=canonical(stock.symbol);if(!indices.some(i=>i[0]===c)&&(stocks.has(c)||stocks.size<30)){stocks.set(c,stock.name);databaseCodes.add(c);}}catch{rejected++;}}
   el('market-watchlist-note').textContent=data.error || '已读取数据库自选股'+(data.truncated?'（仅显示前 30 只）':'')+'。手动查询和移除仅影响当前行情表。'+(rejected?' 部分无效代码已跳过。':'');
   if(!stocks.has(selected)&&!indices.some(i=>i[0]===selected))selected='sh000001';render();draw();if(current())refresh();
  }catch(error){if(version===watchlistVersion)el('market-watchlist-note').textContent=error.message;}
  finally{clearTimeout(timeout);}
 }
 function setVisible(value){visible=value;revision++;clearTimeout(timer);controller?.abort();if(!value)window.marketDetail?.close();if(current()){if(!initialized){initialized=true;loadWatchlist();}refresh();}}
 document.addEventListener('visibilitychange',()=>setVisible(visible));
 el('market-auto').addEventListener('change',()=>{if(el('market-auto').checked)refresh();else clearTimeout(timer);});
 el('market-refresh').addEventListener('click',refresh);
 el('market-search').addEventListener('submit',event=>{event.preventDefault();try{const c=canonical(el('market-symbol').value);if(!stocks.has(c)&&!indices.some(i=>i[0]===c)&&stocks.size>=30)throw Error('当前最多关注 30 只证券，请先移除一只。');if(!indices.some(i=>i[0]===c)){stocks.set(c,c.slice(2)+'.'+c.slice(0,2).toUpperCase());manualCodes.add(c);}el('market-search-error').textContent='';el('market-symbol').value='';choose(c);}catch(error){el('market-search-error').textContent=error.message;}});
 window.marketDashboard={setVisible,reset(){setVisible(false);watchlistVersion++;initialized=false;quotes.clear();trends.clear();stocks.clear();databaseCodes.clear();manualCodes.clear();chartStates.clear();selected='sh000001';el('market-watchlist-note').textContent='';el('market-fetched').textContent='';el('market-status').textContent='请登录后查看';el('market-symbol').value='';el('market-search-error').textContent='';banner('');render();draw();},invalidateWatchlist(){watchlistVersion++;initialized=false;if(current()){initialized=true;loadWatchlist();}}};render();
})();
