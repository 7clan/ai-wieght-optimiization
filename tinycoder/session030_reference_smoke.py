"""Positive control built from trusted old-domain code; never enters model prompts."""
from __future__ import annotations

import json
from pathlib import Path

from .session029_teacher import STORE, API, UI
from .session030 import evaluate
from .session030_contract import PUBLIC


def re_domain(code:str)->str:
    for old,new in [
        ("PocketLedger","ShelfStock"),("pocketledger","shelfstock"),
        ("Expenses","Items"),("expenses","items"),("Expense","Item"),("expense","item"),
        ("description","name"),("amount_cents","units"),
        ("total_cents","total_units"),("category","section"),
        ("by_category","by_section"),("food","pantry"),("travel","tools")
    ]:
        code=code.replace(old,new)
    return code


def main():
    original=json.loads(Path("experiments/session028_mentor_predictions.json").read_text(encoding="utf8"))
    selected=original["selected"]
    fixtures={"logic":re_domain(selected["logic"]),
              "store":re_domain(STORE),"api":re_domain(API),"ui":re_domain(UI),
              "css":selected["css"]}
    report=evaluate(fixtures,PUBLIC,"public")
    if not report["integrated"]:
        raise RuntimeError("Isolated ShelfStock positive control failed: "+str(report["failure_reasons"]))
    print("PASS: all five roles can pass the freshly adapted isolated evaluator",flush=True)


if __name__=="__main__":
    main()
