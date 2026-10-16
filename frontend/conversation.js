/* Keep recent dialogue inside the API limits; no persisted private state. */
(() => {
 'use strict';
 function buildHistory(messages){
  const marker='\n[…原回答中间部分省略…]\n';
  const history=messages.filter(m=>!m.error&&['user','assistant'].includes(m.role)&&typeof m.content==='string'&&m.content.trim()).map(({role,content})=>{
   if(content.length>4000){
    if(role==='user')throw new Error('问题最多 4,000 字，请精简后再发送。');
    content=content.slice(0,2800)+marker+content.slice(-(4000-2800-marker.length));
   }
   return {role,content};
  });
  let size=history.reduce((n,m)=>n+m.content.length,0);
  while(history.length>1&&(history.length>20||size>20000))size-=history.shift().content.length;
  while(history.length>1&&history[0].role!=='user')history.shift();
  return history;
 }
 window.ResearchConversation={buildHistory};
})();
