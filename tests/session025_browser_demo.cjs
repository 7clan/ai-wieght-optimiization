'use strict';
/* Trusted static preview event simulation; does not execute model-generated JS. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');

const html=fs.readFileSync(
  path.join(__dirname,'../docs/previews/session025/interactive.html'),'utf8'
);
function boot(seed){
  const errors=[];
  const dom=new JSDOM(html,{
    url:'https://demo.example.test/',
    runScripts:'dangerously',
    pretendToBeVisual:true,
    beforeParse(window) {
      if(seed)window.localStorage.setItem('qwen-focusboard-session025-demo',seed);
      window.addEventListener('error',e=>errors.push(e.message));
    }
  });
  assert.deepEqual(errors,[]);
  return dom;
}
function text(document,id){return document.getElementById(id).textContent.trim();}
function add(dom,title,priority){
  const d=dom.window.document;
  d.getElementById('new-title').value=title;
  d.getElementById('new-priority').value=priority;
  d.getElementById('create-form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));
}
const dom=boot();
const d=dom.window.document;
assert.equal(text(d,'total'),'0');
add(dom,'Write API tests','high');
assert.equal(text(d,'total'),'1');
assert.equal(text(d,'remaining'),'1');
assert.equal(d.querySelectorAll('.task-row').length,1);
assert.match(d.querySelector('.task-row').textContent,/Write API tests/);
assert.match(d.querySelector('.priority').className,/high/);
d.querySelector('.task-row button').click();
assert.equal(text(d,'completed'),'1');
assert.equal(text(d,'remaining'),'0');
const persisted=dom.window.localStorage.getItem('qwen-focusboard-session025-demo');
assert.ok(persisted);
const resumed=boot(persisted);
assert.equal(text(resumed.window.document,'completed'),'1');
const search=resumed.window.document.getElementById('search');
search.value='not a matching task';
search.dispatchEvent(new resumed.window.Event('input',{bubbles:true}));
assert.equal(resumed.window.document.querySelectorAll('.task-row').length,0);
search.value='';
search.dispatchEvent(new resumed.window.Event('input',{bubbles:true}));
assert.equal(resumed.window.document.querySelectorAll('.task-row').length,1);
resumed.window.document.querySelector('.task-row button:last-child').click();
assert.equal(text(resumed.window.document,'total'),'0');
assert.equal(resumed.window.document.querySelectorAll('.task-row').length,0);
console.log('PASS: add, status, persistence, search and delete in interactive preview');
