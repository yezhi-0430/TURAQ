import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.textContent='';this.attrs={};}
 append(...nodes){this.children.push(...nodes);}
 setAttribute(key,value){this.attrs[key]=value;}
 set innerHTML(value){throw Error('unsafe innerHTML');}
}
const context={window:{},URL,document:{createElement:tag=>new Element(tag),createTextNode:text=>({textContent:text,children:[]})}};
vm.createContext(context);vm.runInContext(fs.readFileSync('frontend/markdown.js','utf8'),context);
const render=context.window.SafeMarkdown.render;
const flatten=n=>[n,...n.children.flatMap(flatten)];
const doc=render('## 数据分析\n\n**股票资料**\n- 名称：贵州茅台\n- `600519.SH`\n\n```json\n{"price":10}\n```\n\n| 日期 | 收盘 |\n| --- | --- |\n| 2024-01-02 | 10 |');
const tags=flatten(doc).map(n=>n.tagName);
for(const tag of ['h2','strong','ul','li','code','pre','table','th','td'])assert(tags.includes(tag),tag+' rendered');
const hostile=flatten(render('<script>alert(1)</script>\n<img src=x onerror=bad>\n[x](javascript:alert)\n[凭据](https://u:p@example.com)\n[来源](https://example.com/report)'));
assert.equal(hostile.filter(n=>n.tagName==='script'||n.tagName==='img').length,0);
const links=hostile.filter(n=>n.tagName==='a');assert.equal(links.length,1);assert.equal(links[0].rel,'noopener noreferrer');
assert(hostile.some(n=>n.textContent.includes('<script>')));
console.log('PASS: safe markdown headings, bold, lists, code, table, escaped HTML and checked external links');
