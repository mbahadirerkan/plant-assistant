"""Fake plant systems behind Passdown: SAP HR, line (MES), maintenance, shift log. Reseeded on every start."""
import datetime as dt
import json
import sqlite3
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fpdf import FPDF
from pydantic import BaseModel

DB = Path(__file__).with_name("demo.db")
AGENT_WEBHOOK = "http://localhost:8000/events"
SHIFTS = ["n24", "d25", "n25", "d26", "n26"]
CURRENT = "d26"
GROUPS = [("open", "Still open"), ("part", "Missing part"), ("quality", "Quality"), ("machine", "Machine down"),
          ("method", "Not in the instruction"), ("check", "Look at this first"), ("closed", "Closed today")]
app = FastAPI()

LINE = {"name": "Doors", "status": "running", "output": 212, "target": 240,
        "stations": {"12": "running", "14": "running"}}

SCRIPTED = [
    {"station": "14", "type": "machine", "severity": "high", "state": "stopped",
     "text": "Station 14 door lift stopped: hydraulic pressure low"},
    {"station": "12", "type": "quality", "severity": "medium", "state": "running",
     "text": "Station 12 seal gap out of spec on 3 doors"},
]


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def seed():
    DB.unlink(missing_ok=True)
    c = db()
    c.executescript("""
    create table employees(id text primary key, name text, role text, stations text, performance text,
        absences_30d int, present int, notes text);
    create table stations(id text primary key, employee text);
    create table notes(id integer primary key, shift text, ts text, station text, type text, text text,
        source text, severity text, status text default 'open', closed_shift text, ai_line text, suggestions text);
    create table log(id integer primary key, note_id int, ts text, kind text, text text, by text, data text);
    create table tickets(id integer primary key, ts text, station text, text text, status text);
    create table handoffs(id integer primary key, shift text, ts text, paragraph text, groups text);
    """)
    c.executemany("insert into employees values (?,?,?,?,?,?,?,?)", [
        ("E201", "Lena Fischer", "Door fitter", "12", "Good", 0, 1, "Trained on station 12."),
        ("E202", "Sam Weber", "Door fitter", "14", "Good", 2, 0, "Absent today."),
        ("E203", "Nora Klein", "Door fitter", "12,14", "Excellent", 0, 1, "Worked station 14 last night. Knows the lift is slow."),
        ("E204", "Ed Braun", "Door fitter", "14", "Good", 1, 1, "Certified for station 14. Only knows the one-person method."),
        ("E205", "Mehmet Kaya", "Line technician", "12,14", "Needs improvement", 3, 1, "Late twice this month."),
        ("E206", "Ayse Yilmaz", "Quality inspector", "12,14", "Excellent", 0, 1, ""),
    ])
    c.executemany("insert into stations values (?,?)", [("12", "E201"), ("14", None)])
    c.executemany("insert into notes(shift,ts,station,type,text,source,severity) values (?,?,?,?,?,?,?)", [
        ("n25", "2026-09-25T23:40:00", "14", "open", "Station 14 torque tool rejects bolts", "supervisor", "medium"),
        ("n25", "2026-09-26T01:10:00", "14", "method", "Two people set the door because the lift is slow. Official method still says one person.", "supervisor", "low"),
        ("n25", "2026-09-26T03:05:00", "12", "check", "Station 12 was missing clips", "supervisor", "low"),
    ])
    past = {
        "n24": ("Hinge bolts at station 14 were short. Station 12 seal pressed in by hand. Spare socket found.",
                [("Still open", "open", "Station 14 hinge bolts were short"),
                 ("Not in the instruction", "method", "Station 12 seal pressed in by hand. Official method still says use the roller."),
                 ("Closed", "closed", "Station 14 spare socket was in the crib")]),
        "d25": ("Clip bin at station 12 ran low. Station 14 lift paused, one person guided the door. Hinge bolts arrived.",
                [("Still open", "open", "Station 12 clip bin was low"),
                 ("Not in the instruction", "method", "Station 14 lift paused, so one person guided the door. Official method still says use the lift."),
                 ("Closed", "closed", "Station 14 hinge bolts arrived")]),
        "n25": ("Torque tool at station 14 rejects bolts. Two people set the door because the lift is slow. Station 12 missed clips.",
                [("Still open", "open", "Station 14 torque tool rejects bolts"),
                 ("Not in the instruction", "method", "Two people set the door because the lift is slow. Official method still says one person."),
                 ("Missing part", "part", "Station 12 was missing clips")]),
    }
    ends = {"n24": "2026-09-25T06:00:00", "d25": "2026-09-25T18:00:00", "n25": "2026-09-26T06:00:00"}
    for sid, (para, items) in past.items():
        groups = [{"label": lbl, "notes": [{"id": f"{sid}-{j}", "type": t, "text": txt, "log": []}]}
                  for j, (lbl, t, txt) in enumerate(items)]
        c.execute("insert into handoffs(shift,ts,paragraph,groups) values (?,?,?,?)",
                  (sid, ends[sid], para, json.dumps(groups)))
    c.commit()


seed()


def note_dict(r, c):
    d = dict(r)
    d["suggestions"] = json.loads(d["suggestions"] or "[]")
    d["log"] = [{**dict(x), "data": json.loads(x["data"] or "null")}
                for x in c.execute("select * from log where note_id=? order by id", (d["id"],))]
    return d


def get_note(nid):
    c = db()
    r = c.execute("select * from notes where id=?", (nid,)).fetchone()
    if not r:
        raise HTTPException(404, "note not found")
    return note_dict(r, c)


def groups_for(notes):
    out = []
    for t, label in GROUPS:
        items = [n for n in notes if (n["status"] == "closed" and t == "closed") or (n["status"] != "closed" and n["type"] == t)]
        if items:
            out.append({"label": label, "notes": items})
    return out


# ---- Shift log (Passdown's data) ----
@app.get("/shift/{sid}")
def shift(sid: str):
    c = db()
    earlier = SHIFTS[:SHIFTS.index(sid)] if sid in SHIFTS else []
    today = [note_dict(r, c) for r in c.execute("select * from notes where shift=? order by id", (sid,))]
    carried = [note_dict(r, c) for r in c.execute(
        f"select * from notes where shift in ({','.join('?' * len(earlier)) or 'null'}) and (status='open' or closed_shift=?) order by id",
        (*earlier, sid))]
    h = c.execute("select * from handoffs where shift=? order by id desc", (sid,)).fetchone()
    handoff = {**dict(h), "groups": json.loads(h["groups"]), "pdf_url": f"/data/handoffs/{h['id']}/pdf"} if h else None
    return {"shift": sid, "today": today, "carried": carried, "handoff": handoff}


class NewNote(BaseModel):
    text: str
    type: str = "open"
    station: str | None = None
    shift: str = CURRENT
    source: str = "supervisor"
    severity: str = "low"


@app.post("/notes")
def add_note(n: NewNote):
    with db() as c:
        nid = c.execute("insert into notes(shift,ts,station,type,text,source,severity) values (?,?,?,?,?,?,?)",
                        (n.shift, now(), n.station, n.type, n.text, n.source, n.severity)).lastrowid
    return get_note(nid)


@app.get("/notes/{nid}")
def read_note(nid: int):
    return get_note(nid)


class NotePatch(BaseModel):
    type: str | None = None
    status: str | None = None
    ai_line: str | None = None
    suggestions: list[str] | None = None


@app.patch("/notes/{nid}")
def patch_note(nid: int, p: NotePatch):
    get_note(nid)
    with db() as c:
        for k, v in p.model_dump(exclude_none=True).items():
            c.execute(f"update notes set {k}=? where id=?", (json.dumps(v) if k == "suggestions" else v, nid))
        if p.status == "closed":
            c.execute("update notes set closed_shift=? where id=?", (CURRENT, nid))
    return get_note(nid)


class LogEntry(BaseModel):
    kind: str = "action"  # action | response
    text: str
    by: str = "Day supervisor"
    data: dict | None = None


@app.post("/notes/{nid}/log")
def add_log(nid: int, e: LogEntry):
    get_note(nid)
    with db() as c:
        c.execute("insert into log(note_id,ts,kind,text,by,data) values (?,?,?,?,?,?)",
                  (nid, now(), e.kind, e.text, e.by, json.dumps(e.data)))
    return get_note(nid)


# ---- SAP HR ----
@app.get("/hr/employees")
def employees(station: str | None = None):
    rows = [dict(r) for r in db().execute("select * from employees")]
    return [r for r in rows if not station or station in r["stations"].split(",")]


@app.get("/hr/employees/{q}")
def employee(q: str):
    r = db().execute("select * from employees where id=? or name like ?", (q, f"%{q}%")).fetchone()
    if not r:
        raise HTTPException(404, "employee not found")
    return dict(r)


class EmpUpdate(BaseModel):
    performance: str | None = None
    notes: str | None = None


@app.patch("/hr/employees/{q}")
def update_employee(q: str, u: EmpUpdate):
    e = employee(q)
    with db() as c:
        for k, v in u.model_dump(exclude_none=True).items():
            c.execute(f"update employees set {k}=? where id=?", (v, e["id"]))
    return employee(e["id"])


@app.get("/stations")
def stations():
    out = []
    for s in db().execute("select * from stations"):
        e = employee(s["employee"]) if s["employee"] else None
        out.append({"id": s["id"], "employee": e})
    return out


class Assign(BaseModel):
    employee: str


@app.post("/stations/{sid}/assign")
def assign(sid: str, a: Assign):
    e = employee(a.employee)
    if sid not in e["stations"].split(","):
        raise HTTPException(400, f"{e['name']} is not certified for station {sid}")
    with db() as c:
        c.execute("update stations set employee=? where id=?", (e["id"], sid))
    return {"station": sid, "employee": e}


# ---- Line (MES) ----
@app.get("/line/status")
def line_status():
    return LINE


@app.post("/line/trigger/{n}")
def trigger(n: int):
    s = SCRIPTED[n % len(SCRIPTED)]
    LINE["stations"][s["station"]] = s["state"]
    LINE["output"] -= 12
    note = add_note(NewNote(text=s["text"], type=s["type"], station=s["station"], source="line", severity=s["severity"]))
    try:
        httpx.post(AGENT_WEBHOOK, json=note, timeout=3)
    except httpx.HTTPError:
        pass
    return note


# ---- Maintenance ----
@app.get("/tickets")
def tickets():
    return [{**dict(r), "id": 4800 + r["id"]} for r in db().execute("select * from tickets order by id desc")]


class Ticket(BaseModel):
    station: str
    text: str


@app.post("/tickets")
def open_ticket(t: Ticket):
    with db() as c:
        tid = c.execute("insert into tickets(ts,station,text,status) values (?,?,?,?)",
                        (now(), t.station, t.text, "open")).lastrowid
    return {"id": 4800 + tid, "station": t.station, "text": t.text, "status": "open"}


# ---- Handoffs ----
@app.get("/handoffs")
def handoffs(days: int = 3):
    since = (dt.datetime.now() - dt.timedelta(days=days)).isoformat()
    return [{**dict(r), "groups": json.loads(r["groups"])} for r in db().execute("select * from handoffs where ts>=? order by ts", (since,))]


class Handoff(BaseModel):
    shift: str = CURRENT
    paragraph: str


@app.post("/handoffs")
def save_handoff(h: Handoff):
    s = shift(h.shift)
    groups = groups_for(s["carried"] + s["today"])
    with db() as c:
        hid = c.execute("insert into handoffs(shift,ts,paragraph,groups) values (?,?,?,?)",
                        (h.shift, now(), h.paragraph, json.dumps(groups))).lastrowid
    return {"id": hid, "pdf_url": f"/data/handoffs/{hid}/pdf"}


def latin(s):
    return (s or "").translate(str.maketrans("şŞıİğĞçÇöÖüÜ·–—", "sSiIgGcCoOuU-- ")).encode("latin-1", "replace").decode("latin-1")


@app.get("/handoffs/{hid}/pdf")
def handoff_pdf(hid: int):
    h = db().execute("select * from handoffs where id=?", (hid,)).fetchone()
    if not h:
        raise HTTPException(404)
    pdf = FPDF()
    pdf.add_page()
    w = pdf.epw

    def line(text, size=11, style="", h=6, indent=0):
        pdf.set_font("Helvetica", style, size)
        pdf.set_x(pdf.l_margin + indent)
        pdf.multi_cell(w - indent, h, latin(text), new_x="LMARGIN", new_y="NEXT")

    line(f"Doors - handoff {h['shift']}", 18, "B", 10)
    line(h["ts"].replace("T", " "), 9)
    pdf.ln(3)
    line(h["paragraph"])
    for g in json.loads(h["groups"]):
        pdf.ln(4)
        line(g["label"].upper(), 10, "B")
        for n in g["notes"]:
            line(f"- {n['text']}", 11, "", 6, 2)
            for e in n.get("log", []):
                r = (e.get("data") or {}).get("record")
                if r:
                    for k in ("action_taken", "done_by", "status", "follow_up"):
                        line(f"{k.replace('_', ' ').capitalize()}: {r.get(k) or 'not stated'}", 9, "", 5, 8)
                else:
                    line(f"{e['ts'][11:16]} {e['text']}", 9, "", 5, 8)
    return Response(bytes(pdf.output()), media_type="application/pdf")


# ---- Demo control page: the "real systems" screen ----
@app.get("/", response_class=HTMLResponse)
def home():
    t = lambda rows: "<table>" + "".join("<tr>" + "".join(f"<td>{v}</td>" for v in r) + "</tr>" for r in rows) + "</table>"
    btns = "".join(f"<button onclick=\"fetch('/line/trigger/{i}',{{method:'POST'}}).then(()=>location.reload())\">Fire: {s['text']}</button><br>" for i, s in enumerate(SCRIPTED))
    st = t([(k, v) for k, v in LINE["stations"].items()])
    hr = t([(e["id"], e["name"], e["stations"], "present" if e["present"] else "absent", e["performance"], e["notes"]) for e in employees()])
    sts = t([(s["id"], s["employee"]["name"] if s["employee"] else "empty") for s in stations()])
    tk = t([(k["id"], k["ts"][11:16], k["station"], k["text"], k["status"]) for k in tickets()]) or "none"
    lg = t([(r["ts"][11:16], r["text"][:60], r["kind"], r["ltext"]) for r in db().execute(
        "select l.ts, n.text, l.kind, l.text as ltext from log l join notes n on n.id=l.note_id order by l.id desc limit 15")])
    return f"""<html><head><meta http-equiv="refresh" content="4"><style>body{{font-family:sans-serif;margin:20px;display:grid;grid-template-columns:1fr 1fr;gap:0 30px}}
    table{{border-collapse:collapse}}td{{border:1px solid #ccc;padding:4px 8px;font-size:14px}}h3{{margin:18px 0 6px}}button{{margin:3px 0}}</style></head><body>
    <div><h3>Line (MES) · Doors · {LINE['output']}/{LINE['target']}</h3>{btns}{st}<h3>Station staffing (SAP HR)</h3>{sts}<h3>Maintenance tickets</h3>{tk}</div>
    <div><h3>SAP HR</h3>{hr}<h3>Shift log · actions & responses</h3>{lg}</div></body></html>"""


if __name__ == "__main__":
    uvicorn.run(app, port=8001)
