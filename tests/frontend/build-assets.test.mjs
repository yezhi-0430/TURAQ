import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
const root='frontend/dist';
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
for(const match of html.matchAll(/<script[^>]*src="([^"]+)"/g)){
 const src=match[1];if(/^https?:/.test(src))continue;
 assert(fs.existsSync(path.join(root,src.replace(/^\//,''))),`built page script exists: ${src}`);
}
console.log('PASS: all scripts referenced by the production page exist');
const assets=fs.readdirSync(path.join(root,'assets')).filter(name=>name.endsWith('.js')).map(name=>fs.readFileSync(path.join(root,'assets',name),'utf8')).join('\n');
assert(assets.includes('stock-search-input'),'stock catalog component is bundled');
assert(assets.includes('/stocks/search?q='),'catalog API adapter is bundled');
assert(assets.includes('X-CSRF-Token'),'central CSRF client is bundled');
assert(assets.includes('theme-select-trigger'),'themed controls are bundled');
assert(!/https?:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?\/api/.test(html+assets),'no cross-origin localhost API URL in build');
for(const match of html.matchAll(/<link[^>]*href="([^"]+)"/g)){const href=match[1];if(!/^https?:/.test(href))assert(fs.existsSync(path.join(root,href.replace(/^\//,''))),`built stylesheet exists: ${href}`);}
console.log('PASS: stock catalog/auth bundled, CSS present, no cross-origin localhost API');
