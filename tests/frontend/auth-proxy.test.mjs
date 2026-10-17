import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import path from 'node:path';
import { createServer } from '../../frontend/node_modules/vite/dist/node/index.js';
import config from '../../frontend/vite.config.js';
test('Vite serves api.js locally while preserving browser Origin for API proxy',async()=>{
 let origin=null;
 const backend=http.createServer((req,res)=>{origin=req.headers.origin;res.setHeader('Content-Type','application/json');if(req.url==='/api/v1/auth/session')res.end(JSON.stringify({user:null,csrf_token:'fixture'}));else{res.statusCode=404;res.end('{"detail":"Not Found"}');}});
 await new Promise(resolve=>backend.listen(0,'127.0.0.1',resolve));const target='http://127.0.0.1:'+backend.address().port;
 const proxy=Object.fromEntries(Object.entries(config.server.proxy).map(([route,opts])=>[route,{...opts,target}]));
 const server=await createServer({configFile:false,root:path.resolve('frontend'),server:{host:'127.0.0.1',port:0,proxy},plugins:config.plugins});
 try{await server.listen();const base='http://127.0.0.1:'+server.httpServer.address().port;const script=await fetch(base+'/api.js');assert.equal(script.status,200,'api.js must not be sent to backend');assert((await script.text()).includes('window.apiClient=createAPIClient()'));assert.equal((await fetch(base+'/auth.js')).status,200);const session=await fetch(base+'/api/v1/auth/session',{headers:{Origin:base}});assert.equal(session.status,200);assert.equal(origin,base,'proxy must retain browser Origin for CSRF');}
 finally{await server.close();await new Promise(resolve=>backend.close(resolve));}
});
