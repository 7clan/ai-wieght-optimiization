// All Qwen-produced source executes exclusively in unprivileged, restricted Docker.
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
  const p=spawnSync('python3',['-I','-B','/opt/fullstack/py_worker021.py'],{
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
      if(!body||!body.description||!Number.isInteger(body.amount_cents)||body.amount_cents<=0)
        throw Error('Invalid expense');
      const x={id:String(next++),description:body.description,
        amount_cents:body.amount_cents,category:body.category||'other'};
      records.push(x);return {...x};
    },
    delete:id=>{const len=records.length;records=records.filter(x=>x.id!==String(id));return records.length<len;}
  };
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
      result(role,false,String(e));
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
    if(!got.ok||!equal(got.value,sample.expected)){
      result('logic',false,got.error||('Expected '+JSON.stringify(sample.expected)+
        ', received '+JSON.stringify(got.value)));
      logicOk=false;break;
    }
  }
  if(logicOk)result('logic',true);

  if(makeStore){
    const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'pocket027-'));
    const filename=path.join(tmp,'expenses.json');
    try {
      const s=makeStore(filename);
      if(!Array.isArray(s.list())||s.list().length!==0)throw Error('Initial store must be empty');
      const created=s.create({description:'Coffee',amount_cents:425,category:'food'});
      if(!created||typeof created.id!=='string'||created.description!=='Coffee')
        throw Error('Store creation contract');
      const reopened=makeStore(filename);
      if(!reopened.list().some(x=>x.id===created.id&&x.amount_cents===425))
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
    try {
      const s=trustedStore();
      const summaryFixture={count:0,total_cents:0,by_category:{}};
      const app=await Promise.resolve(factory(s,()=>summaryFixture));
      if(!app||typeof app.handle!=='function')throw Error('createApp must return Express app');
      let res=await request(app).get('/api/expenses').timeout(1200);
      if(res.status!==200||!equal(res.body,{expenses:[]}))throw Error('GET /api/expenses envelope');
      output.checks.get=true;
      res=await request(app).post('/api/expenses').send({description:'Coffee',amount_cents:425,category:'food'}).timeout(1200);
      if(res.status!==201||res.body.expense?.description!=='Coffee')throw Error('POST envelope/status');
      output.checks.post=true;
      const id=res.body.expense.id;
      res=await request(app).get('/api/summary').timeout(1200);
      if(res.status!==200||!equal(res.body,summaryFixture))throw Error('GET summary processor contract');
      output.checks.summary=true;
      res=await request(app).delete('/api/expenses/'+id).timeout(1200);
      if(res.status!==200||res.body.deleted!==true)throw Error('DELETE response or store method');
      output.checks.delete=true;
      result('api',true);
    } catch(e){result('api',false,String(e));}
  }
  if(view){
    try {
      const html=serverRender.renderToStaticMarkup(React.createElement(view));
      output.ui_markup=html.slice(0,40000);
      if(!/pocketledger|expense/i.test(html)||!/<input\b/.test(html)||
          !/<button\b/.test(html))throw Error('UI needs expense heading, input and button');
      result('ui',true);
    } catch(e){result('ui',false,String(e));}
  }
  if(factory&&makeStore&&output.modules.logic.passed){
    const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'integrated027-'));
    try{
      const s=makeStore(path.join(tmp,'db.json'));
      s.create({description:'Bus',amount_cents:220,category:'travel'});
      s.create({description:'Meal',amount_cents:180,category:'food'});
      const app=await Promise.resolve(factory(s,payload=>{
        const value=runPython(modules.logic,payload);
        if(!value.ok)throw Error(value.error);return value.value;
      }));
      const res=await request(app).get('/api/summary').timeout(1600);
      if(res.status!==200||!equal(res.body,{count:2,total_cents:400,by_category:{travel:220,food:180}}))
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
