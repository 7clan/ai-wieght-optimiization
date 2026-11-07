"""ClinicQueue — the independent transfer benchmark (mission section 11).

A second application with DIFFERENT requirements and terminology
(appointment/patient scheduling, synthetic records only).  It must NOT
reuse TaskFlow-specific source code as a target solution.  Its private
tests were frozen BEFORE any repair selection: this module's checks are
fixed constants, and the transfer runs compare:

  A. frozen Qwen, plain prompts (no TaskFlow patterns)
  B. frozen Qwen + TaskFlow repair-memory patterns in the prompt

The comparison uses whole-module generations only (the honest measure of
PATTERN transfer, not scaffold reuse).  Roles: logic (Python waiting-time
processor) and store (Node queue store) — the two roles where TaskFlow
accumulated verified correction patterns.
"""
from __future__ import annotations

import hashlib
import json

NAME = "ClinicQueue"
ROLES = ("logic", "store")

SPEC = """Build ClinicQueue, a clinic appointment queue manager (SYNTHETIC
data only). Appointments: id string, patientName non-empty string,
department one of 'general','cardio','derma' (default 'general'),
urgency one of 'routine','urgent' (default 'routine'),
arrivedAt 'HH:MM' 24h string, seen boolean (default false).
Receptionists add appointments, mark them seen, cancel them, list the
waiting queue by department or urgency, and read per-department waiting
counts. JSON file persistence."""

LOGIC_SPEC = """Write ONE Python function summarize_queue(payload).
payload = {"appointments": [...]} (arrivedAt 'HH:MM' strings).
Return a dict with EXACTLY these keys:
  waiting: int, appointments not yet seen
  seen: int, appointments already seen
  by_department: dict with keys 'general','cardio','derma' mapping to the
    count of WAITING (not seen) appointments in that department (all
    three keys always present)
  longest_wait_minutes: int, minutes since the EARLIEST waiting
    appointment's arrivedAt until '17:00'; 0 when nothing is waiting.
    Parse 'HH:MM' as hours*60+minutes.
Rules: never mutate the payload; empty -> 0, 0, all zeros, 0.
Start with 'def summarize_queue(payload):'."""

STORE_SPEC = """Write ONE JavaScript module: a factory createQueue(filePath)
managing appointments with JSON file persistence. It returns an object
with EXACTLY these methods:
  listWaiting(filter) -> array of copies; filter {department?, urgency?};
      exact matches; missing keys match everything
  add(body) -> new appointment {id, patientName, department, urgency,
      arrivedAt, seen}
      body: {patientName, department?, urgency?, arrivedAt};
      throw Error when patientName is not a non-empty string, department
      not in ['general','cardio','derma'], urgency not in
      ['routine','urgent'], arrivedAt not matching 'HH:MM'
      (/^\\d{2}:\\d{2}$/); defaults department 'general', urgency
      'routine', seen false
  markSeen(id) -> updated appointment with seen true; throw Error if
      id unknown
  cancel(id) -> true; throw Error if id unknown
Ids are strings 'a1','a2',... The persisted file shape is exactly
{"appointments":[...]}; on construction load it if it exists, else start
empty; persist after EVERY mutation with fs.writeFileSync(filePath,
JSON.stringify(state)). Use: const fs = require('node:fs');
End with: module.exports = createQueue;
Start with 'function createQueue(filePath) {'."""

ANCHOR = {
    "logic": "def summarize_queue(payload):\n",
    "store": "const fs = require('node:fs');\nfunction createQueue(filePath) {\n",
}

GOALS = {
    "logic": """ClinicQueue waiting-time processor (Python). payload is a
dict: payload["appointments"] is the list. Start with:
appointments = payload["appointments"]. Return dict with EXACTLY four
keys: waiting (int, count of seen != True), seen (int, count of seen ==
True), by_department (dict with keys general, cardio, derma mapping to
WAITING counts; all three keys always), longest_wait_minutes (int:
for the EARLIEST waiting appointment, minutes from its arrivedAt until
'17:00', computed as (17*60) - (h*60+m) from 'HH:MM'; 0 when nothing
waits). The four values are plain ints, never dicts. Never mutate the
payload.""",
    "store": """ClinicQueue storage module (Node.js). Factory
createQueue(filePath) returns object with methods: listWaiting(filter),
add(body), markSeen(id), cancel(id). Appointment: {id, patientName,
department, urgency, arrivedAt, seen}. Ids 'a1','a2',... separate
counter. Defaults: department 'general', urgency 'routine', seen false.
Valid: department in general/cardio/derma, urgency in routine/urgent,
arrivedAt matches /^\\d{2}:\\d{2}$/, patientName non-empty string.
Invalid or unknown id throws Error. listWaiting filter {department,
urgency}: exact match, missing keys match all. Return copies. Persist
after EVERY mutation: fs.writeFileSync(filePath,
JSON.stringify(state)); state shape {"appointments":[...]}; on
construction load via fs.existsSync + readFileSync + JSON.parse else
start empty. Values reassigned later must use let.""",
}

EXAMPLES = {
    "logic": """PUBLIC EXAMPLE (exact shapes):
summarize_queue({"appointments": [
{"patientName": "A", "department": "cardio", "urgency": "urgent",
 "arrivedAt": "09:15", "seen": False},
{"patientName": "B", "department": "general", "urgency": "routine",
 "arrivedAt": "10:30", "seen": True}]})
returns
{"waiting": 1, "seen": 1, "by_department": {"general": 0, "cardio": 1,
"derma": 0}, "longest_wait_minutes": 465}
(09:15 -> 17:00 is 7h45m = 465 minutes)
summarize_queue({"appointments": []})
returns
{"waiting": 0, "seen": 0, "by_department": {"general": 0, "cardio": 0,
"derma": 0}, "longest_wait_minutes": 0}""",
    "store": """PUBLIC EXAMPLE (exact behavior):
const q = createQueue('queue.json');
q.add({patientName: 'Ada', arrivedAt: '09:15'}) returns
{id: 'a1', patientName: 'Ada', department: 'general', urgency:
'routine', arrivedAt: '09:15', seen: false}  // defaults applied
and ADDS it: q.listWaiting({}) now contains it.
q.add({patientName: '', arrivedAt: '09:00'}) throws Error.
q.markSeen('a1') CHANGES the stored appointment: later listWaiting({})
no longer includes it; the returned copy has seen: true.
q.markSeen('zz') throws Error('not found: zz').
A NEW createQueue('queue.json') still lists unchanged records (file
persistence). Ids: 'a1', 'a2', ... (string with prefix).""",
}

# --- frozen private tests (defined here BEFORE any transfer run) ---------

LOGIC_TESTS = [
    {"payload": {"appointments": []},
     "expected": {"waiting": 0, "seen": 0,
                  "by_department": {"general": 0, "cardio": 0, "derma": 0},
                  "longest_wait_minutes": 0}},
    {"payload": {"appointments": [
        {"patientName": "P1", "department": "derma", "urgency": "routine",
         "arrivedAt": "08:00", "seen": False},
        {"patientName": "P2", "department": "derma", "urgency": "urgent",
         "arrivedAt": "09:30", "seen": False},
        {"patientName": "P3", "department": "general", "urgency": "routine",
         "arrivedAt": "11:45", "seen": True}]},
     "expected": {"waiting": 2, "seen": 1,
                  "by_department": {"general": 0, "cardio": 2, "derma": 0},
                  "longest_wait_minutes": 540}},
    {"payload": {"appointments": [
        {"patientName": "P4", "department": "cardio", "urgency": "urgent",
         "arrivedAt": "16:59", "seen": False}]},
     "expected": {"waiting": 1, "seen": 0,
                  "by_department": {"general": 0, "cardio": 1, "derma": 0},
                  "longest_wait_minutes": 1}},
]

STORE_TESTS = [
    {"op": "listWaiting", "filter": {}, "expect": []},
    {"op": "add", "body": {"patientName": "Ada", "arrivedAt": "09:15"},
     "expect": {"id": "a1", "patientName": "Ada", "department": "general",
                "urgency": "routine", "arrivedAt": "09:15", "seen": False}},
    {"op": "add", "body": {"patientName": "Bo", "department": "cardio",
                           "urgency": "urgent", "arrivedAt": "10:30"},
     "expect": {"id": "a2", "department": "cardio", "urgency": "urgent"}},
    {"op": "add", "body": {"patientName": "", "arrivedAt": "09:00"},
     "expectError": True},
    {"op": "add", "body": {"patientName": "Cy", "department": "ortho",
                           "arrivedAt": "09:00"}, "expectError": True},
    {"op": "add", "body": {"patientName": "Di", "arrivedAt": "9:15"},
     "expectError": True},
    {"op": "markSeen", "id": "a1", "expect": {"id": "a1", "seen": True}},
    {"op": "markSeen", "id": "zz", "expectError": True},
    {"op": "listWaiting", "filter": {"department": "cardio"},
     "expectCount": 1},
    {"op": "listWaiting", "filter": {"urgency": "urgent"},
     "expectCount": 1},
    {"op": "listWaiting", "filter": {}, "expectCount": 1},
    {"op": "cancel", "id": "a2", "expect": True},
    {"op": "cancel", "id": "a2", "expectError": True},
    {"op": "reload"},
    {"op": "listWaiting", "filter": {}, "expectCount": 0},
    {"op": "persistedShape"},
]


def fingerprint() -> str:
    blob = json.dumps({"spec": SPEC, "logic": LOGIC_SPEC, "store": STORE_SPEC,
                       "logic_tests": LOGIC_TESTS,
                       "store_tests": STORE_TESTS},
                      sort_keys=True).encode("utf8")
    return hashlib.sha256(blob).hexdigest()


def prompt(role: str, *, patterns: str = "") -> str:
    """Transfer prompt. patterns = retrieved TaskFlow repair-memory block
    (concepts only, different domain)."""
    c = "#"
    def line(x):
        return f"{c} {x[:118]}\n"
    text = line(f"NEW {NAME} TASK. Complete the code after the final signature. No prose.")
    for block in (SPEC, GOALS[role], EXAMPLES[role]):
        text += "".join(line(x) for x in block.splitlines()[:40])
    if patterns:
        text += patterns
    return text + "\n" + ANCHOR[role]
