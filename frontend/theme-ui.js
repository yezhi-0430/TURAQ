/* Presentation only: native form values, business handlers and permissions remain authoritative. */
(() => {
 'use strict';
 const controls=new Set(), enhanced=new WeakMap(), disclosures=new WeakMap(), animations=new Set();
 const easing='cubic-bezier(.22,1,.36,1)';
 let active=null,serial=0,scanPending=false;
 const reduced=()=>document.documentElement?.dataset?.reduceMotion==='true'||window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 const element=(tag,cls,text)=>{const n=document.createElement(tag);n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 function motion(node,frames,duration=240){
  if(reduced()||!node.animate)return null;
  const animation=node.animate(frames,{duration,easing,fill:'both'});animations.add(animation);
  animation.finished.then(()=>{animations.delete(animation);animation.cancel();},()=>animations.delete(animation));
  return animation;
 }
 function reveal(node){if(node&&!node.hidden)motion(node,[{opacity:0,transform:'translateY(8px)'},{opacity:1,transform:'translateY(0)'}]);}
 function close(control=active,immediate=false){
  if(!control)return;
  const {button,menu}=control;control.generation++;control.animation?.cancel();control.animation=null;
  if(active===control)active=null;
  button.setAttribute('aria-expanded','false');button.removeAttribute('aria-activedescendant');
  const generation=control.generation;
  const finish=()=>{
   if(generation!==control.generation)return;
   if(menu.hidePopover&&menu.matches(':popover-open'))menu.hidePopover();
   menu.hidden=true;menu.replaceChildren();control.items=[];
  };
  if(immediate||menu.hidden||reduced()){finish();return;}
  control.animation=motion(menu,[{opacity:1,transform:'translateY(0)'},{opacity:0,transform:'translateY(-5px)'}],140);
  if(control.animation)control.animation.finished.then(finish,()=>{});else finish();
 }
 function sync(control){
  const {native,button,text}=control;
  const selected=native.options[native.selectedIndex];
  const value=selected?.textContent||'请选择';if(text.textContent!==value)text.textContent=value;
  if(button.disabled!==native.disabled)button.disabled=native.disabled;
  const label=native.getAttribute('aria-label')||control.label;
  if(button.getAttribute('aria-label')!==label)button.setAttribute('aria-label',label);
  if(active===control&&(native.disabled||native.closest('[hidden]')))close(control,true);
 }
 function highlight(control,index){
  if(!control.items.length)return;
  control.highlight=index;
  control.items.forEach((item,i)=>item.classList.toggle('is-highlighted',i===index));
  const item=control.items[index];if(!item)return;
  control.button.setAttribute('aria-activedescendant',item.id);
  const top=item.offsetTop,bottom=top+item.offsetHeight;
  if(top<control.menu.scrollTop)control.menu.scrollTop=top;
  else if(bottom>control.menu.scrollTop+control.menu.clientHeight)control.menu.scrollTop=bottom-control.menu.clientHeight;
 }
 function choose(control,index){
  const option=control.native.options[index];if(!option||option.disabled)return;
  const changed=control.native.selectedIndex!==index;
  control.native.selectedIndex=index;sync(control);close(control);control.button.focus({preventScroll:true});
  if(changed){control.native.dispatchEvent(new Event('input',{bubbles:true}));control.native.dispatchEvent(new Event('change',{bubbles:true}));}
 }
 function renderOptions(control){
  control.menu.replaceChildren();control.items=[];
  Array.from(control.native.options).forEach((option,index)=>{
   const item=element('button','theme-select-option');item.type='button';item.id=control.menu.id+'-'+index;
   item.setAttribute('role','option');item.setAttribute('aria-selected',String(index===control.native.selectedIndex));item.setAttribute('aria-disabled',String(option.disabled));item.disabled=option.disabled;
   item.append(element('span','theme-option-text',option.textContent));
   const check=element('span','theme-option-check',index===control.native.selectedIndex?'✓':'');check.setAttribute('aria-hidden','true');item.append(check);
   item.tabIndex=-1;item.addEventListener('pointermove',()=>{if(!option.disabled)highlight(control,index);});item.addEventListener('click',()=>choose(control,index));
   control.menu.append(item);control.items.push(item);
  });
  if(!control.items.length)control.menu.append(element('p','theme-select-empty','暂无可选项'));
 }
 function position(control){
  const {menu,button}=control;
  const rect=button.getBoundingClientRect(),width=Math.min(Math.max(rect.width,224),window.innerWidth-24);
  const below=window.innerHeight-rect.bottom-18,above=rect.top-18,up=below<160&&above>below;
  const height=Math.max(48,Math.min(320,up?above:below));
  menu.style.width=width+'px';menu.style.maxHeight=height+'px';
  menu.style.left=Math.max(12,Math.min(rect.left,window.innerWidth-width-12))+'px';
  menu.style.top=(up?Math.max(12,rect.top-Math.min(menu.scrollHeight,height)-8):rect.bottom+8)+'px';
  return up;
 }
 function open(control){
  if(control.native.disabled||control.native.closest('[hidden]'))return;
  if(active&&active!==control)close(active,true);
  control.generation++;control.animation?.cancel();control.animation=null;active=control;sync(control);renderOptions(control);
  const {menu,button}=control;menu.hidden=false;button.setAttribute('aria-expanded','true');
  if(menu.showPopover&&!menu.matches(':popover-open'))menu.showPopover();
  const up=position(control);
  const selected=control.native.selectedIndex;
  highlight(control,selected>=0&&!control.native.options[selected]?.disabled?selected:control.items.findIndex(item=>!item.disabled));
  control.animation=motion(menu,[{opacity:0,transform:`translateY(${up?5:-7}px) scale(.98)`},{opacity:1,transform:'translateY(0) scale(1)'}]);
 }
 function keyboard(control,event){
  const key=event.key;
  if(key==='Tab'){close(control,true);return;}
  if(key==='Escape'){if(active===control){event.preventDefault();event.stopPropagation();close(control);}return;}
  if(['ArrowDown','ArrowUp','Home','End','Enter',' '].includes(key)){
   event.preventDefault();
   if(active!==control){open(control);if(key==='Home')highlight(control,control.items.findIndex(i=>!i.disabled));if(key==='End')highlight(control,control.items.findLastIndex(i=>!i.disabled));return;}
   if(key==='Enter'||key===' '){choose(control,control.highlight);return;}
   const enabled=control.items.map((item,i)=>!item.disabled?i:-1).filter(i=>i>=0);if(!enabled.length)return;
   let index=enabled.indexOf(control.highlight);
   if(key==='Home')index=0;else if(key==='End')index=enabled.length-1;else index=(index+(key==='ArrowDown'?1:-1)+enabled.length)%enabled.length;
   highlight(control,enabled[index]);return;
  }
  if(key.length===1&&!event.ctrlKey&&!event.altKey&&!event.metaKey&&!event.isComposing){
   if(active!==control)open(control);
   const now=Date.now();control.search=now-(control.searchAt||0)>650?key:control.search+key;control.searchAt=now;
   const index=control.items.findIndex(item=>!item.disabled&&item.textContent.toLowerCase().includes(control.search.toLowerCase()));if(index>=0)highlight(control,index);
  }
 }
 function enhance(native){
  if(enhanced.has(native)||native.multiple||native.size>1)return;
  const labels=Array.from(native.labels||[]);
  const label=native.getAttribute('aria-label')||labels.map(l=>Array.from(l.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent.trim()).join(' ')).join(' ')||'选择';
  const key=native.id||'theme-select-'+(++serial),wrapper=element('span','theme-select'),button=element('button','theme-select-trigger'),text=element('span','theme-select-value'),chevron=element('span','theme-select-chevron'),menu=element('div','theme-select-menu');
  button.type='button';button.dataset.selectFor=key;button.setAttribute('role','combobox');button.setAttribute('aria-haspopup','listbox');button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls',key+'-theme-menu');
  text.id=key+'-theme-value';button.setAttribute('aria-describedby',text.id);
  chevron.setAttribute('aria-hidden','true');button.append(text,chevron);menu.id=key+'-theme-menu';menu.setAttribute('role','listbox');menu.setAttribute('aria-label',label);menu.hidden=true;
  if(menu.showPopover)menu.setAttribute('popover','manual');
  const control={native,button,text,menu,wrapper,label,items:[],generation:0,highlight:-1,animation:null,search:''};enhanced.set(native,control);controls.add(control);
  // Existing business code writes value/selectedIndex directly (e.g. chart adjustments).
  // Forward the native setter unchanged, then update presentation without dispatching a request.
  for(const property of ['value','selectedIndex']){
   const descriptor=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,property);
   Object.defineProperty(native,property,{configurable:true,enumerable:descriptor.enumerable,
    get(){return descriptor.get.call(this);},
    set(value){descriptor.set.call(this,value);sync(control);if(active===control){renderOptions(control);highlight(control,native.selectedIndex);}}
   });
  }
  native.classList.add('theme-native-select');native.tabIndex=-1;native.setAttribute('aria-hidden','true');
  native.before(wrapper);wrapper.append(native,button,menu);
  labels.forEach(label=>label.addEventListener('click',event=>{
   if(event.target.closest('button,a,input,select,.theme-select'))return;
   event.preventDefault();button.focus({preventScroll:true});open(control);
  }));
  button.addEventListener('click',()=>active===control?close(control):open(control));button.addEventListener('keydown',event=>keyboard(control,event));native.addEventListener('change',()=>{sync(control);if(active===control)close(control,true);});
  control.observer=new MutationObserver(()=>{sync(control);if(active===control){renderOptions(control);highlight(control,native.selectedIndex);}});
  control.observer.observe(native,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['disabled','selected','value','label','aria-label']});
  native.addEventListener('invalid',()=>button.focus());sync(control);
 }
 function scan(){
  document.querySelectorAll('select').forEach(enhance);
  for(const control of controls){if(!control.native.isConnected){close(control,true);control.observer.disconnect();controls.delete(control);}else sync(control);}
 }
 function scheduleScan(){if(scanPending)return;scanPending=true;queueMicrotask(()=>{scanPending=false;scan();});}
 function disclosure(details){
  let state=disclosures.get(details);
  if(!state){
   const summary=details.querySelector(':scope > summary'),body=element('div','theme-disclosure-body');
   for(const child of Array.from(details.childNodes))if(child!==summary)body.append(child);
   details.append(body);state={body,desired:details.open,animation:null,generation:0};disclosures.set(details,state);
  }
  const {body}=state,start=details.open?body.getBoundingClientRect().height:0;state.desired=!state.desired;state.generation++;state.animation?.cancel();
  const generation=state.generation;
  if(reduced()){details.open=state.desired;return;}
  details.open=true;body.style.overflow='hidden';
  const end=state.desired?body.scrollHeight:0;
  state.animation=motion(body,[{height:start+'px',opacity:start?1:0},{height:end+'px',opacity:state.desired?1:0}],260);
  const finish=()=>{if(generation!==state.generation)return;details.open=state.desired;body.style.overflow='';state.animation=null;};
  if(state.animation)state.animation.finished.then(finish,()=>{});else finish();
 }
 document.addEventListener('click',event=>{
  const summary=event.target.closest('summary');
  if(summary&&summary.parentElement.tagName==='DETAILS'){event.preventDefault();disclosure(summary.parentElement);}
  const tab=event.target.closest('.detail-tab,[data-auth-mode],.watch-group');
  if(tab)requestAnimationFrame(()=>reveal(document.getElementById(tab.matches('.detail-tab')?'detail-chart':tab.matches('.watch-group')?'watch-members':'auth-form')));
 });
 document.addEventListener('pointerdown',event=>{if(active&&!active.wrapper.contains(event.target))close(active);},true);
 document.addEventListener('reset',()=>{close(active,true);queueMicrotask(()=>{for(const control of controls)sync(control);});});
 window.addEventListener('resize',()=>close(active,true));
 document.addEventListener('scroll',event=>{
  if(!active||event.target===active.menu||active.menu.contains(event.target))return;
  const rect=active.button.getBoundingClientRect();
  if(rect.bottom<12||rect.top>window.innerHeight-12)close(active,true);else position(active);
 },true);
 window.addEventListener('private-session-cleared',()=>{
  for(const control of controls)close(control,true);for(const animation of animations)animation.cancel();animations.clear();
  document.querySelectorAll('details').forEach(details=>{const state=disclosures.get(details);if(state){state.generation++;details.open=state.desired;state.body.style.overflow='';state.animation=null;}});queueMicrotask(scan);
 });
 const observer=new MutationObserver(records=>{
  for(const record of records){
   if(record.type==='attributes'&&record.attributeName==='hidden'){
    const target=record.target;
    if(target.hidden&&active&&target.contains(active.native))close(active,true);
    else if(!target.hidden&&target.matches('#risk-detail,#admin-code-box,#stock-search-results,[id^="admin-tab-"]'))reveal(target);
   }
   if(record.type==='childList'&&Array.from(record.addedNodes).some(n=>n.nodeType===1&&(n.matches('select')||n.querySelector('select'))))scheduleScan();
  }
 });
 observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['hidden']});
 window.ThemeUI={sync:scan,reveal,close:()=>close(active,true)};scan();
})();
