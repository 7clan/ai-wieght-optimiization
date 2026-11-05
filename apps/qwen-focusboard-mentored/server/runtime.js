/* Trusted runtime only; Qwen Express routes are parsed and run within Docker. */
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {spawnSync}=require('node:child_process');
const express=require('express');
const esbuild=require('esbuild');

const ROOT=path.resolve(__dirname,'..');
const worker=path.join(__dirname,'sqlite_store.py');

function workerCall(action,data={}) {
  const result=spawnSync('python3',['-I','-B',worker],{
    input:JSON.stringify({action,...data}),encoding:'utf8',timeout:2500,
    maxBuffer:1024*1024,
    env:{PYTHONDONTWRITEBYTECODE:'1',PYTHONHASHSEED:'0',DB_PATH:'/data/focusboard.sqlite3'}
  });
  if(result.error||result.status!==0)throw Error('SQLite worker: '+(result.stderr||result.error?.message).slice(-250));
  const response=JSON.parse(result.stdout);
  if(!response.ok)throw Error(response.error||'Database operation failed');
  return response.value;
}

const store={
  list:()=>workerCall('list'),
  create:body=>workerCall('create',{body}),
  update:(id,body)=>workerCall('update',{id,body}),
  delete:id=>workerCall('delete',{id})
};
const processor=payload=>workerCall('summary',{payload});

function loadModelRoutes() {
  const source=fs.readFileSync(path.join(ROOT,'generated/server/routes.js'),'utf8');
  const code=esbuild.transformSync(source+'\nmodule.exports=createApp;',{
    loader:'jsx',format:'cjs',target:'es2022'
  }).code;
  const module={exports:{}};
  const sandbox=vm.createContext({module,exports:module.exports,
    require:id=>{if(id==='express')return express;throw Error('Blocked require: '+id);},
    console:{log(){},warn(){},error(){}}},
    {codeGeneration:{strings:false,wasm:false}});
  new vm.Script(code,{filename:'qwen-routes.js'}).runInContext(sandbox,{timeout:1500});
  if(typeof module.exports!=='function')throw Error('Generated Express factory missing');
  return module.exports;
}

const app=loadModelRoutes()(store,processor);
app.disable('x-powered-by');
app.use(express.static(path.join(ROOT,'public'),{index:'index.html',maxAge:0}));

if(require.main===module){
  const port=Number(process.env.PORT||3000);
  app.listen(port,'0.0.0.0',()=>console.log('FocusBoard listening on '+port));
}
module.exports=app;
