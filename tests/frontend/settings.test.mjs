import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

assert(fs.existsSync('frontend/settings.js'), 'settings controller must exist');
const context={window:{},console};
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/settings.js','utf8'),context);
const rules=context.window.SettingsRules;
assert(rules, 'shared settings rules are available without DOM');
const defaults=JSON.parse(JSON.stringify(rules.defaults));
assert.equal(defaults.default_page,'agent');
assert.equal(defaults.paper_order_type,'limit');
assert.equal(defaults.market_refresh_seconds,10);
assert.deepEqual(JSON.parse(JSON.stringify(rules.validatePreferences(defaults))),defaults);
for(const change of [{market_refresh_seconds:1},{research_max_rounds:16},{paper_initial_capital:0},{paper_commission_rate:0.03},{density:'invalid'},{market_auto_refresh:'false'},{is_admin:true}]){
 assert.throws(()=>rules.validatePreferences({...defaults,...change}));
}
const exported=rules.exportPreferences(defaults);
assert.deepEqual(JSON.parse(JSON.stringify(rules.importPreferences(JSON.stringify(exported)))),defaults);
assert.throws(()=>rules.importPreferences(JSON.stringify({kind:'admin-settings',schema_version:1,preferences:defaults})));
assert.throws(()=>rules.importPreferences(JSON.stringify({kind:'turaq-personal-settings',schema_version:99,preferences:defaults})));
assert.throws(()=>rules.importPreferences('null'));
assert.throws(()=>rules.importPreferences('{'));
assert.throws(()=>rules.importPreferences(JSON.stringify({kind:'turaq-personal-settings',schema_version:1,preferences:{...defaults,default_page:'admin-users'}})));
assert.equal(rules.shouldSend({key:'Enter',shiftKey:false,ctrlKey:false,metaKey:false,isComposing:false},'enter'),true);
assert.equal(rules.shouldSend({key:'Enter',shiftKey:false,ctrlKey:false,metaKey:false,isComposing:false},'ctrl_enter'),false);
assert.equal(rules.shouldSend({key:'Enter',ctrlKey:true,isComposing:false},'ctrl_enter'),true);
assert.equal(rules.shouldSend({key:'Enter',metaKey:true,isComposing:false},'ctrl_enter'),true);
assert.equal(rules.shouldSend({key:'Enter',isComposing:true},'enter'),false);
assert.equal(rules.shouldSend({key:'Enter',shiftKey:true},'enter'),false);
const stocks=[{name:'乙',symbol:'sz000002'},{name:'甲',symbol:'sh600000'}];
assert.equal(rules.sortStocks(stocks,'symbol')[0].symbol,'sh600000');
assert.equal(stocks[0].symbol,'sz000002','sorting must not mutate source');
assert.deepEqual(JSON.parse(JSON.stringify(rules.sortStocks(stocks,'default'))),stocks);
console.log('PASS: personal settings validation, safe import/export, keyboard and sorting');
