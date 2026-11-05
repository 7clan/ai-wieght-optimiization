// Execute untrusted Qwen-generated Python, Express and React ONLY inside Docker.
const fs = require('node:fs');
const vm = require('node:vm');
const {spawnSync} = require('node:child_process');
const esbuild = require('esbuild');
const express = require('express');
const supertest = require('supertest');
const React = require('react');
const ReactDOMServer = require('react-dom/server');

if (!fs.existsSync('/.dockerenv')) throw Error('Docker required');
if (process.argv.length !== 4) throw Error('input/output argument required');
const {modules, cases, phase} = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
if (!['public','holdout'].includes(phase) || !Array.isArray(cases) ||
    cases.length !== 3 || !modules ||
    ['logic','api','ui','css'].some(name => typeof modules[name] !== 'string' || modules[name].length > 40000)) {
  throw Error('Malformed evaluator request');
}

function loadJs(source, symbol, role) {
  const compiled = esbuild.transformSync(`${source}\nmodule.exports=${symbol};`, {
    loader:'jsx', format:'cjs', target:'es2022',
    jsx:'transform', jsxFactory:'React.createElement',jsxFragment:'React.Fragment'
  }).code;
  const module={exports:{}};
  const context=vm.createContext({module,exports:module.exports,React,
    require(id){
      if(id==='react')return React;
      if(id==='express')return express;
      throw Error('Blocked dependency '+id);
    }, console:{log(){},warn(){},error(){}}});
  new vm.Script(compiled,{filename:`generated-${role}.js`}).runInContext(context,{timeout:1400});
  if(typeof module.exports!=='function')throw Error(`Missing callable ${symbol}`);
  return module.exports;
}

function runPython(source,payload) {
  const result=spawnSync('python3',['-I','-B','/opt/fullstack/py_worker021.py'],{
    input:JSON.stringify({source,payload}),encoding:'utf8',timeout:1900,
    maxBuffer:65536,env:{PYTHONDONTWRITEBYTECODE:'1',PYTHONHASHSEED:'0'}
  });
  if(result.error || result.status!==0)return {ok:false,syntax_valid:true,
    error:result.error?.message||result.stderr.slice(-200)};
  try{return JSON.parse(result.stdout);}catch{return {ok:false,syntax_valid:true,error:'Malformed Python output'};}
}

function storeFactory(){
  let tasks=[];let next=1;
  return {
    list(){return tasks.map(t=>({...t}));},
    create(body){if(!body || typeof body.title!=='string' || !body.title.trim())
      throw Error('title required');
      const task={id:String(next++),title:body.title.trim(),
        priority:body.priority||'medium',done:false};tasks.push(task);return {...task};},
    update(id,body){const task=tasks.find(t=>t.id===String(id));if(!task)return null;
      Object.assign(task,body);return {...task};},
    delete(id){const count=tasks.length;tasks=tasks.filter(t=>t.id!==String(id));
      return tasks.length<count;}
  };
}

const output={phase,modules:{},integrated:false,checks:{},ui_markup:null,
  failure_reasons:[],completed_checks:0};
for(const role of ['logic','api','ui','css'])output.modules[role]={syntax_valid:false,passed:false,error:null};
function resultFor(role,passed,error=null){
  output.modules[role].passed=Boolean(passed);
  output.modules[role].error=passed?null:String(error||'Contract failed').slice(0,300);
  if(!passed)output.failure_reasons.push(`${role}: ${output.modules[role].error}`);
}
function equal(a,b){
  const canonical=x=>JSON.stringify(x,(_,v)=>v && typeof v==='object' &&
    !Array.isArray(v) ? Object.fromEntries(Object.entries(v).sort()) : v);
  return canonical(a)===canonical(b);
}

async function evaluate(){
  let factory, view;
  for(const role of ['api','ui']){
    try {
      if(role==='api')factory=loadJs(modules.api,'createApp','api');
      else view=loadJs(modules.ui,'App','ui');
      output.modules[role].syntax_valid=true;
    }catch(e){
      try{esbuild.transformSync(modules[role],{loader:'jsx'});
        output.modules[role].syntax_valid=true;}catch{ /* invalid syntax */ }
      resultFor(role,false,String(e));
    }
  }
  try{
    const compiled=esbuild.transformSync(modules.css,{loader:'css'}).code;
    output.modules.css.syntax_valid=true;
    resultFor('css',compiled.length>=40 && compiled.includes('{'),
      'CSS absent or too short');
  }catch(e){resultFor('css',false,String(e));}

  let logicGood=true;
  for(const example of cases){
    const found=runPython(modules.logic,example.payload);
    if(found.syntax_valid)output.modules.logic.syntax_valid=true;
    if(!found.ok || !equal(found.value,example.expected)){
      logicGood=false;
      resultFor('logic',false,found.error||`expected ${JSON.stringify(example.expected)}, got ${JSON.stringify(found.value)}`);
      break;
    }
  }
  if(logicGood)resultFor('logic',true);

  if(factory){
    try{
      const store=storeFactory();
      const app=await Promise.resolve(factory(store,()=>({total:0,completed:0,remaining:0})));
      if(!app || typeof app.handle!=='function')throw Error('createApp returned no Express app');
      const empty=await supertest(app).get('/api/tasks').timeout(1600);
      if(empty.status!==200 || !equal(empty.body,{tasks:[]}))throw Error('GET /api/tasks contract');
      output.checks.get=true;
      const created=await supertest(app).post('/api/tasks').send({title:'Ship a feature',priority:'high'}).timeout(1600);
      if(created.status!==201 || created.body?.task?.title!=='Ship a feature')throw Error('POST /api/tasks contract');
      output.checks.post=true;
      const id=String(created.body.task.id);
      const patched=await supertest(app).patch(`/api/tasks/${id}`).send({done:true}).timeout(1600);
      if(patched.status!==200 || patched.body?.task?.done!==true)throw Error('PATCH /api/tasks contract');
      output.checks.patch=true;
      const summary=await supertest(app).get('/api/summary').timeout(1600);
      if(summary.status!==200 || !equal(summary.body,{total:0,completed:0,remaining:0}))
        throw Error('GET /api/summary processor integration contract');
      output.checks.summary=true;
      const deleted=await supertest(app).delete(`/api/tasks/${id}`).timeout(1600);
      if(deleted.status!==200 || deleted.body?.deleted!==true)throw Error('DELETE /api/tasks contract');
      output.checks.delete=true;
      resultFor('api',true);
    }catch(e){resultFor('api',false,String(e));}
  }
  if(view){
    try{
      const markup=ReactDOMServer.renderToStaticMarkup(React.createElement(view));
      output.ui_markup=markup.slice(0,40000);
      if(!/task/i.test(markup) || !/<button\b/.test(markup) || !/<input\b/.test(markup))
        throw Error('Rendered UI must contain a task label, button and input');
      resultFor('ui',true);
    }catch(e){resultFor('ui',false,String(e));}
  }
  if(output.modules.api.passed && output.modules.logic.passed){
    try{
      const store=storeFactory();
      store.create({title:'Integrated',priority:'low'});
      store.update('1',{done:true});
      const app=await Promise.resolve(factory(store,payload=>{
        const parsed=runPython(modules.logic,payload);
        if(!parsed.ok)throw Error(parsed.error);
        return parsed.value;
      }));
      const r=await supertest(app).get('/api/summary').timeout(1600);
      if(r.status!==200 || !equal(r.body,{total:1,completed:1,remaining:0}))
        throw Error('Real Python→Express stats mismatch');
      output.checks.integrated_api=true;
    }catch(e){output.failure_reasons.push('integration: '+String(e).slice(0,180));}
  }
  output.integrated=Object.values(output.modules).every(x=>x.passed) &&
    output.checks.integrated_api===true;
  output.completed_checks=Object.values(output.checks).filter(Boolean).length+
    Number(output.modules.logic.passed)+Number(output.modules.ui.passed)+
    Number(output.modules.css.passed);
  fs.writeFileSync(process.argv[3],JSON.stringify(output,null,2)+'\n');
}

evaluate().catch(error=>{console.error(error);process.exitCode=1;});
