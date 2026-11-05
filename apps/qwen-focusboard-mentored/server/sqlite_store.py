"""Trusted SQLite persistence and Qwen Python transform process boundary."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid

DB=Path(os.environ.get('DB_PATH','/data/focusboard.sqlite3'))
SCRIPT=Path(__file__).resolve().parent.parent/'generated'/'backend'/'logic.py'


def connect():
    DB.parent.mkdir(parents=True,exist_ok=True)
    connection=sqlite3.connect(str(DB),timeout=2.0)
    connection.row_factory=sqlite3.Row
    connection.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, priority TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)''')
    connection.commit()
    return connection


def item(row):
    return {'id':row['id'],'title':row['title'],'priority':row['priority'],
            'done':bool(row['done'])}


def dispatch(request):
    action=request['action']
    with connect() as db:
        if action=='list':
            return [item(row) for row in db.execute('SELECT * FROM tasks ORDER BY rowid DESC')]
        if action=='create':
            body=request.get('body') or {}
            title=str(body.get('title') or '').strip()
            priority=body.get('priority') or 'medium'
            if not title or len(title)>300 or priority not in ('low','medium','high'):
                raise ValueError('Title or priority is invalid')
            ident=uuid.uuid4().hex
            db.execute('INSERT INTO tasks VALUES(?,?,?,?)',(ident,title,priority,0))
            db.commit()
            return item(db.execute('SELECT * FROM tasks WHERE id=?',(ident,)).fetchone())
        if action=='update':
            ident=str(request.get('id',''))
            body=request.get('body') or {}
            old=db.execute('SELECT * FROM tasks WHERE id=?',(ident,)).fetchone()
            if old is None:return None
            updated=item(old)
            for key in ('title','priority','done'):
                if key in body:updated[key]=body[key]
            updated['title']=str(updated['title']).strip()
            if not updated['title'] or len(updated['title'])>300 or updated['priority'] not in ('low','medium','high'):
                raise ValueError('Invalid task update')
            db.execute('UPDATE tasks SET title=?,priority=?,done=? WHERE id=?',
                       (updated['title'],updated['priority'],int(bool(updated['done'])),ident))
            db.commit()
            return item(db.execute('SELECT * FROM tasks WHERE id=?',(ident,)).fetchone())
        if action=='delete':
            result=db.execute('DELETE FROM tasks WHERE id=?',(str(request.get('id','')),))
            db.commit()
            return bool(result.rowcount)
        if action=='summary':
            spec=importlib.util.spec_from_file_location('verified_qwen_logic',SCRIPT)
            if spec is None or spec.loader is None:raise RuntimeError('Generated statistics module missing')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.transform(request['payload'])
    raise ValueError('Unsupported action')


def main():
    try:
        request=json.load(sys.stdin)
        result={'ok':True,'value':dispatch(request)}
    except Exception as exc:
        result={'ok':False,'error':type(exc).__name__+': '+str(exc)}
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':main()
