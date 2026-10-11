(() => {
 'use strict';
 window.AuthRules={validPassword:value=>typeof value==='string'&&Array.from(value).length>=6&&Array.from(value).length<=15};
 if(typeof document==='undefined')return;
 const $=id=>document.getElementById(id),api=window.apiClient;
 let mode='login',busy=false,ready=null,previousUser=null;
 const titles={login:'登录研究工作台',register:'邀请码注册',forgot:'找回密码',reset:'设置新密码',verify:'验证邮箱',resend:'重发验证邮件'};
 function show(next='login'){
  mode=next;$('auth-title').textContent=titles[mode];$('auth-status').textContent='';
  for(const [field,modes] of Object.entries({email:['login','register','forgot','resend'],password:['login','register','reset'],invite:['register','verify'],token:['reset','verify']})){
   $('auth-'+field+'-row').hidden=!modes.includes(mode);$('auth-'+field).required=modes.includes(mode)&&!(field==='invite'&&mode==='verify');
  }
  $('auth-password').autocomplete=mode==='login'?'current-password':'new-password';
  $('auth-submit').textContent={login:'登录',register:'提交注册',forgot:'请求重置邮件',reset:'重置密码',verify:'验证邮箱',resend:'请求验证邮件'}[mode];
  $('auth-mail-note').textContent=api.session.mail_configured?'注册与找回请求受理后，仍需在邮箱中完成验证。':'真实邮件服务尚未配置，暂不能注册、重发或找回密码。已有已验证账号可以登录。';
  $('auth-submit').disabled=busy||(!api.session.mail_configured&&['register','forgot','resend'].includes(mode));
  $('auth-dialog').showModal();
 }
 function update(session){const changed=previousUser!==session.user?.id,lost=previousUser&&!session.user;previousUser=session.user?.id||null;$('account-email').textContent=session.user?.email||'未登录';$('account-button').textContent=session.user?'退出账号':'登录';$('model-mode').textContent={disabled:'模型调用已关闭',fake:'隔离测试模型',qwen:'Qwen 在线模型'}[session.model_mode]||'模型状态未知';if(changed||!session.user){$('app').hidden=true;window.dispatchEvent(new CustomEvent('private-session-cleared'));if(lost)show();} }
 api.subscribe(update);
 ready=api.bootstrap().then(session=>{update(session);return session;}).catch(error=>{$('auth-status').textContent=error.message;return null;});
 window.account={async requireLogin(){await ready;if(api.session.user)return true;show();return false;},show,ready};
 $('account-button').addEventListener('click',async()=>{if(busy)return;if(!api.session.user){show();return;}busy=true;try{await api.authenticate('logout');$('landing').hidden=false;show();}catch(error){$('auth-status').textContent=error.message;show();}finally{busy=false;}});
 $('auth-close').addEventListener('click',()=>$('auth-dialog').close());
 document.querySelectorAll('[data-auth-mode]').forEach(button=>button.addEventListener('click',()=>{if(!busy)show(button.dataset.authMode);}));
 $('auth-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;const submission=mode,password=$('auth-password').value;
  if(['register','reset'].includes(mode)&&!window.AuthRules.validPassword(password)){$('auth-status').textContent='密码必须为 6–15 个字符；不会自动裁剪或截断。';return;}
  busy=true;$('auth-submit').disabled=true;$('auth-status').textContent='正在提交…';
  const body={};if(['login','register','forgot','resend'].includes(mode))body.email=$('auth-email').value.trim();if(['login','register','reset'].includes(mode))body.password=password;
  if(['register','verify'].includes(mode)&&$('auth-invite').value.trim())body.invite_code=$('auth-invite').value.trim();if(['reset','verify'].includes(mode))body.token=$('auth-token').value.trim();
  try{
   await ready;if(!api.session.csrf_token)await api.bootstrap();
   if(mode==='login'){await api.authenticate('login',body);$('auth-password').value='';$('auth-dialog').close();window.dispatchEvent(new CustomEvent('account-login'));}
   else{const path={register:'register',forgot:'forgot-password',reset:'reset-password',verify:'verify-email',resend:'resend-verification'}[mode];const data=await api.request('/auth/'+path,{method:'POST',body});$('auth-password').value='';$('auth-status').textContent=data?.detail||'请求已受理；请检查邮箱并完成后续步骤。';if(['reset','verify'].includes(mode))await api.bootstrap();}
  }catch(error){$('auth-status').textContent=error.message;}
  finally{busy=false;if(mode===submission)$('auth-submit').disabled=!api.session.mail_configured&&['register','forgot','resend'].includes(mode);}
 });
 // Email links use a fragment so tokens are never sent in the page URL to the server.
 const fragment=new URLSearchParams(window.location.hash.slice(1)),query=new URLSearchParams(window.location.search);
 const token=fragment.get('verify')||fragment.get('reset')||fragment.get('token')||query.get('token'),action=fragment.has('verify')?'verify':fragment.has('reset')?'reset':fragment.get('action')||query.get('action');
 const linkedMode=action==='reset'||window.location.pathname.includes('reset-password')?'reset':action==='verify'||window.location.pathname.includes('verify-email')?'verify':null;
 if(token&&linkedMode){$('auth-token').value=token;window.history.replaceState(null,'',window.location.pathname);ready.then(()=>show(linkedMode));}
})();
