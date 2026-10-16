(() => {
 'use strict';
 const $=id=>document.getElementById(id);
 let groups=[],members=[],selected=null,visible=false,saving=false,memberVersion=0,searchVersion=0,loadVersion=0,dialogAction=null;
 let memberLoadFailed=false, refreshError='', accountRevision=0;
 const node=(tag,cls,text)=>{const n=document.createElement(tag);n.className=cls||'';if(text!==undefined)n.textContent=text;return n;};
 function status(text,error=false){$('watch-status').textContent=text;$('watch-status').className='watch-status'+(error?' error':'');}
 async function request(path,method='GET',body){
  const mine=accountRevision,data=await window.apiClient.request(path,{method,body,timeout:12000,public:path.startsWith('/stocks/search?')});
  if(mine!==accountRevision)throw Object.assign(Error('账号已变化，已忽略旧响应。'),{name:'StaleResponseError'});return data;
 }
 function controls(){
  $('watch-rename').disabled=saving||selected===null;$('watch-delete').disabled=saving||selected===null;
  document.querySelectorAll('#watchlist-page button[type="submit"]').forEach(b=>b.disabled=saving);
 }
 function group(){return groups.find(g=>g.id===selected);}
 function renderGroups(){
  $('watch-groups').replaceChildren();
  for(const g of groups){const b=node('button','watch-group'+(g.id===selected?' active':''),g.name);b.type='button';b.setAttribute('aria-pressed',String(g.id===selected));b.addEventListener('click',()=>{if(saving)return;loadVersion++;selected=g.id;searchVersion++;$('watch-results').replaceChildren();renderGroups();loadMembers();});$('watch-groups').append(b);}
  $('watch-title').textContent=group()?.name || '选择或创建一个分组';controls();
 }
 function renderMembers(){
  $('watch-members').replaceChildren();$('watch-count').textContent=memberLoadFailed?'—':members.length+' 只股票';
  if(memberLoadFailed){$('watch-members').append(node('div','watch-empty','加载失败，点击“刷新列表”重试。'));return;}
  if(!members.length){$('watch-members').append(node('div','watch-empty',selected===null?'创建一个分组，开始整理你的自选股。':'当前分组暂无股票，搜索并添加第一只。'));return;}
  const sorted=window.SettingsRules?window.SettingsRules.sortStocks(members,window.settingsCenter?.preferences.watchlist_sort):members;
  for(const stock of sorted){const row=node('div','watch-stock'),title=node('button','watch-stock-title',stock.name);title.type='button';title.append(node('small','',stock.symbol+' · 点击开始研究'));title.addEventListener('click',()=>window.researchStock(stock));
   const actions=node('div','watch-stock-actions'),remove=node('button','btn','移除');remove.type='button';remove.disabled=saving;remove.addEventListener('click',()=>removeStock(stock));actions.append(remove);row.append(title,actions);$('watch-members').append(row);}
 }
 async function loadMembers(){
  const id=selected,version=++memberVersion;memberLoadFailed=false;members=[];renderMembers();if(id===null)return;
  $('watch-members').replaceChildren(node('div','watch-empty','正在加载组内股票…'));
  try{const data=await request('/watchlists/'+id+'/stocks');if(version!==memberVersion||selected!==id)return;members=data;renderMembers();}
  catch(error){if(version===memberVersion){memberLoadFailed=true;refreshError=error.message;$('watch-members').replaceChildren(node('div','watch-empty','加载失败，点击“刷新列表”重试。'));status(error.message,true);}}
 }
 async function loadGroups(preferred=selected){
  const version=++loadVersion;
  try{const data=await request('/watchlists');if(version!==loadVersion)return;groups=data;selected=groups.some(g=>g.id===preferred)?preferred:groups[0]?.id??null;renderGroups();await loadMembers();}
  catch(error){if(version===loadVersion){refreshError=error.message;status(error.message,true);}}
 }
 function changed(){window.marketDashboard?.invalidateWatchlist();}
 async function mutate(action,success){
  if(saving)return;const mine=accountRevision;saving=true;refreshError='';controls();renderMembers();
  try{await action();if(mine!==accountRevision)return false;changed();status(success+(refreshError?' 列表刷新失败，请点击“刷新列表”核对。':''),Boolean(refreshError));return true;}
  catch(error){if(mine===accountRevision)status(error.message,true);return false;}
  finally{if(mine===accountRevision){saving=false;controls();renderMembers();}}
 }
 $('watch-create').addEventListener('submit',async e=>{e.preventDefault();const name=$('watch-group-name').value.trim();if(!name){status('请输入分组名称。',true);return;}
  await mutate(async()=>{const g=await request('/watchlists','POST',{name});$('watch-group-name').value='';await loadGroups(g.id);},'分组已保存。');
 });
 function canonical(value){let s=value.trim().toLowerCase();if(/^\d{6}\.(sh|sz|bj)$/.test(s))s=s.slice(-2)+s.slice(0,6);if(/^\d{6}$/.test(s)){const prefix=s.startsWith('92')||/^[48]/.test(s)?'bj':/^6/.test(s)?'sh':/^[03]/.test(s)?'sz':null;if(!prefix)return null;s=prefix+s;}return /^(sh|sz|bj)\d{6}$/.test(s)?s:null;}
 function clearSearch(){searchVersion++;$('watch-results').replaceChildren();$('watch-search-note').textContent='';}
 $('watch-query').addEventListener('input',clearSearch);
 $('watch-search').addEventListener('submit',async e=>{
  e.preventDefault();const query=$('watch-query').value.trim();if(!query){clearSearch();return;}
  const version=++searchVersion;const code=canonical(query);$('watch-results').replaceChildren();$('watch-search-note').textContent='正在搜索…';
  try{
   const catalog=await request('/stocks/search?q='+encodeURIComponent(query));
   const results=(catalog.results||[]).map(({symbol,name})=>({symbol,name}));
   let note='搜索证券目录；添加时由服务端核对可信股票资料。目录可能不完整。';
   if(version!==searchVersion)return;
   $('watch-search-note').textContent=results.length?note:note+' 未找到结果；未入库股票请尝试完整代码。';
   for(const stock of results){const row=node('div','watch-stock watch-result'),info=node('div');info.append(node('span','',stock.name),node('p','',stock.symbol));const button=node('button','btn','添加到本组');button.type='button';button.disabled=selected===null||saving||members.some(s=>s.symbol===stock.symbol);if(members.some(s=>s.symbol===stock.symbol))button.textContent='已在本组';button.addEventListener('click',()=>addStock(stock,button));row.append(info,button);$('watch-results').append(row);}
  }catch(error){if(version===searchVersion){$('watch-search-note').textContent='搜索失败，可重新提交。';status(error.message,true);}}
 });
 async function addStock(stock,button){const id=selected;if(id===null||saving)return;button.disabled=true;const ok=await mutate(async()=>{await request('/watchlists/'+id+'/stocks','POST',stock);if(selected===id)await loadMembers();},stock.name+' 已加入分组。');button.disabled=ok;button.textContent=ok?'已在本组':'添加到本组';}
 async function removeStock(stock){const id=selected;await mutate(async()=>{await request('/watchlists/'+id+'/stocks/'+encodeURIComponent(stock.symbol),'DELETE');await loadMembers();searchVersion++;$('watch-results').replaceChildren();},stock.name+' 已从当前分组移除。');}
 function openDialog(mode){if(!group()||saving)return;dialogAction={mode,id:selected,name:group().name};$('watch-dialog-title').textContent=mode==='rename'?'重命名分组':'删除分组';$('watch-dialog-description').textContent=mode==='rename'?'为分组设置便于识别的名称。':'确认删除“'+group().name+'”？将清除该组关联，股票资料、日线及其他分组不受影响。';$('watch-rename-field').hidden=mode!=='rename';$('watch-rename-value').required=mode==='rename';$('watch-rename-value').value=group().name;$('watch-dialog-confirm').textContent=mode==='rename'?'保存名称':'确认删除';$('watch-dialog').showModal();}
 $('watch-rename').addEventListener('click',()=>openDialog('rename'));$('watch-delete').addEventListener('click',()=>openDialog('delete'));$('watch-dialog-cancel').addEventListener('click',()=>$('watch-dialog').close());
 $('watch-dialog-form').addEventListener('submit',async e=>{e.preventDefault();if(!dialogAction||saving)return;const {mode,id}=dialogAction,name=$('watch-rename-value').value.trim();if(mode==='rename'&&!name){$('watch-rename-value').focus();return;}$('watch-dialog').close();await mutate(async()=>{await request('/watchlists/'+id,mode==='rename'?'PATCH':'DELETE',mode==='rename'?{name}:undefined);searchVersion++;$('watch-results').replaceChildren();await loadGroups(mode==='rename'?id:null);},mode==='rename'?'分组名称已更新。':'分组已删除。');});
 $('watch-reload').addEventListener('click',()=>{if(!saving){status('');searchVersion++;$('watch-results').replaceChildren();loadGroups();}});
 window.watchlistManager={applyPreferences(){renderMembers();},reset(){accountRevision++;visible=false;loadVersion++;memberVersion++;searchVersion++;groups=[];members=[];selected=null;saving=false;dialogAction=null;$('watch-dialog').close();$('watch-group-name').value='';$('watch-query').value='';$('watch-results').replaceChildren();$('watch-search-note').textContent='';status('');renderGroups();renderMembers();},reload(){if(visible)loadGroups();},setVisible(value){visible=value;if(visible&&!saving){status('');loadGroups();}else if(!visible){searchVersion++;loadVersion++;memberVersion++;$('watch-dialog').close();}}};
 renderGroups();renderMembers();
})();
