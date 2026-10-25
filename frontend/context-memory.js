/* Explicit account memory. No conversations, credentials or preferences in browser storage. */
(() => {
 'use strict';
 const api=window.apiClient;
 let host=null,controls=null,generation=0,visible=false,loadedUser=null,busy=false;
 const node=(tag,text='')=>{const el=document.createElement(tag);el.textContent=text;return el;};
 function reset(){
  generation++;loadedUser=null;busy=false;
  if(controls){controls.detail.value='concise';controls.pages.checked=true;controls.units.checked=true;controls.status.textContent='未保存研究偏好。';enabled(false);}
 }
 function enabled(ready){for(const el of [controls.detail,controls.pages,controls.units,controls.save,controls.clear])el.disabled=!ready||busy;controls.refresh.disabled=busy;}
 function render(){
  const card=node('section');card.className='settings-card';
  card.append(node('h3','长期研究偏好'),node('p','主动保存后用于下次研究。只保存以下选项，不读取聊天历史，也不改变财报评分。'));
  const form=node('form'),detail=node('select'),pages=node('input'),units=node('input');
  for(const [value,label] of [['concise','简洁回答'],['detailed','适当展开']]){const option=node('option',label);option.value=value;detail.append(option);}
  detail.value='concise';pages.type='checkbox';units.type='checkbox';pages.checked=true;units.checked=true;
  for(const [label,input] of [['回答详细程度',detail],['引用已核实的财报页序',pages],['关注原表单位和报告期',units]]){const row=node('label',label);row.className='settings-field';row.append(input);form.append(row);}
  const actions=node('div');actions.className='settings-footer-actions';
  const save=node('button','保存研究偏好'),refresh=node('button','刷新'),clear=node('button','清除偏好');
  save.type='submit';refresh.type=clear.type='button';for(const button of [save,refresh,clear])button.className='btn';save.className='btn primary';
  actions.append(save,refresh,clear);form.append(actions);
  const status=node('p');status.className='settings-help';status.setAttribute('role','status');card.append(form,status);host.replaceChildren(card);
  controls={detail,pages,units,save,refresh,clear,status};
  form.addEventListener('submit',event=>{event.preventDefault();return write('PUT');});
  clear.addEventListener('click',()=>write('DELETE'));refresh.addEventListener('click',()=>load());reset();
 }
 function apply(data){
  const ready=data.state==='ready',pref=data.preferences;
  controls.detail.value=pref?.answer_detail==='detailed'?'detailed':'concise';
  controls.pages.checked=pref?.include_page_refs!==false;controls.units.checked=pref?.check_original_units!==false;
  controls.status.textContent=!ready?(data.state==='disabled'?'长期偏好尚未启用，研究功能仍可使用。':'长期偏好服务暂不可用，研究功能仍可使用。'):(pref?'研究偏好已保存，下次研究时生效。':'未保存研究偏好。');
  enabled(ready);
 }
 async function load(){
  if(!api.session.user||busy)return;const mine=++generation,user=api.session.user.id;busy=true;enabled(false);controls.status.textContent='正在读取研究偏好…';
  try{const data=await api.request('/context/preferences');if(mine!==generation||api.session.user?.id!==user)return;loadedUser=user;busy=false;apply(data);}
  catch{if(mine===generation){busy=false;apply({state:'unavailable'});}}
 }
 async function write(method){
  if(busy||!api.session.user||controls.save.disabled)return;const mine=++generation,user=api.session.user.id;busy=true;enabled(false);
  const body=method==='PUT'?{answer_detail:controls.detail.value,include_page_refs:controls.pages.checked,check_original_units:controls.units.checked}:{};
  try{const data=await api.request('/context/preferences',{method,body});if(mine!==generation||api.session.user?.id!==user)return;busy=false;apply(data);}
  catch{if(mine===generation){busy=false;enabled(true);controls.status.textContent='操作未确认，请先刷新核对后再重试。';}}
 }
 api.subscribe(session=>{if(loadedUser!==session.user?.id)reset();});
 window.addEventListener('private-session-cleared',reset);
 window.contextMemory={async show(next,target){visible=Boolean(next);if(!target)return;if(host!==target){host=target;render();}host.hidden=!visible;if(visible&&api.session.user&&loadedUser!==api.session.user.id)await load();}};
})();
