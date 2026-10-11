// Component tests stub the central client contract; auth suites exercise the real client.
export function installComponentAPI(context){
 context.window.apiClient={request:async(path,options={})=>{
  const method=options.method||'GET',url=new URL(path.startsWith('/api/')?path:'/api/v1'+path,'http://fixture.test').href;
  const response=await context.fetch(url,{...options,method,body:options.body===undefined?undefined:JSON.stringify(options.body)});
  if(!response.ok)throw Object.assign(Error('HTTP '+response.status),{status:response.status});
  return response.status===204?null:response.json();
 }};
}
