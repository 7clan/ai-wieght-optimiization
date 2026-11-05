// All Qwen-produced source executes exclusively in unprivileged, restricted Docker.
// Session031 evaluator: DevMetrics. Adds a behavioral jsdom mount proving the
// generated React UI really enters its required offline demo mode.
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const vm=require('node:vm');
const {spawnSync}=require('node:child_process');
const esbuild=require('esbuild');
const express=require('express');
const request=require('supertest');
const React=require('react');
const serverRender=require('react-dom/server');
const {createRoot}=require('react-dom/client');
const {JSDOM}=require('jsdom');

if(!fs.existsSync('/.dockerenv'))throw Error('Docker-only evaluator');
const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const {modules,cases,phase}=input;
const ROLES=['logic','store','api','ui','css'];
if(!['public','holdout'].includes(phase)||!Array.isArray(cases)||cases.length!==3||
   !modules||ROLES.some(k=>typeof modules[k]!=='string'||modules[k].length>50000))
  throw Error('Invalid isolated evaluation request');

const output={phase,integrated:false,modules:{},checks:{},ui_markup:null,
  failure_reasons:[],completed_checks:0};
for(const role of ROLES)output.modules[role]={syntax_valid:false,passed:false,error:null};
function result(role,ok,reason){
  output.modules[role].passed=!!ok;
  output.modules[role].error=ok?null:String(reason||'Contract failed').slice(0,260);
  if(!ok)output.failure_reasons.push(role+': '+output.modules[role].error);
}
function equal(a,b){
  const norm=x=>JSON.stringify(x,(_k,v)=>v&&typeof v==='object'&&!Array.isArray(v)
    ?Object.fromEntries(Object.entries(v).sort()):v);
  return norm(a)===norm(b);
}
function loadFunction(source,name,role){
  const compiled=esbuild.transformSync(source+'\nmodule.exports='+name+';',{
    loader:'jsx',format:'cjs',target:'es2022'
  }).code;
  const module={exports:{}};
  const context=vm.createContext({
    module,exports:module.exports,React,console:{log(){},warn(){},error(){}},
    require(id) {
      if(id==='react')return React;
      if(id==='express')return express;
      if(id==='node:fs'||id==='fs')return fs;
      throw Error('Disallowed module '+id);
    }
  },{codeGeneration:{strings:false,wasm:false}});
  new vm.Script(compiled,{filename:'qwen-'+role+'.js'}).runInContext(context,{timeout:1100});
  if(typeof module.exports!=='function')throw Error('Missing '+name+' function');
  return module.exports;
}
function runPython(source,payload){
  const p=spawnSync('python3',['-I','-B','/opt/fullstack/py_worker031.py'],{
    input:JSON.stringify({source,payload}),encoding:'utf8',timeout:1750,
    maxBuffer:65536,env:{PYTHONDONTWRITEBYTECODE:'1',PYTHONHASHSEED:'0'}
  });
  if(p.error||p.status!==0)return {ok:false,error:p.error?.message||p.stderr.slice(-180)};
  try{return JSON.parse(p.stdout);}catch{return {ok:false,error:'Invalid Python output'};}
}
function trustedStore(){
  let records=[],next=1;
  return {
    list:()=>records.map(x=>({...x})),
    create:body=>{
      if(!body||typeof body.project!=='string'||!body.project||
         !Number.isInteger(body.minutes)||body.minutes<=0||
         !/^\d{4}-\d{2}-\d{2}$/.test(String(body.date||'')))
        throw Error('Invalid entry');
      const x={id:String(next++),project:body.project,minutes:body.minutes,
        date:body.date,note:typeof body.note==='string'?body.note:''};
      records.push(x);return {...x};
    },
    delete:id=>{const len=records.length;records=records.filter(x=>x.id!==String(id));return records.length<len;}
  };
}
async function mountOffline(uiSource){
  // Execute the generated App in a jsdom-backed realm where fetch always
  // fails, then assert the REQUIRED offline demo mode really renders the
  // fixed demo dataset. Same shared React instance; vm realm supplies the
  // browser-like globals. This is a behavioral DOM check, not a real browser
  // click test and not evidence about live network behavior.
  const dom=new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>',
    {url:'https://devmetrics.test/',pretendToBeVisual:true});
  const w=dom.window;
  const keys=['document','window','navigator','fetch','setTimeout','clearTimeout',
              'requestAnimationFrame','cancelAnimationFrame'];
  const saved={};for(const k of keys)saved[k]=global[k];
  const savedNavDesc=Object.getOwnPropertyDescriptor(global,'navigator');
  const realSetTimeout=global.setTimeout.bind(global);
  const realClearTimeout=global.clearTimeout.bind(global);
  const raf=(cb)=>realSetTimeout(cb,16);
  function install(key,value){
    if(key==='navigator'){
      try{Object.defineProperty(global,'navigator',{value,configurable:true,
        writable:true});}catch{ /* Node getter-only: leave as-is */ }
    }else global[key]=value;
  }
  const patches={
    document:w.document,window:w,navigator:w.navigator,
    fetch:()=>Promise.reject(new Error('offline')),
    setTimeout:(...a)=>realSetTimeout(...a),clearTimeout:(...a)=>realClearTimeout(...a),
    requestAnimationFrame:raf,cancelAnimationFrame:()=>{},
    IS_REACT_ACT_ENVIRONMENT:true
  };
  for(const k of Object.keys(patches))install(k,patches[k]);
  let root=null;
  async function settle(renderFn){
    // Development React exposes act(); the production build in this image does
    // not, so fall back to timed polling until the required offline mode shows.
    if(typeof React.act==='function'){
      await React.act(async()=>{renderFn();});
      for(let i=0;i<8;i++){
        await React.act(async()=>{await new Promise(r=>setTimeout(r,120));});
        if(/offline/i.test(w.document.body.innerHTML))return;
      }
    }else{
      renderFn();
      for(let i=0;i<12;i++){
        await new Promise(r=>setTimeout(r,150));
        if(/offline/i.test(w.document.body.innerHTML))return;
      }
    }
  }
  try{
    const compiled=esbuild.transformSync(uiSource+'\nmodule.exports=App;',{
      loader:'jsx',format:'cjs',target:'es2022'}).code;
    const module={exports:{}};
    const context=vm.createContext({
      module,exports:module.exports,React,
      console:{log(){},warn(){},error(){}},
      document:w.document,window:w,navigator:w.navigator,
      fetch:()=>Promise.reject(new Error('offline')),
      setTimeout:(...a)=>realSetTimeout(...a),
      clearTimeout:(...a)=>realClearTimeout(...a),
      require(id){ if(id==='react')return React; throw Error('Disallowed module '+id); }
    },{codeGeneration:{strings:false,wasm:false}});
    new vm.Script(compiled,{filename:'qwen-ui-mount.js'}).runInContext(context,{timeout:1500});
    const view=module.exports;
    if(typeof view!=='function')throw Error('App not exported');
    root=createRoot(w.document.getElementById('root'));
    await settle(()=>{root.render(React.createElement(view));});
    return w.document.body.innerHTML;
  } finally {
    try{if(root)root.unmount();}catch{}
    for(const k of keys){
      if(k==='navigator'){
        try{
          if(savedNavDesc)Object.defineProperty(global,'navigator',savedNavDesc);
          else delete global.navigator;
        }catch{}
      }else if(saved[k]===undefined)delete global[k];
      else global[k]=saved[k];
    }
    delete global.IS_REACT_ACT_ENVIRONMENT;
    dom.window.close();
  }
}
async function main(){
  let factory,view,makeStore;
  for(const [role,name] of [['store','createStore'],['api','createApp'],['ui','App']]){
    try {
      const fn=loadFunction(modules[role],name,role);
      output.modules[role].syntax_valid=true;
      if(role==='store')makeStore=fn;
      if(role==='api')factory=fn;
      if(role==='ui')view=fn;
    } catch(e) {
      try{esbuild.transformSync(modules[role],{loader:'jsx'});output.modules[role].syntax_valid=true;}catch{}
      // Include the first stack frame so 'Assignment to constant variable'
      // style errors carry a line:column location back into repair prompts.
      const frame=(e&&e.stack||'').split('\n')[1]||'';
      result(role,false,String(e)+(frame?' @ '+frame.trim().slice(0,90):''));
    }
  }
  try {
    const css=esbuild.transformSync(modules.css,{loader:'css'}).code;
    output.modules.css.syntax_valid=true;
    result('css',css.length>70&&css.includes('{'),'Missing substantial CSS rules');
  } catch(e){result('css',false,String(e));}

  let logicOk=true;
  for(const sample of cases){
    const got=runPython(modules.logic,sample.payload);
    if(got.syntax_valid)output.modules.logic.syntax_valid=true;
    // Distance-from-trivial signal: a real attempt returns a structured value
    // even when wrong; a `pass` stub returns null. Degrades nothing when the
    // module fully passes.
    if(got.ok&&got.value&&typeof got.value==='object'&&!Array.isArray(got.value))
      output.checks.logic_structured=true;
    if(!got.ok||!equal(got.value,sample.expected)){
      result('logic',false,got.error||('Expected '+JSON.stringify(sample.expected)+
        ', received '+JSON.stringify(got.value)));
      logicOk=false;break;
    }
  }
  if(logicOk)result('logic',true);

  if(makeStore){
    const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'devm031-'));
    const filename=path.join(tmp,'entries.json');
    try {
      const s=makeStore(filename);
      if(!Array.isArray(s.list())||s.list().length!==0)throw Error('Initial store must be empty');
      const created=s.create({project:'api-server',minutes:95,date:'2026-11-03',note:'routes'});
      if(!created||typeof created.id!=='string'||created.project!=='api-server'||
          created.minutes!==95)throw Error('Store creation contract');
      output.checks.create=true;
      let rejected=0;
      for(const bad of [{project:'',minutes:5,date:'2026-11-04'},
                        {project:'x',minutes:0,date:'2026-11-04'},
                        {project:'x',minutes:5,date:'2026/11/04'},
                        {project:'x',minutes:'5',date:'2026-11-04'}])
        try{s.create(bad);}catch(e){rejected++;}
      if(rejected!==4)throw Error('Store must reject all four invalid bodies');
      output.checks.store_validation=true;
      const reopened=makeStore(filename);
      if(!reopened.list().some(x=>x.id===created.id&&x.minutes===95))
        throw Error('On-disk persistence across store instances');
      output.checks.persistence=true;
      if(reopened.delete(created.id)!==true||makeStore(filename).list().length!==0)
        throw Error('Store deletion persistence');
      output.checks.store_delete=true;
      result('store',true);
    } catch(e){result('store',false,String(e));}
    finally{fs.rmSync(tmp,{recursive:true,force:true});}
  }
  if(factory){
    // Report EVERY failing route so repair prompts carry complete feedback.
    const apiFailures=[];
    const chk=async(name,fn)=>{try{await fn();output.checks[name]=true;}
      catch(e){apiFailures.push(name+' -> '+String(e&&e.message?e.message:e).slice(0,140));}};
    try {
      const s=trustedStore();
      const summaryFixture={total_minutes:0,by_project:{},by_day:{},
        active_projects:0,busiest_day:null};
      let app=null,id=null;
      await chk('app',()=>{app=factory(s,()=>summaryFixture);
        if(!app||typeof app.handle!=='function')throw Error('createApp must return Express app');});
      if(app){
        await chk('health',async()=>{const res=await request(app).get('/api/health').timeout(1200);
          if(res.status!==200||!equal(res.body,{ok:true}))throw Error('GET /api/health must return 200 {ok:true}');});
        await chk('get',async()=>{const res=await request(app).get('/api/entries').timeout(1200);
          if(res.status!==200||!equal(res.body,{entries:[]}))throw Error('GET /api/entries must return 200 {entries:store.list()}');});
        await chk('post',async()=>{const res=await request(app).post('/api/entries')
          .send({project:'api-server',minutes:6,date:'2026-11-04',note:'x'}).timeout(1200);
          if(res.status!==201||res.body.item?.project!=='api-server')
            throw Error('POST /api/entries must return 201 {item:store.create(req.body)}');
          id=res.body.item.id;});
        await chk('post_invalid',async()=>{const res=await request(app).post('/api/entries')
          .send({project:'',minutes:5,date:'2026-11-04'}).timeout(1200);
          if(res.status!==400||typeof res.body.error!=='string'||!res.body.error)
            throw Error('invalid POST must catch store.create throw and return 400 {error:string}');});
        await chk('delete',async()=>{const res=await request(app).delete('/api/entries/'+(id||'1')).timeout(1200);
          if(res.status!==200||res.body.deleted!==true)
            throw Error('DELETE /api/entries/:id must return 200 {deleted:store.delete(id)}');});
        await chk('projects',async()=>{s.create({project:'beta',minutes:3,date:'2026-11-04'});
          s.create({project:'alpha',minutes:4,date:'2026-11-04'});
          const res=await request(app).get('/api/projects').timeout(1200);
          if(res.status!==200||!equal(res.body,{projects:['alpha','beta']}))
            throw Error('GET /api/projects must return 200 {projects:sorted distinct project names}');});
        await chk('summary',async()=>{const res=await request(app).get('/api/summary').timeout(1200);
          if(res.status!==200||!equal(res.body,summaryFixture))
            throw Error('GET /api/summary body must be exactly processor({entries:store.list()})');});
      }
      result('api',apiFailures.length===0,apiFailures.join(' | ')||undefined);
    } catch(e){result('api',false,String(e));}
  }
  if(view){
    try {
      const code=modules.ui;
      // Report EVERY missing wiring pattern so repair prompts carry
      // complete feedback in one round.
      const missing=[];
      for(const [pattern,name] of [
        [/React\.useState|\buseState\s*\(/,'state hook (React.useState)'],
        [/React\.useEffect|\buseEffect\s*\(/,'load effect (React.useEffect)'],
        [/\bfetch\s*\(/,'API fetch'],
        [/\/api\/entries/,'entries endpoint /api/entries'],
        [/\/api\/summary/,'summary endpoint /api/summary'],
        [/onChange\s*=/,'controlled input onChange='],
        [/onSubmit\s*=|onClick\s*=/,'working form onSubmit= or button onClick='],
        [/\bDELETE\b/,'DELETE request'],
        [/\bPOST\b/,'POST request'],
        [/offline/i,'offline badge word'],
        [/api-server/,'demo dataset entry api-server'],
        [/mobile-ui/,'demo dataset entry mobile-ui'],
        [/docs/,'demo dataset entry docs'],
        [/\bfilter\s*\(/,'project filter']
      ])if(!pattern.test(code))missing.push(name);
      if(missing.length)throw Error('UI lacks: '+missing.join(', '));
      output.checks.ui_wiring=true;
      // Behavioral proof in a disposable jsdom realm (not a real browser click test).
      const markup=await mountOffline(modules.ui);
      output.ui_markup=markup.slice(0,40000);
      if(!/offline/i.test(markup))throw Error('offline badge did not render');
      for(const name of ['api-server','mobile-ui','docs'])
        if(!markup.includes(name))throw Error('offline demo entry missing: '+name);
      if(!markup.includes('295'))throw Error('offline summary total 295 missing');
      if(!/<input\b/i.test(markup)||!/<button\b/i.test(markup))
        throw Error('offline mode needs visible inputs and buttons');
      output.checks.ui_offline=true;
      result('ui',true);
    } catch(e){result('ui',false,String(e));}
  }
  if(factory&&makeStore&&output.modules.logic.passed){
    const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'integrated031-'));
    try{
      const s=makeStore(path.join(tmp,'db.json'));
      const app=await Promise.resolve(factory(s,payload=>{
        const value=runPython(modules.logic,payload);
        if(!value.ok)throw Error(value.error);return value.value;
      }));
      await request(app).post('/api/entries').send({project:'core',minutes:45,date:'2026-11-01'}).timeout(1600);
      await request(app).post('/api/entries').send({project:'core',minutes:30,date:'2026-11-02'}).timeout(1600);
      const res=await request(app).get('/api/summary').timeout(1600);
      if(res.status!==200||!equal(res.body,{total_minutes:75,by_project:{core:75},
          by_day:{'2026-11-01':45,'2026-11-02':30},active_projects:1,busiest_day:'2026-11-01'}))
        throw Error('Real model store/API/Python end-to-end mismatch');
      output.checks.integration=true;
    }catch(e){output.failure_reasons.push('integration: '+String(e).slice(0,200));}
    finally{fs.rmSync(tmp,{recursive:true,force:true});}
  }
  output.integrated=ROLES.every(x=>output.modules[x].passed)&&output.checks.integration===true;
  output.completed_checks=Object.values(output.checks).filter(Boolean).length+
    ROLES.filter(x=>output.modules[x].passed).length;
  fs.writeFileSync(process.argv[3],JSON.stringify(output,null,2)+'\n');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
