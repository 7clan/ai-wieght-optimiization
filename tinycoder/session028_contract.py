"""Session028: mentor demonstrations from unrelated tasks, never target answers."""
from __future__ import annotations

import hashlib
import json

from .session027_contract import ROLES, SPEC

# These values are not in the Session027 run or any student-facing prompt.
def fresh_holdout():
    return [
        {"payload":{"expenses":[]},"expected":{"count":0,"total_cents":0,"by_category":{}}},
        {"payload":{"expenses":[{"amount_cents":17,"category":"food"},
                                {"amount_cents":331,"category":"travel"},
                                {"amount_cents":52,"category":"food"}]},
         "expected":{"count":3,"total_cents":400,"by_category":{"food":69,"travel":331}}},
        {"payload":{"expenses":[{"amount_cents":46,"category":"other"},
                                {"amount_cents":7,"category":"travel"},
                                {"amount_cents":2,"category":"other"},
                                {"amount_cents":44,"category":"food"},
                                {"amount_cents":1,"category":"food"}]},
         "expected":{"count":5,"total_cents":100,
                     "by_category":{"other":48,"travel":7,"food":45}}}
    ]


ROLE_GOAL={
 "logic":"""Implement backend/logic.py transform(payload). Input is a dict with
  key 'expenses' containing a list of dicts. Return dict keys count,
  total_cents and by_category. Count items. Sum amount_cents across ALL categories,
  grouping by each item's category. For no expenses return zero counts and {}.
  Use Python only. Complete the function, do not repeat this comment.""",
 "store":"""Implement server/store.js createStore(filePath). Return methods
  list(), create(body), delete(id). On a NEW file path list() must return [].
  On each create or delete persist the complete JSON array using fs.writeFileSync.
  A new createStore(filePath) instance must load the prior state. Create returns
  an expense with a string id. Reject empty description and invalid/nonpositive
  integer amount_cents with Error. Delete returns boolean. Complete and close
  the function. No other packages.""",
 "api":"""Implement server/routes.js createApp(store, processor). All handlers
  MUST be defined INSIDE createApp, and it MUST return the Express app.
  Use express.json(); GET /api/expenses -> {expenses:store.list()};
  POST /api/expenses -> status 201 {expense:store.create(req.body)};
  DELETE /api/expenses/:id -> {deleted:store.delete(req.params.id)};
  GET /api/summary -> processor({expenses:store.list()}) directly as JSON.
  Do NOT app.listen() and do NOT call req/res outside route handlers.
  Complete the function, do not repeat this comment.""",
 "ui":"""Implement client/App.jsx function App() with React hooks and JSX.
  useState for expenses, description, amount and summary; useEffect to fetch
  GET /api/expenses and GET /api/summary. Provide an editable description input
  and amount input with onChange, an Add expense submit/click handler sending
  POST /api/expenses JSON, and Delete buttons sending DELETE /api/expenses/:id.
  Refresh expenses and summary after edits; render a category summary, a list
  and title PocketLedger. Complete the function, export with module.exports.
  No extra libraries. Do not repeat this comment."""
}

LESSONS={
 "logic":"""# TEACHER'S WORKED EXAMPLE from an UNRELATED domain:
# This music algorithm receives a dict, extracts its LIST, then groups records.
def summarize_songs(payload):
    songs = payload.get('songs', [])
    by_artist = {}
    for song in songs:
        who = song['artist']
        by_artist[who] = by_artist.get(who, 0) + song['seconds']
    return {'count': len(songs), 'seconds': sum(s['seconds'] for s in songs),
            'by_artist': by_artist}
# Notice: do NOT iterate payload dictionary keys; do NOT filter one group.
""",
 "store":"""// TEACHER'S WORKED EXAMPLE from an UNRELATED domain: persisted bookmarks.
const fs = require('node:fs');
function openBookmarks(filename) {
  function read() {
    if (!fs.existsSync(filename)) return [];
    return JSON.parse(fs.readFileSync(filename, 'utf8'));
  }
  function write(items) { fs.writeFileSync(filename, JSON.stringify(items)); }
  return {
    list: () => read(),
    add: (bookmark) => { const all=read(); all.push(bookmark); write(all); return bookmark; },
    remove: (url) => { const before=read(); const after=before.filter(x=>x.url!==url);
                       write(after); return before.length!==after.length; }
  };
}
// Notice: on initial access avoid ENOENT; after EACH mutation write the JSON array.
""",
 "api":"""// TEACHER'S WORKED EXAMPLE from an UNRELATED domain: reading-library API.
const express = require('express');
function makeLibrary(books) {
  const server = express();
  server.use(express.json());
  server.get('/api/books', (req,res) => res.status(200).json({books:books.list()}));
  server.post('/api/books', (req,res) => res.status(201).json({book:books.add(req.body)}));
  server.delete('/api/books/:id', (req,res) => res.json({deleted:books.remove(req.params.id)}));
  return server;
}
// Notice: every server.route() is INSIDE the factory, then return server.
""",
 "ui":"""// TEACHER'S WORKED EXAMPLE from an UNRELATED domain: editable reading list.
const React = require('react');
function ReadingListDemo() {
  const [books,setBooks]=React.useState([]);
  const [title,setTitle]=React.useState('');
  async function refresh(){const r=await fetch('/api/books');const data=await r.json();
    setBooks(data.books||[]);}
  React.useEffect(()=>{refresh();},[]);
  async function add(e){e.preventDefault();await fetch('/api/books',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({title})});
    setTitle('');await refresh();}
  async function remove(id){await fetch('/api/books/'+id,{method:'DELETE'});await refresh();}
  return <main><h1>Reading list</h1><form onSubmit={add}>
    <input value={title} onChange={e=>setTitle(e.target.value)}/>
    <button type="submit">Add</button></form>
    <ul>{books.map(book=><li key={book.id}>{book.title}
    <button onClick={()=>remove(book.id)}>Remove</button></li>)}</ul></main>;
}
// Notice: data is loaded with useEffect; events call POST or DELETE then refresh.
"""
}

PREFIX={
 "logic":"def transform(payload):\n",
 "store":"const fs = require('node:fs');\nfunction createStore(filePath) {\n",
 "api":"const express = require('express');\nfunction createApp(store, processor) {\n",
 "ui":"const React = require('react');\nfunction App() {\n"
}


def prompt(role, prior_error:str, level:int):
    if role not in PREFIX:
        raise ValueError(role)
    comment="# " if role=="logic" else "// "
    intro=(comment+"POCKETLEDGER TASK: "+ROLE_GOAL[role].replace("\n", "\n"+comment)+"\n")
    err=(comment+"LAST STUDENT ERROR: "+" ".join(str(prior_error).split())[:150]+"\n")
    reminder=(comment+"REPAIR CHECKLIST: Use all response fields. Close all blocks.\n") if level>=2 else ""
    # Keep the worked example AND a targeted contract, but no target code solution.
    return LESSONS[role]+"\n"+intro+err+reminder+PREFIX[role]


def fingerprint():
    return hashlib.sha256(json.dumps({"spec":SPEC,"goals":ROLE_GOAL,
        "lessons":LESSONS},sort_keys=True).encode()).hexdigest()
