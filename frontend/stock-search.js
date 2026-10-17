/* Public catalog lookup; provider strings are always text nodes. */
(() => {
 'use strict';
 let timer=null,controller=null,revision=0,currentQuery='';
 const input=document.getElementById('stock-search-input'),button=document.getElementById('stock-search-btn'),results=document.getElementById('stock-search-results');
 if(!input||!results)return;
 function node(tag,cls,text){const n=document.createElement(tag);n.className=cls;n.textContent=text;return n;}
 function hide(){revision++;clearTimeout(timer);controller?.abort();controller=null;currentQuery='';results.hidden=true;results.replaceChildren();}
 function message(text){results.replaceChildren(node('div','stock-search-empty',text));results.hidden=false;}
 function select(stock){hide();input.value='';if(!document.getElementById('dashboard-page').hidden)window.marketDetail?.open(stock.code,stock.name);else if(!document.getElementById('watchlist-page').hidden){document.getElementById('watch-query').value=stock.symbol;document.getElementById('watch-search').requestSubmit();}else{document.getElementById('input-box').value='查询 '+stock.symbol+' 的股票资料';document.getElementById('input-box').focus();}}
 async function search(query){
  query=query.trim();hide();if(!query)return;currentQuery=query;const mine=revision;controller=new AbortController();message('正在搜索…');
  try{const data=await window.apiClient.request('/stocks/search?q='+encodeURIComponent(query)+'&limit=30',{signal:controller.signal,public:true});if(mine!==revision||currentQuery!==query)return;
   results.replaceChildren();for(const stock of data.results||[]){const row=node('button','stock-search-item','');row.type='button';row.setAttribute('aria-label','选择 '+stock.name+' '+stock.symbol);const info=node('div','','');info.append(node('span','stock-search-item-name',stock.name),node('span','stock-search-item-code',stock.symbol));row.append(info,node('span','stock-search-item-market',stock.market));row.addEventListener('click',()=>select(stock));results.append(row);}if(!results.children.length)message('未找到匹配的股票；目录可能不完整。');else results.hidden=false;
  }catch(error){if(mine!==revision||error.name==='AbortError'||error.name==='StaleResponseError')return;message(error.message);}
 }
 input.addEventListener('input',()=>{hide();const query=input.value.trim();if(query)timer=setTimeout(()=>search(query),300);});
 button?.addEventListener('click',()=>search(input.value));
 input.addEventListener('keydown',e=>{if(e.key==='Escape')hide();if(e.key==='Enter'){e.preventDefault();search(input.value);}});
 document.addEventListener('click',e=>{if(!input.contains(e.target)&&!results.contains(e.target)&&!button?.contains(e.target))hide();});
 window.addEventListener('private-session-cleared',()=>{hide();input.value='';});
 window.StockSearch={search,hide};
})();
