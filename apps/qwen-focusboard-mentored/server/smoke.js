/* Test actual generated Python+Express+React artifacts, not only a mock. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const request=require('supertest');
const app=require('./runtime.js');

async function main(){
  const base=await request(app).get('/api/tasks');
  assert.equal(base.status,200);
  assert.ok(Array.isArray(base.body.tasks));
  const post=await request(app).post('/api/tasks').send({title:'End-to-end smoke',priority:'high'});
  assert.equal(post.status,201);
  const id=post.body.task.id;
  assert.ok(id);
  const patch=await request(app).patch('/api/tasks/'+id).send({done:true});
  assert.equal(patch.status,200);
  assert.equal(patch.body.task.done,true);
  const stats=await request(app).get('/api/summary');
  assert.equal(stats.status,200);
  assert.ok(stats.body.completed>=1);
  const del=await request(app).delete('/api/tasks/'+id);
  assert.equal(del.status,200);
  assert.equal(del.body.deleted,true);
  assert.equal((await request(app).get('/')).status,200);
  assert.equal((await request(app).get('/assets/app.js')).status,200);
  assert.equal((await request(app).get('/style.css')).status,200);
  assert.ok(fs.statSync('/data/focusboard.sqlite3').size>0);
  console.log('Actual model-assisted full-stack HTTP/SQLite/screen bundle smoke PASS');
}
main().catch(error=>{console.error(error);process.exitCode=1});
