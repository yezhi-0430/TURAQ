import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
class Element {
 constructor(){this.children=[];this.listeners={};this.value='';this.textContent='';this.hidden=true;this.open=false;this.dataset={};this.attrs={};this.classList={toggle(){}};this.style={};this.content={cloneNode:()=>new Element()};}
 append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this.children=nodes;} addEventListener(k,f){this.listeners[k]=f;} setAttribute(k,v){this.attrs[k]=v;} removeAttribute(k){delete this.attrs[k];} close(){this.open=false;} showModal(){this.open=true;} focus(){} contains(t){return t===this||this.children.includes(t);} getBoundingClientRect(){return{width:400};}
}
const flush=async()=>{for(let i=0;i<6;i++)await new Promise(r=>setImmediate(r));};
function fixture({mail=false,initialUser=null,suggestions=[]}={}){
 const els=new Map(),get=id=>{if(!els.has(id))els.set(id,new Element());return els.get(id);},events={};let user=initialUser,chatWrites=0,searchResolve;
 const modes=['login','register','forgot','reset','verify','resend'].map(authMode=>{const b=new Element();b.dataset.authMode=authMode;return b;});
 const requests=[],entry=new Element(),research=new Element(),home=new Element();
 const context={console,AbortController,setTimeout,clearTimeout,URL,URLSearchParams,CustomEvent:class{constructor(type){this.type=type;}},window:{location:{hash:'',search:'',pathname:'/'},history:{replaceState(){}},scrollTo(){},matchMedia:()=>({matches:true}),addEventListener:(k,f)=>{(events[k]??=[]).push(f);},dispatchEvent:e=>{for(const f of events[e.type]||[])f(e);}},document:{addEventListener(){},getElementById:get,createElement:()=>new Element(),querySelector:()=>research,querySelectorAll:selector=>selector==='[data-auth-mode]'?modes:selector==='[data-enter]'?[entry]:selector==='[data-home]'?[home]:[]},fetch:async(url,opts)=>{requests.push([url,opts]);if(url.endsWith('/session'))return res({user,csrf_token:user?'private-csrf':'anon-csrf',mail_configured:mail,model_mode:'fake'});if(url.endsWith('/login')){user={id:1,email:'synthetic@example.test',is_admin:false};return res({user,csrf_token:'private-csrf',mail_configured:mail,model_mode:'fake'});}if(url.endsWith('/logout')){user=null;return res({user:null,csrf_token:'new-anon',mail_configured:mail,model_mode:'fake'});}if(url.endsWith('/agent/chat')){chatWrites++;return res({answer:'A',executions:[{tool_name:'get_daily_prices',status:'success',source:{kind:'local_database',executed_at:'2026-10-11T15:00:00+08:00',latest_trade_date:'2026-10-09',record_count:1}}],suggestions});}if(url.endsWith('/watchlists'))return res([{id:1,name:'Synthetic owned group'}]);if(url.endsWith('/watchlists/1/stocks'))return res([{symbol:'000001.SZ',name:'Synthetic bank'}]);if(url.endsWith('/agent/actions/remove-stock'))return res({status:'success'});if(url.includes('/stocks/search'))return new Promise(r=>searchResolve=r);return res({detail:'请求已受理'});}};
 function res(data,status=200){return{ok:status<400,status,json:async()=>data,headers:{get:()=>null}};}
 vm.createContext(context);for(const path of ['frontend/api.js','frontend/actions.js'])vm.runInContext(fs.readFileSync(path,'utf8'),context);
 const html=fs.readFileSync('frontend/index.html','utf8'),inline=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];vm.runInContext(inline,context);vm.runInContext(fs.readFileSync('frontend/auth.js','utf8'),context);
 return {get,context,requests,entry,home,modes,res,get chatWrites(){return chatWrites;},finishSearch(data){searchResolve(res(data));}};
}
const event={preventDefault(){}};
test('anonymous entry opens accessible account form and never enters private app',async()=>{const f=fixture();await f.context.window.account.ready;await f.entry.listeners.click();assert.equal(f.get('app').hidden,true);assert.equal(f.get('auth-dialog').open,true);assert(f.get('auth-mail-note').textContent.includes('尚未配置'));f.modes[1].listeners.click();assert.equal(f.get('auth-submit').disabled,true);assert.equal(f.get('auth-invite-row').hidden,false);});
test('form login preserves password, enters app, and logout clears chat/account UI',async()=>{const f=fixture();await f.context.window.account.ready;await f.entry.listeners.click();f.get('auth-email').value='synthetic@example.test';f.get('auth-password').value=' abcde';await f.get('auth-form').listeners.submit(event);await flush();assert.equal(f.get('app').hidden,false);assert.equal(f.get('auth-dialog').open,false);assert.equal(JSON.parse(f.requests.find(([url])=>url.endsWith('/login'))[1].body).password,' abcde');f.get('input-box').value='question';await f.get('chatForm').listeners.submit(event);assert(f.get('messages-area').children.length>0);await f.get('account-button').listeners.click();assert.equal(f.get('app').hidden,true);assert.equal(f.get('account-email').textContent,'未登录');assert.equal(f.get('messages-area').children.length,1);assert.equal(f.get('input-box').value,'');});
for(const failure of ['offline','expired'])test(failure+' logout immediately clears every private component and preserves remote uncertainty',async()=>{
 const f=fixture({initialUser:{id:1,email:'a@example.test'}});await f.context.window.account.ready;await f.entry.listeners.click();
 f.get('input-box').value='question';await f.get('chatForm').listeners.submit(event);f.get('input-box').value='private draft';
 let resets=0,finish;for(const key of ['marketDashboard','watchlistManager','marketDetail'])f.context.window[key]={reset(){resets++;}};f.context.window.StockSearch={hide(){resets++;}};
 f.context.fetch=()=>new Promise((resolve,reject)=>finish=()=>failure==='offline'?reject(new TypeError('offline')):resolve(f.res({detail:'expired'},401)));
 const logout=f.get('account-button').listeners.click();assert.equal(f.context.window.apiClient.session.user,null);assert.equal(f.get('app').hidden,true);assert.equal(f.get('input-box').value,'');assert.equal(f.get('messages-area').children.length,1);assert.equal(resets,4);
 finish();await logout;assert(f.get('auth-status').textContent.includes('服务端退出结果未确认'));assert.equal(f.get('auth-submit').disabled,false);
 f.get('auth-close').listeners.click();assert.equal(f.get('app').hidden,true);
});
test('successful logout allows immediate account B credential login without switching form modes',async()=>{
 const f=fixture({initialUser:{id:1,email:'a@example.test'}});await f.context.window.account.ready;await f.entry.listeners.click();await f.get('account-button').listeners.click();
 assert.equal(f.get('auth-dialog').open,true);assert.equal(f.get('auth-submit').disabled,false);
 f.context.fetch=async(url,opts)=>{f.requests.push([url,opts]);return f.res({user:{id:2,email:'b@example.test'},csrf_token:'b',mail_configured:false,model_mode:'fake'});};
 f.get('auth-email').value='b@example.test';f.get('auth-password').value='123456';await f.get('auth-form').listeners.submit(event);await flush();
 assert.equal(f.context.window.apiClient.session.user.id,2);assert.equal(f.get('app').hidden,false);assert.equal(f.get('account-email').textContent,'b@example.test');
});
test('login shows authenticated idle chat status and re-entry preserves an active research status',async()=>{
 const f=fixture();await f.context.window.account.ready;await f.entry.listeners.click();f.get('auth-email').value='synthetic@example.test';f.get('auth-password').value='123456';await f.get('auth-form').listeners.submit(event);await flush();
 assert.equal(f.get('chat-status').textContent,'等待提问');f.get('chat-status').textContent='研究进行中';await f.entry.listeners.click();assert.equal(f.get('chat-status').textContent,'研究进行中');
});
test('editing or clearing watchlist queries discards delayed results including empty submit',async()=>{
 const f=fixture({initialUser:{id:1,email:'a@example.test'}});await f.context.window.account.ready;vm.runInContext(fs.readFileSync('frontend/watchlist.js','utf8'),f.context);
 for(const value of ['', 'different']){
  f.get('watch-query').value='bank';const pending=f.get('watch-search').listeners.submit(event);await flush();f.get('watch-query').value=value;
  f.get('watch-query').listeners.input?.();
  f.finishSearch({results:[{symbol:'000001.SZ',name:'old bank'}]});await pending;assert.equal(f.get('watch-results').children.length,0);assert.equal(f.get('watch-search-note').textContent,'');
 }
 f.get('watch-query').value='bank';const pending=f.get('watch-search').listeners.submit(event);await flush();f.get('watch-query').value='';await f.get('watch-search').listeners.submit(event);
 f.finishSearch({results:[{symbol:'000001.SZ',name:'old bank'}]});await pending;assert.equal(f.get('watch-results').children.length,0);assert.equal(f.get('watch-search-note').textContent,'');
});
test('repeated chat submit produces only one in-flight POST',async()=>{const f=fixture({initialUser:{id:1,email:'a@example.test'}});await f.context.window.account.ready;f.get('input-box').value='question';await Promise.all([f.get('chatForm').listeners.submit(event),f.get('chatForm').listeners.submit(event)]);assert.equal(f.chatWrites,1);});
test('catalog strings stay text; clearing search ignores delayed results',async()=>{const f=fixture();await f.context.window.account.ready;vm.runInContext(fs.readFileSync('frontend/stock-search.js','utf8'),f.context);const first=f.context.window.StockSearch.search('bank');await flush();f.finishSearch({results:[{symbol:'000001.SZ',code:'sz000001',name:'<img src=x onerror=alert(1)>',market:'SZ'}]});await first;assert.equal(f.get('stock-search-results').children[0].children[0].children[0].textContent,'<img src=x onerror=alert(1)>');const late=f.context.window.StockSearch.search('second');await flush();f.get('stock-search-input').value='';f.get('stock-search-input').listeners.input();f.finishSearch({results:[{name:'old private',symbol:'000002.SZ',code:'sz000002'}]});await late;assert.equal(f.get('stock-search-results').hidden,true);assert.equal(f.get('stock-search-results').children.length,0);});
test('registration/reset use the same untrimmed Unicode password rule and auth CSRF',async()=>{const f=fixture({mail:true});await f.context.window.account.ready;f.modes[1].listeners.click();f.get('auth-email').value='synthetic@example.test';f.get('auth-invite').value='fixture-invitation-123456';f.get('auth-password').value='12345';await f.get('auth-form').listeners.submit(event);assert(!f.requests.some(([url])=>url.endsWith('/register')));f.get('auth-password').value='😀'.repeat(6);await f.get('auth-form').listeners.submit(event);const registration=f.requests.find(([url])=>url.endsWith('/register'));assert.equal(JSON.parse(registration[1].body).password,'😀'.repeat(6));assert.equal(registration[1].headers['X-CSRF-Token'],'anon-csrf');f.modes[3].listeners.click();f.get('auth-token').value='fixture-reset-token-123456';f.get('auth-password').value='1234567890123456';await f.get('auth-form').listeners.submit(event);assert(!f.requests.some(([url])=>url.endsWith('/reset-password')));f.get('auth-password').value=' abcde';await f.get('auth-form').listeners.submit(event);assert.equal(JSON.parse(f.requests.find(([url])=>url.endsWith('/reset-password'))[1].body).password,' abcde');});
test('401 clears private UI, opens login and stops further private requests',async()=>{const f=fixture({initialUser:{id:1,email:'a@example.test'}});await f.context.window.account.ready;await f.entry.listeners.click();let privateCalls=0;f.context.fetch=async()=>{privateCalls++;return f.res({detail:'expired'},401);};await assert.rejects(f.context.window.apiClient.request('/watchlists'));assert.equal(f.get('app').hidden,true);assert.equal(f.get('auth-dialog').open,true);await assert.rejects(f.context.window.apiClient.request('/market/watchlist'));assert.equal(privateCalls,1);});
test('suggestion UI shows exact owned target, cancel sends no action and final doubleclick sends once',async()=>{const f=fixture({initialUser:{id:1,email:'a@example.test'},suggestions:[{kind:'suggestion',operation:'remove_watchlist_stock',watchlist_id:1,stock_code:'000001.SZ',text:'Synthetic proposal',confirmed:true}]});await f.context.window.account.ready;f.get('input-box').value='fixture proposal';await f.get('chatForm').listeners.submit(event);function pending(){return f.get('messages-area').children.at(-1).children.find(n=>n.className==='pending-action');}assert(pending().children[0].textContent.includes('尚未执行'));await pending().children[1].listeners.click();assert.equal(f.get('action-dialog').open,true);assert(f.get('action-description').textContent.includes('Synthetic owned group'));f.get('action-cancel').listeners.click();assert(!f.requests.some(([url])=>url.endsWith('/actions/remove-stock')));await pending().children[1].listeners.click();await Promise.all([f.get('action-confirm').listeners.click(),f.get('action-confirm').listeners.click()]);assert.equal(f.requests.filter(([url])=>url.endsWith('/actions/remove-stock')).length,1);assert(pending().children[0].textContent.includes('执行成功'));});

function renderedText(node){return [node.textContent,...node.children.map(renderedText)].join('\n');}

test('invalid tool arguments show the rejection and allow a later successful chat',async()=>{
 const f=fixture({initialUser:{id:1,email:'qa@example.test'}});await f.context.window.account.ready;
 const replies=[
  {run_id:'error-run',status:'completed',rounds:2,answer:'前期价格为零，无法计算。',model_mode:'fake',executions:[{tool_name:'calculate_change',arguments:{previous_close:0,current_close:9},status:'error',result:null,error:JSON.stringify({kind:'invalid_arguments',message:'previous_close must be greater than 0'}),duration_ms:0.1,source:null}]},
  {run_id:'recovered-run',status:'completed',rounds:2,answer:'下跌 10%',model_mode:'fake',executions:[{tool_name:'calculate_change',arguments:{previous_close:10,current_close:9},status:'success',result:JSON.stringify({change_percent:'-10.0000'}),error:null,duration_ms:0.1,source:null}]}
 ];
 f.context.fetch=async()=>f.res(replies.shift());
 f.get('input-box').value='invalid';await f.get('chatForm').listeners.submit(event);
 const failure=renderedText(f.get('messages-area'));
 assert(failure.includes('执行失败'));assert(failure.includes('invalid_arguments'));assert(failure.includes('previous_close must be greater than 0'));
 assert(!failure.includes('执行结果'));assert(!failure.includes('0%'));assert.equal(f.get('send-button').disabled,false);
 f.get('input-box').value='valid';await f.get('chatForm').listeners.submit(event);
 assert(renderedText(f.get('messages-area').children.at(-1)).includes('-10.0000'));
 assert.equal(f.get('chat-status').textContent,'本次研究已完成');assert.equal(replies.length,0);
});

test('round exhaustion preserves five tool records and stays incomplete without an answer',async()=>{
 const f=fixture({initialUser:{id:1,email:'qa@example.test'}});await f.context.window.account.ready;
 f.context.fetch=async()=>f.res({run_id:'limited-run',status:'max_rounds_exceeded',rounds:5,answer:null,model_mode:'fake',executions:Array.from({length:5},()=>({tool_name:'calculate_change',arguments:{previous_close:10,current_close:9},status:'success',result:JSON.stringify({change_percent:'-10.0000'}),error:null,duration_ms:0.1,source:null}))});
 f.get('input-box').value='repeat';await f.get('chatForm').listeners.submit(event);
 const last=f.get('messages-area').children.at(-1);
 assert(renderedText(last).includes('尚未形成最终答案'));
 assert.equal(last.children.filter(node=>node.className==='tool-record').length,5);
 assert.equal(f.get('chat-status').textContent,'本次研究未完成');assert(f.get('session-meta').textContent.includes('5 轮 · 未完成'));
 assert.equal(f.get('send-button').disabled,false);assert.equal(f.get('new-chat').disabled,false);
});


test('workspace re-entry reactivates an admin page after returning home',async()=>{
 const f=fixture({initialUser:{id:1,email:'admin@example.com',is_admin:true}});await f.context.window.account.ready;
 const calls=[];f.context.window.adminPanel={allowed:()=>true,setVisible:page=>calls.push(page),reset(){}};
 await f.context.window.selectWorkspacePage('admin-invites');assert.equal(calls.at(-1),'admin-invites');
 f.home.listeners.click();assert.equal(calls.at(-1),null);
 await vm.runInContext('enterWorkspace()',f.context);assert.equal(calls.at(-1),'admin-invites');
});
