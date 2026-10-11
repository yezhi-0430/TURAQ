/* All HTTP traffic uses the browser origin; sessions stay in HttpOnly cookies. */
(() => {
 'use strict';
 function createAPIClient(fetcher = (...args) => fetch(...args)) {
  let session = {user:null,csrf_token:null,mail_configured:false,model_mode:'disabled'}, revision = 0;
  const listeners = new Set(), controllers = new Set();
  const stale = () => Object.assign(new Error('账号已变化，已忽略旧响应。'),{name:'StaleResponseError'});
  function change(next) {
   revision++; for(const controller of controllers)controller.abort(); controllers.clear();
   session = next; for(const listener of listeners)listener(session);
  }
  async function request(path, options = {}) {
   if(typeof path !== 'string' || !/^\/(?!\/)/.test(path) || /[\\#]/.test(path))throw Error('API 必须使用同源相对路径。');
   const url = path.startsWith('/api/') ? path : '/api/v1'+path;
   const method = (options.method || 'GET').toUpperCase(), writing = !['GET','HEAD'].includes(method);
   const auth = url.startsWith('/api/v1/auth/'), publicRead = options.public === true && !writing;
   if(!auth && !publicRead && !session.user)throw Object.assign(Error('请先登录。'),{status:401});
   if(writing && !session.csrf_token)throw Error('会话尚未准备好，请重新加载登录页。');
   const mine = revision, controller = new AbortController(); controllers.add(controller);
   const onAbort = () => controller.abort(); options.signal?.addEventListener('abort',onAbort,{once:true});
   if(options.signal?.aborted)controller.abort();
   let timedOut = false;
   const timer = setTimeout(()=>{timedOut=true;controller.abort();},options.timeout ?? 20000);
   try {
    const headers = {...options.headers};
    if(writing)headers['X-CSRF-Token']=session.csrf_token;
    if(options.body !== undefined)headers['Content-Type']='application/json';
    const response = await fetcher(url,{method,credentials:'same-origin',headers,body:options.body === undefined ? undefined : JSON.stringify(options.body),signal:controller.signal});
    if(mine !== revision)throw stale();
    let data; try{data=response.status===204?null:await response.json();}catch{throw Object.assign(Error('服务响应格式无效。'),{unknownOutcome:writing});}
    if(mine !== revision)throw stale();
    if(!response.ok){
     const retryAfter=response.headers?.get('Retry-After');
     const error=Object.assign(Error(typeof data?.detail==='string'?data.detail:'请求未完成（HTTP '+response.status+'）。'),{status:response.status,retryAfter});
     if(response.status===429)error.message += retryAfter ? ' 请在 '+retryAfter+' 秒后重试。' : ' 请稍后重试。';
     if(response.status===401&&!auth)change({...session,user:null,csrf_token:null});
     throw error;
    }
    return data;
   }catch(error){
    if(mine!==revision && error.status!==401)throw stale();
    if(!error.status && error.name!=='StaleResponseError' && (error.name==='AbortError'||error.name==='TypeError')){
     throw Object.assign(Error(writing?'连接中断，结果待确认。请先刷新核对，勿重复提交。':timedOut?'加载超时，请稍后重试。':'无法连接服务，请检查连接后重试。'),{unknownOutcome:writing,name:error.name});
    }
    throw error;
   }finally{clearTimeout(timer);options.signal?.removeEventListener('abort',onAbort);controllers.delete(controller);}
  }
  return {request, get session(){return session;},get revision(){return revision;}, subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);},
   async bootstrap(){const next=await request('/auth/session');change(next);return next;},
   async authenticate(path,body){const next=await request('/auth/'+path,{method:'POST',body});change(next);return next;},
   invalidate(){change({...session,user:null,csrf_token:null});}
  };
 }
 window.createAPIClient=createAPIClient;
 window.apiClient=createAPIClient();
})();
