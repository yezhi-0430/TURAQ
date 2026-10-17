import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
test('workspace focuses on answers and hides tool inventory and execution explanation',()=>{
 const html=fs.readFileSync('frontend/index.html','utf8');
 const tags=[...html.matchAll(/class="tool-tag">([^<]+)/g)].map(m=>m[1]);
 assert.equal(tags.length,0);
 assert(html.includes('research-grid answer-only'));
 assert(!html.includes('一条清晰的研究路径'));
 assert(!html.includes('正在分析问题与执行工具'));
 assert(html.includes('主要指数表现与简短概括'));assert(html.includes('最近 90'));
});
test('provenance distinguishes catalog, observation time, calculation input and partial data',()=>{
 const c={window:{}};vm.createContext(c);vm.runInContext(fs.readFileSync('frontend/actions.js','utf8'),c);
 const describe=c.window.describeSource;
 assert(describe({kind:'cached_catalog',record_count:2}).includes('股票代码目录'));
 const quote=describe({kind:'online_market',record_count:1,quote_time:'2026-10-09T15:00:00+08:00',data_status:'partial'});
 assert(quote.includes('行情观测时间'));assert(quote.includes('部分失败'));
 const calc=describe({kind:'python_calculation',inputs_origin:'market_data',data_status:'insufficient_data',price_adjustment:'qfq'});
 assert(calc.includes('已查询行情'));assert(calc.includes('信息不足'));assert(calc.includes('前复权'));
});
