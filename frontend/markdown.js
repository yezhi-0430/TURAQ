/* A small Markdown renderer: DOM nodes only, no raw HTML, images, or executable URLs. */
(() => {
 'use strict';
 const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
 function safeLink(value){
  try{if(typeof value!=='string'||/[\s\\]/.test(value))return null;const u=new URL(value);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch{return null;}
 }
 function inline(parent,text,depth=0){
  if(depth>4){parent.append(document.createTextNode(text));return;}
  const pattern=/(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|\[[^\]\n]+\]\([^\s)]+\))/g;
  let start=0,match;
  while((match=pattern.exec(text))){
   parent.append(document.createTextNode(text.slice(start,match.index)));
   const token=match[0];let child;
   if(token.startsWith('`'))child=node('code',token.slice(1,-1));
   else if(token.startsWith('**')||token.startsWith('__')){child=node('strong');inline(child,token.slice(2,-2),depth+1);}
   else if(token.startsWith('*')){child=node('em');inline(child,token.slice(1,-1),depth+1);}
   else{
    const parts=token.match(/^\[([^\]]+)\]\((.+)\)$/),href=safeLink(parts[2]);
    child=node(href?'a':'span');inline(child,parts[1],depth+1);
    if(href){child.href=href;child.target='_blank';child.rel='noopener noreferrer';}
   }
   parent.append(child);start=pattern.lastIndex;
  }
  parent.append(document.createTextNode(text.slice(start)));
 }
 const cells=line=>line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(s=>s.trim());
 const divider=line=>line&&line.includes('|')&&cells(line).every(s=>/^:?-{3,}:?$/.test(s));
 function render(value){
  const root=node('div');root.className='message-content markdown';
  const lines=String(value??'').replace(/\r\n?/g,'\n').split('\n');
  for(let i=0;i<lines.length;){
   const line=lines[i];if(!line.trim()){i++;continue;}
   if(/^\s*```/.test(line)){
    const pre=node('pre'),code=node('code'),body=[];i++;
    while(i<lines.length&&!/^\s*```/.test(lines[i]))body.push(lines[i++]);
    code.textContent=body.join('\n');pre.append(code);root.append(pre);if(i<lines.length)i++;continue;
   }
   if(line.includes('|')&&divider(lines[i+1])){
    const wrap=node('div');wrap.className='markdown-table-wrap';const table=node('table'),head=node('thead'),row=node('tr');
    for(const text of cells(line)){const cell=node('th');inline(cell,text);row.append(cell);}head.append(row);table.append(head);
    const body=node('tbody');i+=2;
    while(i<lines.length&&lines[i].includes('|')&&lines[i].trim()){
     const row=node('tr');for(const text of cells(lines[i++])){const cell=node('td');inline(cell,text);row.append(cell);}body.append(row);
    }
    table.append(body);wrap.append(table);root.append(wrap);continue;
   }
   const heading=line.match(/^\s{0,3}(#{1,6})\s+(.+)$/);
   if(heading){const h=node('h'+Math.min(6,heading[1].length));inline(h,heading[2]);root.append(h);i++;continue;}
   if(/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)){root.append(node('hr'));i++;continue;}
   const list=line.match(/^\s*(?:([-+*])|(\d+)\.)\s+(.+)$/);
   if(list){
    const ordered=Boolean(list[2]),group=node(ordered?'ol':'ul');
    if(ordered)group.setAttribute('start',list[2]);
    while(i<lines.length){const item=lines[i].match(/^\s*(?:([-+*])|(\d+)\.)\s+(.+)$/);if(!item||Boolean(item[2])!==ordered)break;const li=node('li');inline(li,item[3]);group.append(li);i++;}
    root.append(group);continue;
   }
   if(/^\s*>\s?/.test(line)){const quote=node('blockquote');inline(quote,line.replace(/^\s*>\s?/,''));root.append(quote);i++;continue;}
   const p=node('p');inline(p,line);root.append(p);i++;
  }
  return root;
 }
 window.SafeMarkdown={render};
})();
