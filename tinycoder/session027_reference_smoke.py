"""Positive-control evaluator preflight. These fixtures never enter Qwen prompts."""
from __future__ import annotations

from .session027 import evaluate
from .session027_contract import PUBLIC

GOOD={
    "logic":"""def transform(payload):
    values={}
    items=payload.get('expenses',[])
    for item in items:
        kind=item['category']
        values[kind]=values.get(kind,0)+item['amount_cents']
    return {'count':len(items),'total_cents':sum(item['amount_cents'] for item in items),
            'by_category':values}
""",
    "store":"""const fs=require('node:fs');
function createStore(filePath){
 function load(){try{return JSON.parse(fs.readFileSync(filePath,'utf8'))}catch{return []}}
 function save(rows){fs.writeFileSync(filePath,JSON.stringify(rows))}
 return {
  list(){return load()},
  create(body){
   if(!body.description||!Number.isInteger(body.amount_cents)||body.amount_cents<=0)
     throw Error('Invalid');
   const x={...body,id:String(Date.now())+String(Math.random())};
   const rows=load();rows.push(x);save(rows);return x;
  },
  delete(id){const rows=load();const rest=rows.filter(x=>x.id!==String(id));
   save(rest);return rest.length<rows.length;}
 };
}
""",
    "api":"""const express=require('express');
function createApp(store,processor){
 const app=express();app.use(express.json());
 app.get('/api/expenses',(req,res)=>res.json({expenses:store.list()}));
 app.post('/api/expenses',(req,res)=>res.status(201).json({expense:store.create(req.body)}));
 app.delete('/api/expenses/:id',(req,res)=>res.json({deleted:store.delete(req.params.id)}));
 app.get('/api/summary',(req,res)=>res.json(processor({expenses:store.list()})));
 return app;
}
""",
    "ui":"""const React=require('react');
function App(){
 return React.createElement('main',null,React.createElement('h1',null,'PocketLedger expenses'),
  React.createElement('input',{placeholder:'Expense description'}),
  React.createElement('button',null,'Add expense'));
}
""",
    "css":"body{margin:0;background:#fafbfe;color:#202840;font-family:sans-serif;padding:2rem}button{padding:1rem;background:blue;color:white}"
}


def main():
    found=evaluate(GOOD,PUBLIC,"public")
    if not found["integrated"]:
        raise RuntimeError("Evaluator positive-control failed: "+str(found["failure_reasons"]))
    print("PASS: independent five-module trusted evaluator control",flush=True)


if __name__=="__main__":
    main()
