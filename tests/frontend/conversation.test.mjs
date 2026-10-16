import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
function builder(){const c={window:{}};vm.createContext(c);if(fs.existsSync('frontend/conversation.js'))vm.runInContext(fs.readFileSync('frontend/conversation.js','utf8'),c);assert.equal(typeof c.window.ResearchConversation?.buildHistory,'function');return c.window.ResearchConversation.buildHistory;}
test('long dialogue retains recent exchanges and latest question within API limits',()=>{
 const build=builder(),history=[];for(let i=0;i<18;i++){history.push({role:'user',content:'股票问题'+i},{role:'assistant',content:'回复'+i,executions:[{secret:'private records'}]});}
 history.push({role:'user',content:'最后问题：它为什么下跌？'});const copy=JSON.stringify(history),result=build(history);
 assert(result.length<=20);assert.equal(result[0].role,'user');assert.equal(result.at(-1).content,'最后问题：它为什么下跌？');assert(result.every(m=>!m.executions));assert.equal(JSON.stringify(history),copy);
});
test('large answers and errors are bounded without truncating latest input',()=>{
 const build=builder(),history=[];for(let i=0;i<12;i++)history.push({role:'user',content:'问'+i},{role:'assistant',content:'答'.repeat(3000)});
 history.push({role:'assistant',error:true,content:'模型错误'},{role:'user',content:'新'.repeat(4000)});
 const result=build(history);assert(result.reduce((n,m)=>n+m.content.length,0)<=20000);assert.equal(result.at(-1).content.length,4000);assert(!result.some(m=>m.content==='模型错误'));
});

test('oversized assistant answers are explicitly excerpted for subsequent questions',()=>{
 const build=builder(),answer='开头依据'+ '答'.repeat(8000)+'结尾总结';
 const messages=[{role:'user',content:'分析一下'},{role:'assistant',content:answer},{role:'assistant',content:'   '},{role:'user',content:'问'.repeat(4000)}];
 const result=build(messages);
 assert(result.every(m=>m.content.length<=4000&&m.content.trim()));
 assert(result[1].content.startsWith('开头依据'));assert(result[1].content.endsWith('结尾总结'));
 assert(result[1].content.includes('原回答中间部分省略'));assert.equal(result.at(-1).content,messages.at(-1).content);
 assert.equal(messages[1].content,answer);
});
