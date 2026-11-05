"""Trusted positive control proves the stricter evaluator can accept correct code."""
from __future__ import annotations

from .session027_contract import PUBLIC
from .session027_reference_smoke import GOOD
from .session028 import evaluate


def main():
    fixture=dict(GOOD)
    fixture["ui"]="""const React=require('react');
function App(){
 const [items,setItems]=React.useState([]);
 const [description,setDescription]=React.useState('');
 const [amount,setAmount]=React.useState('');
 const [summary,setSummary]=React.useState({});
 async function reload(){
  const a=await fetch('/api/expenses');setItems((await a.json()).expenses);
  const b=await fetch('/api/summary');setSummary(await b.json());
 }
 React.useEffect(()=>{reload();},[]);
 async function add(e){e.preventDefault();await fetch('/api/expenses',{method:'POST',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({description,amount_cents:Number(amount),category:'other'})});
  await reload();
 }
 async function remove(id){await fetch('/api/expenses/'+id,{method:'DELETE'});await reload();}
 return <main><h1>PocketLedger</h1><form onSubmit={add}>
  <input value={description} onChange={e=>setDescription(e.target.value)}/>
  <input type="number" value={amount} onChange={e=>setAmount(e.target.value)}/>
  <button type="submit">Add Expense</button></form>
  <ul>{items.map(x=><li key={x.id}>{x.description}
    <button onClick={()=>remove(x.id)}>Delete</button></li>)}</ul>
  <div>{summary.total_cents}</div></main>;
}
"""
    report=evaluate(fixture,PUBLIC,"public")
    if not report["integrated"] or not report["checks"].get("ui_wiring"):
        raise RuntimeError("Session028 reference failed: "+str(report["failure_reasons"]))
    print("PASS: stricter functional-contract positive control",flush=True)


if __name__=="__main__":
    main()
