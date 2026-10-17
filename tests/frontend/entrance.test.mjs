import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

function fixture({reduced=false}={}) {
 const context={window:{},document:{getElementById:()=>null},console};
 vm.createContext(context);
 if(fs.existsSync('frontend/entrance.js'))vm.runInContext(fs.readFileSync('frontend/entrance.js','utf8'),context);
 assert.equal(typeof context.window.createEntranceController,'function','entrance controller exists');
 const active=[];let signedIn=true;
 function element(hidden=false){return{hidden,classList:{add(){},remove(){}},animate(){let finish,reject;const finished=new Promise((a,b)=>{finish=a;reject=b;});const animation={finished,finish,cancel:()=>reject(Object.assign(Error('cancelled'),{name:'AbortError'}))};active.push(animation);return animation;}};}
 const landing=element(),workspace=element(true),dialog={...element(),open:true,close(){this.open=false;}};
 const controller=context.window.createEntranceController({landing,workspace,dialog,reducedMotion:()=>reduced,authenticated:()=>signedIn});
 return{controller,landing,workspace,dialog,active,logout(){signedIn=false;controller.cancelTransition();}};
}
test('entrance initialization stays put until a user starts login',()=>{
 const f=fixture();assert.equal(f.workspace.hidden,true);assert.equal(f.dialog.open,true);assert.equal(f.active.length,0);
});
test('reduced motion enters authenticated workspace without an animation',async()=>{
 const f=fixture({reduced:true});assert.equal(await f.controller.enterWorkspace(),true);
 assert.equal(f.landing.hidden,true);assert.equal(f.workspace.hidden,false);assert.equal(f.dialog.open,false);assert.equal(f.active.length,0);
});
test('session clearing during login transition cannot reveal an old workspace',async()=>{
 const f=fixture();const entered=f.controller.enterWorkspace();assert.equal(f.active.length,1);
 f.logout();assert.equal(await entered,false);assert.equal(f.workspace.hidden,true);assert.equal(f.landing.hidden,false);
});
test('login and landing fade finish before transition reports completion',async()=>{
 const f=fixture();const entered=f.controller.enterWorkspace();f.active[0].finish();
 await new Promise(r=>setImmediate(r));assert.equal(f.dialog.open,false);assert.equal(f.workspace.hidden,false);assert.equal(f.landing.hidden,false);
 for(const animation of f.active.slice(1))animation.finish();
 assert.equal(await entered,true);assert.equal(f.landing.hidden,true);assert.equal(f.workspace.hidden,false);
});
test('logout while workspace is fading in immediately hides it and discards completion',async()=>{
 const f=fixture();const entered=f.controller.enterWorkspace();f.active[0].finish();await new Promise(r=>setImmediate(r));
 assert.equal(f.workspace.hidden,false);f.logout();assert.equal(await entered,false);
 assert.equal(f.workspace.hidden,true);assert.equal(f.landing.hidden,false);
});
test('returning home during entry cancels it even while the account remains logged in',async()=>{
 const f=fixture();const entered=f.controller.enterWorkspace();f.active[0].finish();await new Promise(r=>setImmediate(r));
 f.controller.cancelTransition();assert.equal(await entered,false);assert.equal(f.workspace.hidden,true);assert.equal(f.landing.hidden,false);
});
test('transition blocks mouse and keyboard re-entry until it finishes or is cancelled',async()=>{
 const f=fixture();const entered=f.controller.enterWorkspace();
 assert.equal(f.landing.inert,true);assert.equal(f.dialog.inert,true);
 f.controller.cancelTransition();assert.equal(await entered,false);
 assert.equal(f.landing.inert,false);assert.equal(f.dialog.inert,false);
});
