/* Plot only records returned by the market service. */
(() => {
 'use strict';
 const good=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v));
 const fmt=v=>good(v)?Number(v).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
 const percent=v=>good(v)?(Number(v)>0?'+':'')+fmt(v)+'%':'—';
 const color=v=>Number(v)>=0?'#ec9a92':'#9cc6a5';
 const svg=(tag,attrs={},text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n;};
 const tradingMinute=t=>{const [h,m]=t.split(':').map(Number);const n=h*60+m;return n>=780?n-90:n;};
 function render(host,{period='minute',data,state={},compact=false,onInspect=()=>{}}){
  const restoreFocus=host.children[0]&&document.activeElement===host.children[0];
  host.replaceChildren();
  const minute=period==='minute',all=(minute?data?.points:data?.bars)||[];
  const valid=all.filter(p=>good(minute?p.price:p.close));
  if(!valid.length){host.textContent=data?.error||'正在获取真实行情…';onInspect('暂无可用记录');return;}
  const count=Math.max(15,Math.min(valid.length,state.count||80));
  const start=minute?0:state.start===null||state.start===undefined?Math.max(0,valid.length-count):Math.max(0,Math.min(state.start,valid.length-count));
  const records=minute?valid:valid.slice(start,start+count);
  const bounds=host.getBoundingClientRect();
  const width=Math.max(320,Math.round(bounds.width)||1000),height=Math.max(compact?180:260,Math.round(bounds.height)||460);
  const L=32,R=width-75,T=20,B=compact?height-38:Math.round(height*.64),VT=Math.round(height*.75),VB=compact?B:height-45;
  const getPrice=p=>Number(minute?p.price:p.close),key=p=>minute?p.time:p.date;
  const prices=records.flatMap(p=>minute?[Number(p.price),...(good(p.average_price)?[Number(p.average_price)]:[])]:[Number(p.high),Number(p.low)]);
  if(minute&&good(data.previous_close))prices.push(Number(data.previous_close));
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
  if(!compact)chart.append(svg('line',{x1:L,x2:R,y1:VT-15,y2:VT-15,stroke:'#ffffff18'}),label(L,VT-22,'成交量（手）'));
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
  const volumes=records.filter(p=>good(p.volume_lots)),maxVolume=Math.max(1,...volumes.map(p=>Number(p.volume_lots)));
  const volWidth=Math.max(1,Math.min(12,(R-L)/Math.max(1,records.length)*.65));
  if(!compact)records.forEach((p,i)=>{if(!good(p.volume_lots))return;const v=Number(p.volume_lots),h=v/maxVolume*(VB-VT),delta=minute?getPrice(p)-(i?getPrice(records[i-1]):Number(data.previous_close||p.price)):Number(p.close)-Number(p.open);
   chart.append(svg('rect',{x:x(p,i)-volWidth/2,y:VB-h,width:volWidth,height:h,fill:color(delta),opacity:.75,'data-kind':'volume-bar'}));
  });
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
   onInspect(describe(p));
  }
  chart.addEventListener('pointermove',event=>{
   const rect=chart.getBoundingClientRect(),px=(event.clientX-rect.left)/rect.width*width;
   let nearest=0;for(let i=1;i<records.length;i++)if(Math.abs(x(records[i],i)-px)<Math.abs(x(records[nearest],nearest)-px))nearest=i;
   inspect(nearest);
  });
  chart.addEventListener('pointerleave',()=>{state.hover=false;cross.setAttribute('visibility','hidden');for(const item of [...priceLabels,...timeLabels])item.node.setAttribute('visibility','visible');onInspect(describe(records.at(-1)));});
  chart.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();const i=records.findIndex(p=>key(p)===state.time);inspect((i<0?records.length-1:i)+(event.key==='ArrowLeft'?-1:1));});
  const active=records.findIndex(p=>key(p)===state.time);inspect(active>=0&&state.hover?active:records.length-1,Boolean(active>=0&&state.hover));
 }
 window.MarketChart={render};
})();
