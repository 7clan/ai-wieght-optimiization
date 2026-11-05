// Runs inside nonroot, read-only, network-disabled Docker only.
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const request=require('supertest');

const APP='/opt/pocketledger';
const {createStore}=require(APP+'/server/store.js');
const {createApp}=require(APP+'/server/routes.js');
async function main(){
 const file='/tmp/session029-expenses.json';
 const store=createStore(file);
 const processor=(payload)=>{
   const result=spawnSync('python3',['-I','-B',APP+'/backend/bridge.py'],{
      input:JSON.stringify(payload),encoding:'utf8',timeout:2500
   });
   assert.equal(result.status,0,result.stderr);
   return JSON.parse(result.stdout);
 };
 const app=createApp(store,processor);
 assert.equal(fs.existsSync(APP+'/public/app.js'),true,'missing React bundle');
 assert.ok(fs.statSync(APP+'/public/app.js').size>10000,'suspiciously empty bundle');
 assert.deepEqual((await request(app).get('/api/expenses')).body,{expenses:[]});
 let r=await request(app).post('/api/expenses')
   .send({description:'Sandwich',amount_cents:875,category:'food'});
 assert.equal(r.status,201);
 const id=r.body.expense.id;
 assert.equal(typeof id,'string');
 assert.equal(createStore(file).list().length,1,'persistence after re-open');
 assert.deepEqual((await request(app).get('/api/summary')).body,
   {count:1,total_cents:875,by_category:{food:875}});
 r=await request(app).post('/api/expenses')
   .send({description:'Wrong',amount_cents:-4,category:'travel'});
 assert.equal(r.status,400,'bad input accepted');
 assert.deepEqual((await request(app).delete('/api/expenses/'+id)).body,{deleted:true});
 assert.equal(createStore(file).list().length,0,'delete not persisted');
 console.log('PASS: bundled React, Express CRUD, Python summary and JSON persistence');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
