import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Element {
 constructor(){this.children=[];this.listeners={};this.hidden=false;this.disabled=false;this.textContent='';this.value='';this.open=false;this.classList={toggle(){}};}
 append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this.children=nodes;} addEventListener(name,fn){this.listeners[name]=fn;}
 setAttribute(){} showModal(){this.open=true;} close(){this.open=false;}
}
const text=node=>[node.textContent,...node.children.map(text)].join('\n');
function fixture({admin=true,request=async()=>({users:[],invites:[],total:0})}={}){
 const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
 let session={user:{id:1,is_admin:admin},csrf_token:'test'},listeners=[];const calls=[];
 const api={get session(){return session;},subscribe(fn){listeners.push(fn);},request:async(path,opts)=>{calls.push([path,opts]);return request(path,opts);}};
 const context={window:{apiClient:api,addEventListener(){},selectWorkspacePage:async()=>{}},document:{getElementById:get,createElement:()=>new Element()},AbortController,console,Date,URLSearchParams};
 vm.createContext(context);vm.runInContext(fs.readFileSync('frontend/admin.js','utf8'),context);
 return{get,calls,panel:context.window.adminPanel,change(user){session={...session,user};listeners.forEach(fn=>fn(session));}};
}

test('ordinary accounts have no admin menu or admin fetch',async()=>{
 const f=fixture({admin:false});assert.equal(f.get('admin-label').hidden,true);
 assert.equal(f.panel.allowed(),false);await f.panel.setVisible('admin-users');assert.equal(f.calls.length,0);
});
test('user data stays text and missing timestamps remain unknown',async()=>{
 const f=fixture({request:async()=>({users:[{id:2,email:'<img onerror=alert(1)>',verified:true,disabled:false,is_admin:false,created_at:null,last_seen:null}],total:1})});
 await f.panel.setVisible('admin-users');const content=text(f.get('admin-users-body'));
 assert(content.includes('<img onerror=alert(1)>'));assert(content.includes('未记录'));assert(!content.includes('1970'));
});
test('account changes clear admin data and ignore late private reads',async()=>{
 let finish;const f=fixture({request:()=>new Promise(r=>finish=r)});const pending=f.panel.setVisible('admin-users');
 f.change({id:2,is_admin:false});finish({users:[{id:1,email:'old-private-account'}],total:1});await pending;
 assert(!text(f.get('admin-users-body')).includes('old-private-account'));assert.equal(f.get('admin-label').hidden,true);
});
test('cancelled status confirmation sends no mutation',async()=>{
 const f=fixture({request:async()=>({users:[{id:2,email:'member@example.com',verified:true,disabled:false,is_admin:false}],total:1})});
 await f.panel.setVisible('admin-users');const row=f.get('admin-users-body').children[0];await row.children.at(-1).children[0].listeners.click();
 assert.equal(f.get('admin-confirm-dialog').open,true);f.get('admin-confirm-cancel').listeners.click();
 assert(!f.calls.some(([,opts])=>opts?.method==='PATCH'));
});
test('new invitation is shown once and cleared when leaving its page',async()=>{
 const f=fixture({request:async(path,opts)=>opts?.method==='POST'?{id:7,code:'synthetic-new-code'}:{invites:[],total:0,users:[]}});
 await f.panel.setVisible('admin-invites');f.get('admin-invite-uses').value='50';f.get('admin-invite-days').value='7';
 await f.get('admin-create-invite').listeners.submit({preventDefault(){}});
 assert.equal(f.get('admin-new-code').textContent,'synthetic-new-code');
 await f.panel.setVisible('admin-users');assert.equal(f.get('admin-new-code').textContent,'');
});
test('forbidden response hides admin access and uncertain writes are never retried',async()=>{
 let mutations=0;const f=fixture({request:async(path,opts)=>{if(opts?.method==='POST'){mutations++;throw Object.assign(Error('结果待确认'),{unknownOutcome:true});}return{invites:[],total:0};}});
 await f.panel.setVisible('admin-invites');f.get('admin-invite-uses').value='50';f.get('admin-invite-days').value='7';
 await f.get('admin-create-invite').listeners.submit({preventDefault(){}});assert.equal(mutations,1);assert(text(f.get('admin-status')).includes('待确认'));
 const denied=fixture({request:async()=>{throw Object.assign(Error('forbidden'),{status:403});}});
 await denied.panel.setVisible('admin-users');assert.equal(denied.panel.allowed(),false);assert.equal(denied.get('admin-label').hidden,true);
});

test('double create submits produce one write; old account writes cannot unlock a new one',async()=>{
 const finishes=[];let writes=0;
 const f=fixture({request:async(path,opts)=>{if(opts?.method==='POST'){writes++;return new Promise(r=>finishes.push(r));}return{invites:[],users:[],total:0};}});
 await f.panel.setVisible('admin-invites');f.get('admin-invite-uses').value='50';f.get('admin-invite-days').value='7';
 const event={preventDefault(){}},submit=()=>f.get('admin-create-invite').listeners.submit(event);
 const old=submit();await submit();assert.equal(writes,1);
 f.change({id:2,is_admin:true});await f.panel.setVisible('admin-invites');const current=submit();assert.equal(writes,2);
 finishes[0]({id:1,code:'old-account-secret'});await old;
 assert.equal(f.get('admin-new-code').textContent,'');submit();assert.equal(writes,2,'old response must not release current write lock');
 finishes[1]({id:2,code:'current-account-code'});await current;
 assert.equal(f.get('admin-new-code').textContent,'current-account-code');
});

test('double confirmation sends exactly one status change and reloads after success',async()=>{
 let finish,writes=0;const f=fixture({request:async(path,opts)=>{if(opts?.method==='PATCH'){writes++;assert.deepEqual(JSON.parse(JSON.stringify(opts.body)),{disabled:true});return new Promise(r=>finish=r);}return{users:[{id:2,email:'member@example.com',verified:true,disabled:false,is_admin:false}],total:1};}});
 await f.panel.setVisible('admin-users');await f.get('admin-users-body').children[0].children.at(-1).children[0].listeners.click();
 const first=f.get('admin-confirm-button').listeners.click(),second=f.get('admin-confirm-button').listeners.click();
 assert.equal(writes,1);finish({id:2,disabled:true});await Promise.all([first,second]);assert(text(f.get('admin-status')).includes('已确认操作成功'));
});

test('committed invite survives refresh failure and reports the stale list',async()=>{
 let reads=0;const f=fixture({request:async(path,opts)=>{if(opts?.method==='POST')return{id:3,code:'save-this-once'};if(++reads>1)throw Error('refresh failed');return{invites:[],total:0};}});
 await f.panel.setVisible('admin-invites');f.get('admin-invite-uses').value='3';f.get('admin-invite-days').value='7';
 await f.get('admin-create-invite').listeners.submit({preventDefault(){}});
 assert.equal(f.get('admin-new-code').textContent,'save-this-once');assert(text(f.get('admin-status')).includes('刷新失败'));
});

test('settled mutations restore controls even after navigating to another admin page',async()=>{
 let finish;const f=fixture({request:async(path,opts)=>opts?.method==='POST'?new Promise(r=>finish=r):{invites:[],users:[],total:0}});
 await f.panel.setVisible('admin-invites');f.get('admin-invite-uses').value='3';f.get('admin-invite-days').value='7';
 const pending=f.get('admin-create-invite').listeners.submit({preventDefault(){}});
 await f.panel.setVisible('admin-users');finish({id:7,code:'not-shown-after-navigation'});await pending;
 await f.panel.setVisible('admin-invites');assert.equal(f.get('admin-create-button').disabled,false);
 assert.equal(f.get('admin-new-code').textContent,'');
});
