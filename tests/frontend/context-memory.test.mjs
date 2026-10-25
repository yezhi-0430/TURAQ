import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.value='';this.checked=false;this.hidden=false;this.disabled=false;this.textContent='';}
 append(...children){this.children.push(...children);} replaceChildren(...children){this.children=children;}
 addEventListener(type,fn){this.listeners[type]=fn;} setAttribute(){}
}
function fixture(request){
 const calls=[],subscriptions=[],events={};let user={id:1};
 const api={get session(){return{user};},subscribe(fn){subscriptions.push(fn);},async request(path,options){calls.push([path,options]);return request(path,options);}};
 const window={apiClient:api,addEventListener(type,fn){events[type]=fn;}},document={createElement:tag=>new Element(tag)};
 const ctx=vm.createContext({window,document});
 vm.runInContext(fs.readFileSync('frontend/context-memory.js','utf8'),ctx);
 const host=new Element();
 return{panel:window.contextMemory,host,calls,change(next){user=next;subscriptions.forEach(fn=>fn({user}));},clear(){events['private-session-cleared']?.();}};
}
const find=(node,tag)=>node.tagName===tag?node:node.children.map(child=>find(child,tag)).find(Boolean);
const text=node=>[node.textContent,...node.children.map(text)].join('\n');
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('explicit typed memory save uses account API and clears without browser storage',async()=>{
 const f=fixture(async(path,options)=>({state:'ready',preferences:options?.method==='DELETE'?null:{answer_detail:'detailed',include_page_refs:true,check_original_units:true}}));
 await f.panel.show(true,f.host);assert(text(f.host).includes('研究偏好'));
 const form=find(f.host,'form');await form.listeners.submit({preventDefault(){}});
 assert.equal(f.calls[1][1].method,'PUT');assert.equal(f.calls[1][1].body.answer_detail,'detailed');
 const all=node=>[node,...node.children.flatMap(all)];const buttons=all(f.host);
 const clear=buttons.find(n=>n.textContent==='清除偏好');assert(clear);await clear.listeners.click();
 assert.equal(f.calls[2][1].method,'DELETE');assert(text(f.host).includes('未保存'));
});

test('late read from previous account cannot render memory',async()=>{
 let finish;const f=fixture(()=>new Promise(resolve=>finish=resolve));
 const pending=f.panel.show(true,f.host);f.change({id:2});finish({state:'ready',preferences:{answer_detail:'detailed'}});await pending;
 assert(!text(f.host).includes('已保存'));assert.equal(find(f.host,'select').value,'concise');
});

test('offline or disabled service exposes a retry state and disables saving',async()=>{
 const f=fixture(async()=>({state:'unavailable',preferences:null}));await f.panel.show(true,f.host);
 assert(text(f.host).includes('暂不可用'));assert.equal(find(f.host,'button').disabled,true);
 f.clear();await tick();assert.equal(find(f.host,'select').value,'concise');
});
