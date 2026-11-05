'use strict';
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const express=require('express');
const {createStore}=require('./store.js');
const {createApp}=require('./routes.js');
const db=process.env.POCKETLEDGER_DB || path.join(__dirname,'../data/expenses.json');
require('node:fs').mkdirSync(path.dirname(db),{recursive:true});
const processor=payload=>{
 const result=spawnSync('python3',['-I','-B',path.join(__dirname,'../backend/bridge.py')],{
  input:JSON.stringify(payload),encoding:'utf8',timeout:3000,maxBuffer:1024*1024
 });
 if(result.error || result.status!==0)throw new Error(result.error?.message || result.stderr);
 return JSON.parse(result.stdout);
};
const app=createApp(createStore(db),processor);
app.use(express.static(path.join(__dirname,'../public')));
const port=Number(process.env.PORT || 3000);
app.listen(port,'0.0.0.0',()=>console.log('PocketLedger running at http://localhost:'+port));
