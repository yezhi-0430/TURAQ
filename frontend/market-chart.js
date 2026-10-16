/* Plot only records returned by the market service. */
(() => {
 'use strict';
 const good=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v));
 const fmt=v=>good(v)?Number(v).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
 const percent=v=>good(v)?(Number(v)>0?'+':'')+fmt(v)+'%':'—';
 const color=v=>Number(v)>=0?'#ec9a92':'#9cc6a5';
 const svg=(tag,attrs={},text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n;};
 // Moving averages for K periods, computed over the whole series so the visible window starts correct.
 const MA=[{n:5,color:'#e8e6e1'},{n:10,color:'#d46ad8'},{n:20,color:'#e3a73c'}],VOL_MA=MA.slice(0,2);
 const average=(rows,field,n)=>{let sum=0,ok=0;return rows.map((p,i)=>{const v=Number(p[field]),out=good(p[field]);sum+=out?v:0;ok+=out?1:0;
  if(i>=n){const q=rows[i-n];if(good(q[field])){sum-=Number(q[field]);ok-=1;}}return i>=n-1&&ok===n?sum/n:null;});};
 const lots=v=>!good(v)?'—':Math.abs(v)>=1e8?fmt(v/1e8)+'亿':Math.abs(v)>=1e4?fmt(v/1e4)+'万':fmt(v);
 const tradingMinute=t=>{const [h,m]=t.split(':').map(Number);const n=h*60+m;return n>=780?n-90:n;};
 // levels: [{price,label}] reference lines (e.g. cost), drawn only inside the visible range.
 // marks: [{date,time,side}] fills; K bars match the first bar dated on/after the fill.
 function render(host,{period='minute',data,state={},compact=false,levels=[],marks=[],onInspect=()=>{}}){
  const restoreFocus=host.children[0]&&document.activeElement===host.children[0];
  host.replaceChildren();
  const minute=period==='minute',all=(minute?data?.points:data?.bars)||[];
  const valid=all.filter(p=>good(minute?p.price:p.close));
  if(!valid.length){host.textContent=data?.error||'正在获取真实行情…';onInspect('暂无可用记录');return;}
  const count=Math.max(15,Math.min(valid.length,state.count||80));
  const start=minute?0:state.start===null||state.start===undefined?Math.max(0,valid.length-count):Math.max(0,Math.min(state.start,valid.length-count));
  const records=minute?valid:valid.slice(start,start+count);
  const priceMA=minute?[]:MA.map(m=>({...m,values:average(valid,'close',m.n).slice(start,start+count)}));
  const volumeMA=minute?[]:VOL_MA.map(m=>({...m,values:average(valid,'volume_lots',m.n).slice(start,start+count)}));
  const bounds=host.getBoundingClientRect();
  const width=Math.max(320,Math.round(bounds.width)||1000),height=Math.max(compact?180:260,Math.round(bounds.height)||460);
  const L=32,R=width-75,T=20,B=compact?height-38:Math.round(height*.64),VT=Math.round(height*.75),VB=compact?B:height-45;
  const getPrice=p=>Number(minute?p.price:p.close),key=p=>minute?p.time:p.date;
  const prices=records.flatMap(p=>minute?[Number(p.price),...(good(p.average_price)?[Number(p.average_price)]:[])]:[Number(p.high),Number(p.low)]);
  if(minute&&good(data.previous_close))prices.push(Number(data.previous_close));
  for(const m of priceMA)for(const v of m.values)if(v!==null)prices.push(v);
  const min=Math.min(...prices),max=Math.max(...prices),pad=Math.max((max-min)*.12,min*.001,.01),lo=min-pad,hi=max+pad;
  const y=p=>T+(hi-p)/(hi-lo)*(B-T);
  const first=minute?tradingMinute(records[0].time):0,last=minute?tradingMinute(records.at(-1).time):records.length-1;
  const x=(p,i)=>minute?L+(tradingMinute(p.time)-first)/Math.max(1,last-first)*(R-L):L+(i+.5)/records.length*(R-L);
  const chart=svg('svg',{viewBox:`0 0 ${width} ${height}`,preserveAspectRatio:'none',role:'img',tabindex:0,'aria-label':`真实${minute?'分时':'K线'}图；左右方向键查看数据`});
  const label=(xx,yy,text,anchor='start',fill='#a2a99f')=>svg('text',{x:xx,y:yy,'text-anchor':anchor,fill,'font-size':11},text);
  const priceLabels=[];
  for(let i=0;i<5;i++){
   const price=lo+(hi-lo)*i/4,yy=y(price);
   const text=label(R+8,yy+4,fmt(price));priceLabels.push({node:text,y:yy});
   chart.append(svg('line',{x1:L,x2:R,y1:yy,y2:yy,stroke:'#ffffff0b'}),text);
  }
  // Legend rows: text spans whose values follow the inspected bar.
  const legend=(xx,yy,kind,parts)=>{const node=svg('text',{x:xx,y:yy,'font-size':11,'data-kind':kind}),spans=parts.map(([text,fill])=>svg('tspan',{fill,dx:6},text));spans[0].setAttribute('dx',0);node.append(...spans);chart.append(node);return spans;};
  const maSpans=minute?[]:legend(L,T-7,'ma-legend',[[({day:'日线',week:'周线',month:'月线'})[period]||'K线','#a2a99f'],...priceMA.map(m=>['',m.color])]);
  if(!compact)chart.append(svg('line',{x1:L,x2:R,y1:VT-15,y2:VT-15,stroke:'#ffffff18'}));
  const volSpans=compact?[]:minute?(chart.append(label(L,VT-22,'成交量（手）')),[]):legend(L,VT-22,'vol-ma',[['成交量','#a2a99f'],['','#a2a99f'],...volumeMA.map(m=>['',m.color])]);
  if(minute&&good(data.previous_close))chart.append(svg('line',{x1:L,x2:R,y1:y(Number(data.previous_close)),y2:y(Number(data.previous_close)),stroke:'#a2a99f66','stroke-dasharray':'4 4'}));
  const pathFor=field=>{
   let d='',previous=null;
   records.forEach((p,i)=>{if(!good(p[field])){previous=null;return;}const gap=previous===null||tradingMinute(p.time)-tradingMinute(previous.time)>5;d+=(gap?'M':'L')+x(p,i).toFixed(2)+' '+y(Number(p[field])).toFixed(2)+' ';previous=p;});
   return d;
  };
  if(minute){
   chart.append(svg('path',{d:pathFor('price'),fill:'none',stroke:'#e9ece5','stroke-width':1.6,'data-kind':'price-line'}));
   if(records.some(p=>good(p.average_price)))chart.append(svg('path',{d:pathFor('average_price'),fill:'none',stroke:'#d2ba85','stroke-width':1.6,'data-kind':'average-line'}));
  }else{
   const barWidth=Math.max(1,Math.min(12,(R-L)/records.length*.65));
   records.forEach((p,i)=>{const xx=x(p,i),op=Number(p.open),cl=Number(p.close),c=color(cl-op);
    chart.append(svg('line',{x1:xx,x2:xx,y1:y(Number(p.high)),y2:y(Number(p.low)),stroke:c}),svg('rect',{x:xx-barWidth/2,y:Math.min(y(op),y(cl)),width:barWidth,height:Math.max(1,Math.abs(y(op)-y(cl))),fill:c,'data-kind':'candle'}));
   });
  }
  const linePath=(values,yOf)=>{let d='',open=false;values.forEach((v,i)=>{if(v===null){open=false;return;}d+=(open?'L':'M')+x(records[i],i).toFixed(2)+' '+yOf(v).toFixed(2)+' ';open=true;});return d;};
  for(const m of priceMA){const d=linePath(m.values,y);if(d)chart.append(svg('path',{d,fill:'none',stroke:m.color,'stroke-width':1.2,'data-kind':'ma','data-n':m.n}));}
  for(const level of levels){
   if(!good(level.price))continue;const v=Number(level.price);if(v<lo||v>hi)continue;const yy=y(v);
   chart.append(svg('line',{x1:L,x2:R,y1:yy,y2:yy,stroke:'#d2ba85',opacity:.7,'stroke-dasharray':'6 4','data-kind':'level'}),label(L+4,yy-5,(level.label||'')+' '+fmt(v),'start','#d2ba85'));
  }
  const placed=new Set();
  for(const m of marks){
   let index=-1;
   if(minute){if(m.date!==data.trade_date||!m.time)continue;index=valid.findIndex(p=>p.time>=m.time);}
   else index=valid.findIndex(p=>p.date>=m.date);
   index-=start;if(index<0||index>=records.length||placed.has(index+':'+m.side))continue;placed.add(index+':'+m.side);
   const p=records[index],xx=x(p,index),buy=m.side==='buy';
   const yy=minute?y(getPrice(p))+(buy?16:-8):buy?y(Number(p.low))+14:y(Number(p.high))-6;
   chart.append(svg('text',{x:xx,y:Math.max(T+8,Math.min(B-2,yy)),'text-anchor':'middle',fill:buy?'#ec9a92':'#9cc6a5','font-size':11,'font-weight':600,'data-kind':'trade-mark'},buy?'B':'S'));
  }
  const volumes=records.filter(p=>good(p.volume_lots)),maxVolume=Math.max(1,...volumes.map(p=>Number(p.volume_lots)),...volumeMA.flatMap(m=>m.values.filter(v=>v!==null)));
  const volWidth=Math.max(1,Math.min(12,(R-L)/Math.max(1,records.length)*.65));
  if(!compact)records.forEach((p,i)=>{if(!good(p.volume_lots))return;const v=Number(p.volume_lots),h=v/maxVolume*(VB-VT),delta=minute?getPrice(p)-(i?getPrice(records[i-1]):Number(data.previous_close||p.price)):Number(p.close)-Number(p.open);
   chart.append(svg('rect',{x:x(p,i)-volWidth/2,y:VB-h,width:volWidth,height:h,fill:color(delta),opacity:.75,'data-kind':'volume-bar'}));
  });
  if(!compact)for(const m of volumeMA){const d=linePath(m.values,v=>VB-v/maxVolume*(VB-VT));if(d)chart.append(svg('path',{d,fill:'none',stroke:m.color,'stroke-width':1.1,'data-kind':'vol-ma-line','data-n':m.n}));}
  if(!compact&&!volumes.length)chart.append(label(L,VT+30,'源数据暂无成交量'));
  const ticks=[...new Set([0,Math.floor((records.length-1)/2),records.length-1])];
  const timeLabels=[];
  for(const i of ticks){const text=label(x(records[i],i),height-(compact?12:23),key(records[i]),i===0?'start':i===records.length-1?'end':'middle');timeLabels.push({node:text,x:x(records[i],i)});chart.append(text);}
  const cross=svg('g',{'data-kind':'crosshair',visibility:'hidden','pointer-events':'none'});
  const vertical=svg('line',{y1:T,y2:VB,stroke:'#d2ba85','stroke-dasharray':'4 3'}),horizontal=svg('line',{x1:L,x2:R,stroke:'#d2ba85','stroke-dasharray':'4 3'});
  const dot=svg('circle',{r:3,fill:'#d2ba85'}),priceBox=svg('rect',{x:R+2,width:71,height:22,rx:3,fill:'#d2ba85'}),priceText=label(R+5,0,'','start','#171a18');
  const timeBox=svg('rect',{y:height-(compact?28:39),width:minute?58:86,height:23,rx:3,fill:'#d2ba85'}),timeText=label(0,height-(compact?12:23),'','middle','#171a18');
  cross.append(vertical,horizontal,dot,priceBox,priceText,timeBox,timeText);chart.append(cross);host.append(chart);if(restoreFocus)chart.focus({preventScroll:true});
  function describe(p){
   return minute?`${data.trade_date} ${p.time}　价格 ${fmt(p.price)}　涨跌幅 ${percent(p.change_percent)}　均价 ${fmt(p.average_price)}　区间量 ${fmt(p.volume_lots)} 手`:
    `${({none:'不复权',qfq:'前复权',hfq:'后复权'})[data.adjustment||'none']} · ${p.date}　开 ${fmt(p.open)}　高 ${fmt(p.high)}　低 ${fmt(p.low)}　收 ${fmt(p.close)}　涨跌幅 ${percent(p.change_percent)}　量 ${fmt(p.volume_lots)} 手`;
  }
  function inspect(i,show=true){
   i=Math.max(0,Math.min(records.length-1,i));const p=records[i],xx=x(p,i),yy=y(getPrice(p));
   state.time=key(p);state.hover=show;cross.setAttribute('visibility',show?'visible':'hidden');
   for(const n of [vertical]){n.setAttribute('x1',xx);n.setAttribute('x2',xx);}
   horizontal.setAttribute('y1',yy);horizontal.setAttribute('y2',yy);dot.setAttribute('cx',xx);dot.setAttribute('cy',yy);
   priceBox.setAttribute('y',yy-11);priceText.setAttribute('y',yy+4);priceText.textContent=fmt(getPrice(p));
   const tw=minute?58:86,tx=Math.max(L,Math.min(R-tw,xx-tw/2));timeBox.setAttribute('x',tx);timeText.setAttribute('x',tx+tw/2);timeText.textContent=key(p);
   for(const item of timeLabels)item.node.setAttribute('visibility',show&&Math.abs(item.x-(tx+tw/2))<tw?'hidden':'visible');
   for(const item of priceLabels)item.node.setAttribute('visibility',show&&Math.abs(item.y-yy)<18?'hidden':'visible');
   legendAt(i);onInspect(describe(p));
  }
  function legendAt(i){
   priceMA.forEach((m,k)=>{maSpans[k+1].textContent=`${k?'':'MA'}${m.n}:${fmt(m.values[i])}`;});
   if(!volSpans.length)return;volSpans[1].textContent=`量:${lots(Number(records[i].volume_lots))}`;
   volumeMA.forEach((m,k)=>{volSpans[k+2].textContent=`${k?'':'MA'}${m.n}:${lots(m.values[i])}`;});
  }
  chart.addEventListener('pointermove',event=>{
   const rect=chart.getBoundingClientRect(),px=(event.clientX-rect.left)/rect.width*width;
   let nearest=0;for(let i=1;i<records.length;i++)if(Math.abs(x(records[i],i)-px)<Math.abs(x(records[nearest],nearest)-px))nearest=i;
   inspect(nearest);
  });
  chart.addEventListener('pointerleave',()=>{state.hover=false;legendAt(records.length-1);cross.setAttribute('visibility','hidden');for(const item of [...priceLabels,...timeLabels])item.node.setAttribute('visibility','visible');onInspect(describe(records.at(-1)));});
  chart.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();const i=records.findIndex(p=>key(p)===state.time);inspect((i<0?records.length-1:i)+(event.key==='ArrowLeft'?-1:1));});
  const active=records.findIndex(p=>key(p)===state.time);inspect(active>=0&&state.hover?active:records.length-1,Boolean(active>=0&&state.hover));
 }
 window.MarketChart={render};
})();
