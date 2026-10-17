/* Administrative data uses the same authenticated, CSRF-protected API client. */
(() => {
 'use strict';
 const $=id=>document.getElementById(id),api=window.apiClient;
 let visible=null,epoch=0,reader=null,pending=null,writing=false,denied=false,lastUser=null;
 let userOffset=0,inviteOffset=0,userTotal=0,inviteTotal=0,writeSerial=0;
 const size=20,navIds=['admin-label','admin-dashboard-nav','admin-users-nav','admin-invites-nav'];
 const allowed=()=>api.session.user?.is_admin===true&&!denied;
 const node=(tag,value='',className='')=>{const el=document.createElement(tag);el.textContent=String(value??'');el.className=className;return el;};
 const stamp=value=>value&&Number.isFinite(Date.parse(value))?new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'未记录';
 const status=(message,error=false)=>{$('admin-status').textContent=message;$('admin-status').className='admin-status'+(error?' error':'');};
 const clearCode=()=>{$('admin-new-code').textContent='';$('admin-code-box').hidden=true;};
 function reset(){epoch++;writeSerial++;reader?.abort();reader=null;visible=null;pending=null;writing=false;userOffset=inviteOffset=0;userTotal=inviteTotal=0;clearCode();$('admin-confirm-dialog').close();$('admin-confirm-description').textContent='';$('admin-users-body').replaceChildren();$('admin-invites-body').replaceChildren();$('admin-overview').replaceChildren();$('admin-usage').replaceChildren();$('admin-user-query').value='';$('admin-user-filter').value='';status('');$('admin-as-of').textContent='';$('admin-user-page-note').textContent='';$('admin-invite-page-note').textContent='';$('admin-create-button').disabled=false;$('admin-page').hidden=true;}
 function update(session){const id=session.user?.id??null;if(id!==lastUser){reset();denied=false;lastUser=id;}if(!session.user?.is_admin)reset();navIds.forEach(id=>$(id).hidden=!allowed());}
 function handleError(error){if(error.name==='StaleResponseError')return;if(error.status===403){denied=true;reset();navIds.forEach(id=>$(id).hidden=true);window.selectWorkspacePage?.('agent');return;}status(error.unknownOutcome?'结果待确认：连接中断，操作可能已完成。请先刷新列表核对，不要重复提交。':error.message||'管理数据加载失败。',true);}
 function tableRows(target,rows,makeRow,empty,columns){target.replaceChildren();if(!rows.length){const tr=node('tr'),td=node('td',empty,'admin-empty');td.colSpan=columns;tr.append(td);target.append(tr);return;}rows.forEach(row=>target.append(makeRow(row)));}
 function cells(values){const tr=node('tr');values.forEach(value=>tr.append(node('td',value)));return tr;}
 function requestConfirmation(label,path,method,body){if(!allowed()||writing||!visible)return;pending={path,method,body};$('admin-confirm-description').textContent=label;$('admin-confirm-button').disabled=false;$('admin-confirm-dialog').showModal();}
 function userRow(user){const tr=cells([user.id,user.email,user.disabled?'已禁用':user.verified?'正常':'待验证',user.is_admin?'管理员':'用户',stamp(user.created_at),stamp(user.last_seen)]),td=node('td');
  if(user.is_admin)td.append(node('span','管理员保护','muted'));else{const button=node('button',user.disabled?'启用':'禁用','btn admin-small');button.type='button';button.addEventListener('click',()=>requestConfirmation((user.disabled?'启用':'禁用')+'账号 '+user.email+'（ID '+user.id+'）。'+(user.disabled?'旧登录会话不会恢复，用户需重新登录。':'该账号所有登录会话将被撤销。'),'/admin/users/'+user.id,'PATCH',{disabled:!user.disabled}));td.append(button);}tr.append(td);return tr;
 }
 const inviteState={active:'有效',revoked:'已撤销',expired:'已过期',exhausted:'已用完'};
 function inviteRow(invite){const tr=cells(['#'+invite.id,invite.used_count+' / '+invite.max_uses,stamp(invite.expires_at),inviteState[invite.status]||'未知']),td=node('td');if(!invite.revoked){const button=node('button','撤销','btn admin-small');button.type='button';button.addEventListener('click',()=>requestConfirmation('撤销邀请码 #'+invite.id+'。未使用名额将失效，已激活账号保留。','/admin/invites/'+invite.id,'DELETE',{}));td.append(button);}else td.append(node('span','—','muted'));tr.append(td);return tr;}
 function pager(kind,offset,total){$(kind+'-page-note').textContent=total?'共 '+total+' 条 · '+(offset+1)+'–'+Math.min(offset+size,total):'暂无记录';$(kind+'-previous').disabled=offset===0;$(kind+'-next').disabled=offset+size>=total;}
 function renderOverview(data,usage){const grid=$('admin-overview');grid.replaceChildren();[
  ['总用户数',data.total_users],['近7日会话活动用户',data.active_users_7d],['近24小时研究请求',data.research_requests_24h],['可用邀请名额',data.available_slots],['近24小时模型 HTTP 尝试',data.model_http_attempts_24h],['今日工具调用尝试',data.tool_attempts_today],['模型 Token','未记录'],['实际费用','未记录']
 ].forEach(([label,value])=>{const card=node('div','','admin-stat');card.append(node('div',label,'muted'),node('strong',value??'未记录'));grid.append(card);});
 const area=$('admin-usage');area.replaceChildren();const appendTable=(title,headers,rows)=>{const section=node('section','','admin-card');section.append(node('h2',title));const wrap=node('div','','admin-table-wrap'),table=node('table','','admin-table'),head=node('thead'),tr=node('tr'),body=node('tbody');headers.forEach(h=>tr.append(node('th',h)));head.append(tr);tableRows(body,rows,row=>cells(row),'暂无记录',headers.length);table.append(head,body);wrap.append(table);section.append(wrap);area.append(section);};
 appendTable('近7日工具使用排行（前20名）',['用户','工具尝试','工具成功率'],usage.by_user.map(u=>[u.email,u.calls,(u.success_rate*100).toFixed(1)+'%']));
 appendTable('近7日工具统计',['工具','调用尝试','成功率'],usage.by_tool.map(t=>[t.tool_name,t.usage,(t.success_rate*100).toFixed(1)+'%']));
 appendTable('工具调用趋势（上海日期）',['日期','调用尝试'],usage.daily_trend.map(d=>[d.date,d.calls]));
 $('admin-as-of').textContent='统计时间：'+stamp(data.as_of)+' · Asia/Shanghai';
 }
 async function load(){if(!allowed()||!visible)return;const page=visible,mine=++epoch;reader?.abort();reader=new AbortController();const opts={signal:reader.signal};status('正在加载…');
  try{if(page==='admin-dashboard'){const [data,usage]=await Promise.all([api.request('/admin/stats/overview',opts),api.request('/admin/stats/llm-usage',opts)]);if(mine!==epoch||!allowed())return;renderOverview(data,usage);}
   if(page==='admin-users'){const q=$('admin-user-query').value.trim(),filter=$('admin-user-filter').value;const query=new URLSearchParams({limit:String(size),offset:String(userOffset),q});if(filter)query.set('disabled',filter);const data=await api.request('/admin/users?'+query,opts);if(mine!==epoch||!allowed())return;userTotal=data.total;tableRows($('admin-users-body'),data.users,userRow,'没有符合条件的用户',7);pager('admin-user',userOffset,userTotal);}
   if(page==='admin-invites'){const data=await api.request('/admin/invites?limit='+size+'&offset='+inviteOffset,opts);if(mine!==epoch||!allowed())return;inviteTotal=data.total;tableRows($('admin-invites-body'),data.invites,inviteRow,'尚未生成邀请码',5);pager('admin-invite',inviteOffset,inviteTotal);}
   if(mine===epoch){status('');return true;}
  }catch(error){if(mine===epoch&&error.name!=='AbortError')handleError(error);}
 }
 async function setVisible(page){if(!page){epoch++;reader?.abort();visible=null;clearCode();pending=null;$('admin-confirm-dialog').close();return;}if(!allowed())return false;if(visible!==page){clearCode();pending=null;$('admin-confirm-dialog').close();}visible=page;['dashboard','users','invites'].forEach(tab=>$('admin-tab-'+tab).hidden=page!=='admin-'+tab);return load();}
 async function write(path,method,body){if(writing||!allowed()||!visible)return;writing=true;const mine=epoch,page=visible,operation=++writeSerial;const current=()=>operation===writeSerial&&allowed()&&page===visible;$('admin-create-button').disabled=true;$('admin-confirm-button').disabled=true;status('正在保存…');
  try{const result=await api.request(path,{method,body});if(mine!==epoch||!current())return;if(method==='POST'){clearCode();$('admin-new-code').textContent=result.code;$('admin-code-box').hidden=false;}const refreshed=await load();if(current())status(refreshed===true?(method==='POST'?'邀请码已生成，请立即保存；原码仅展示这一次。':'后端已确认操作成功。'):(method==='POST'?'邀请码已生成，原码仅展示一次；列表刷新失败，请刷新核对。':'操作已成功，但列表刷新失败；请刷新核对。'),refreshed!==true);
  }catch(error){if(mine===epoch&&page===visible)handleError(error);}
  finally{if(operation===writeSerial){if(allowed()){$('admin-create-button').disabled=false;$('admin-confirm-button').disabled=false;}writing=false;}}
 }
 $('admin-refresh').addEventListener('click',()=>{if(!writing)load();});
 $('admin-user-search').addEventListener('submit',event=>{event.preventDefault();if(writing)return;userOffset=0;load();});
 ['user','invite'].forEach(kind=>['previous','next'].forEach(direction=>$("admin-"+kind+'-'+direction).addEventListener('click',()=>{if(writing)return;const delta=direction==='next'?size:-size;if(kind==='user')userOffset=Math.max(0,userOffset+delta);else inviteOffset=Math.max(0,inviteOffset+delta);load();})));
 $('admin-create-invite').addEventListener('submit',async event=>{event.preventDefault();if(writing||!allowed())return;const uses=Number($('admin-invite-uses').value),days=Number($('admin-invite-days').value);if(!Number.isInteger(uses)||uses<1||uses>10000||!Number.isInteger(days)||days<1||days>3650){status('名额须为 1–10000 的整数，有效天数须为 1–3650 的整数。',true);return;}clearCode();await write('/admin/invites','POST',{max_uses:uses,days});});
 $('admin-confirm-cancel').addEventListener('click',()=>{pending=null;$('admin-confirm-dialog').close();});
 $('admin-confirm-dialog').addEventListener('cancel',()=>{pending=null;});
 $('admin-confirm-button').addEventListener('click',async()=>{const action=pending;if(!action||writing)return;pending=null;$('admin-confirm-dialog').close();await write(action.path,action.method,action.body);});
 window.adminPanel={allowed,reset,setVisible};api.subscribe(update);update(api.session);
})();
