/* Decorative candles, with no market/model requests or automatic navigation. */
(() => {
 'use strict';
 function createEntranceController({landing,workspace,dialog,reducedMotion,authenticated}) {
  let generation=0;
  const animations=new Set();
  const clearAnimations=()=>{for(const animation of animations)animation.cancel();animations.clear();};
  function cancelTransition(){generation++;clearAnimations();landing.inert=false;dialog.inert=false;landing.classList.remove('intro-leaving');workspace.hidden=true;landing.hidden=false;}
  async function animate(element,frames,options){
   if(reducedMotion()||typeof element.animate!=='function')return;
   const animation=element.animate(frames,{...options,fill:'forwards'});animations.add(animation);
   await animation.finished;
  }
  async function enterWorkspace(){
   const mine=++generation;clearAnimations();
   const current=()=>mine===generation&&authenticated();
   if(!current())return false;
   landing.inert=true;dialog.inert=true;
   try{
    if(dialog.open){
     await animate(dialog,[{opacity:1,transform:'translateY(0)'},{opacity:0,transform:'translateY(-6px)'}],{duration:200,easing:'ease-in'});
     if(!current())return false;
     dialog.close();
    }
    landing.classList.add('intro-leaving');workspace.hidden=false;
    await Promise.all([
     animate(landing,[{opacity:1},{opacity:0}],{duration:480,easing:'ease-in-out'}),
     animate(workspace,[{opacity:0,transform:'translateY(10px)'},{opacity:1,transform:'translateY(0)'}],{duration:640,easing:'cubic-bezier(.22,1,.36,1)'})
    ]);
    if(!current())return false;
    landing.classList.add('intro-complete');landing.hidden=true;
    return true;
   }catch(error){
    if(error.name==='AbortError'||!current())return false;
    // A browser without usable animations still has a working authenticated entry.
    dialog.close();landing.classList.add('intro-complete');landing.hidden=true;workspace.hidden=false;return true;
   }finally{
    if(mine===generation){clearAnimations();landing.inert=false;dialog.inert=false;landing.classList.remove('intro-leaving');}
   }
  }
  return{enterWorkspace,cancelTransition};
 }
 window.createEntranceController=createEntranceController;
 const chart=document.getElementById('intro-chart');
 if(!chart)return;
 const ns='http://www.w3.org/2000/svg';
 function svgElement(tag,attributes){const node=document.createElementNS(ns,tag);for(const [key,value]of Object.entries(attributes))node.setAttribute(key,String(value));return node;}
 // Deliberately invented geometry: these are brand decoration, never quotations.
 const candles=[
  [720,700,735,689],[702,690,714,678],[693,674,706,666],[679,689,695,667],
  [691,665,704,653],[667,638,682,630],[640,650,658,628],[650,664,675,641],
  [663,642,676,633],[643,584,660,575],[587,579,606,565],[578,596,609,568],
  [596,562,610,551],[560,488,574,473],[490,508,518,481],[510,446,526,433],
  [446,344,460,326],[348,336,365,318],[336,369,382,322],[368,219,382,195],
  [220,177,244,158],[179,198,215,163],[199,130,216,109],[131,83,157,61]
 ];
 candles.forEach(([open,close,low,high],index)=>{
  const outer=svgElement('g',{transform:`translate(${78+index*62},0)`});
  const shape=svgElement('g',{class:`intro-candle ${close<open?'up':'down'}`,style:`--candle-delay:${(index*.123).toFixed(3)}s`});
  shape.append(svgElement('line',{x1:0,x2:0,y1:high,y2:low,class:'intro-wick'}),svgElement('rect',{x:-10,y:Math.min(open,close),width:20,height:Math.max(7,Math.abs(open-close)),rx:1.5,class:'intro-body'}));
  outer.append(shape);chart.append(outer);
 });
 const landing=document.getElementById('landing');
 window.siteEntrance=createEntranceController({landing,workspace:document.getElementById('app'),dialog:document.getElementById('auth-dialog'),reducedMotion:()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches,authenticated:()=>Boolean(window.apiClient?.session.user)});
 landing.classList.add('intro-running');
})();
