"""Fake plant systems behind Passdown: SAP HR, line (MES), maintenance, shift log. Reseeded on every start."""
import datetime as dt
import json
import os
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
GROUPS = [("open", "Still open"), ("part", "Missing part"), ("quality", "Quality"), ("machine", "Machine down"),
          ("method", "Not in the instruction"), ("check", "Look at this first"), ("closed", "Closed today")]
app = FastAPI()

LINE = {}
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


# ---- Shift calendar: day 06-18, night 18-06. Ids like 2026-09-26-day ----
def shift_id(date, kind):
    return f"{date.isoformat()}-{kind}"


def next_shift(sid):
    date, kind = dt.date.fromisoformat(sid[:10]), sid[11:]
    return shift_id(date, "night") if kind == "day" else shift_id(date + dt.timedelta(days=1), "day")


def shift_info(sid, status):
    date, kind = dt.date.fromisoformat(sid[:10]), sid[11:]
    return {"id": sid, "kind": kind, "status": status, "label": f"{kind.capitalize()} {date.day}",
            "when": f"{date:%a %d %b} · {kind.capitalize()} shift", "date": date.isoformat()}


def shift_end(sid):
    date, kind = dt.date.fromisoformat(sid[:10]), sid[11:]
    return (dt.datetime.combine(date, dt.time(18)) if kind == "day"
            else dt.datetime.combine(date + dt.timedelta(days=1), dt.time(6))).isoformat()


def active():
    return db().execute("select id from shifts where status='active'").fetchone()["id"]


def seed():
    LINE.clear()
    LINE.update({"name": "Doors", "status": "running", "output": 212, "target": 240,
                 "stations": {"12": "running", "14": "running"}})
    today = dt.date.today()
    y, yy = today - dt.timedelta(days=1), today - dt.timedelta(days=2)
    s_n2, s_d1, s_n1, s_d0 = shift_id(yy, "night"), shift_id(y, "day"), shift_id(y, "night"), shift_id(today, "day")
    c = db()
    for (t,) in c.execute("select name from sqlite_master where type='table'").fetchall():
        c.execute(f"drop table {t}")
    c.executescript("""
    create table shifts(id text primary key, status text);
    create table employees(id text primary key, name text, role text, stations text, performance text,
        absences_30d int, present int, notes text);
    create table stations(id text primary key, employee text);
    create table notes(id integer primary key, shift text, ts text, station text, type text, text text,
        source text, severity text, status text default 'open', closed_shift text, ai_line text, suggestions text);
    create table log(id integer primary key, note_id int, ts text, kind text, text text, by text, data text);
    create table tickets(id integer primary key, ts text, station text, text text, status text);
    create table handoffs(id integer primary key, shift text, ts text, paragraph text, groups text, confirmed text);
    """)
    c.executemany("insert into shifts values (?,?)",
                  [(s_n2, "passed"), (s_d1, "passed"), (s_n1, "passed"), (s_d0, "active")])
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
        (s_n1, f"{y}T23:40:00", "14", "open", "Station 14 torque tool rejects bolts", "supervisor", "medium"),
        (s_n1, f"{today}T01:10:00", "14", "method", "Two people set the door because the lift is slow. Official method still says one person.", "supervisor", "low"),
        (s_n1, f"{today}T03:05:00", "12", "check", "Station 12 was missing clips", "supervisor", "low"),
    ])
    past = {
        s_n2: ("Hinge bolts at station 14 were short. Station 12 seal pressed in by hand. Spare socket found.",
               [("Still open", "open", "Station 14 hinge bolts were short"),
                ("Not in the instruction", "method", "Station 12 seal pressed in by hand. Official method still says use the roller."),
                ("Closed", "closed", "Station 14 spare socket was in the crib")]),
        s_d1: ("Clip bin at station 12 ran low. Station 14 lift paused, one person guided the door. Hinge bolts arrived.",
               [("Still open", "open", "Station 12 clip bin was low"),
                ("Not in the instruction", "method", "Station 14 lift paused, so one person guided the door. Official method still says use the lift."),
                ("Closed", "closed", "Station 14 hinge bolts arrived")]),
        s_n1: ("Torque tool at station 14 rejects bolts. Two people set the door because the lift is slow. Station 12 missed clips.",
               [("Still open", "open", "Station 14 torque tool rejects bolts"),
                ("Not in the instruction", "method", "Two people set the door because the lift is slow. Official method still says one person."),
                ("Missing part", "part", "Station 12 was missing clips")]),
    }
    for sid, (para, items) in past.items():
        groups = [{"label": lbl, "notes": [{"id": f"{sid}-{j}", "type": t, "text": txt, "log": []}]}
                  for j, (lbl, t, txt) in enumerate(items)]
        c.execute("insert into handoffs(shift,ts,paragraph,groups,confirmed) values (?,?,?,?,?)",
                  (sid, shift_end(sid), para, json.dumps(groups), shift_end(sid)))
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


def handoff_dict(h):
    return {**dict(h), "groups": json.loads(h["groups"]), "pdf_url": f"/data/handoffs/{h['id']}/pdf"} if h else None


# ---- Shift log (Passdown's data) ----
@app.get("/shifts")
def shifts():
    rows = [shift_info(r["id"], r["status"]) for r in db().execute("select * from shifts order by id")]
    return rows + [shift_info(next_shift(rows[-1]["id"]), "next")]


@app.get("/shift/{sid}")
def shift(sid: str):
    """sid can be 'current' for the active shift."""
    c = db()
    sid = active() if sid == "current" else sid
    ids = [r["id"] for r in c.execute("select id from shifts order by id")]
    earlier = ids[:ids.index(sid)] if sid in ids else ids
    today = [note_dict(r, c) for r in c.execute("select * from notes where shift=? order by id", (sid,))]
    carried = [note_dict(r, c) for r in c.execute(
        f"select * from notes where shift in ({','.join('?' * len(earlier)) or 'null'}) and (status='open' or closed_shift=?) order by id",
        (*earlier, sid))]
    handoff = handoff_dict(c.execute("select * from handoffs where shift=? order by id desc", (sid,)).fetchone())
    received = handoff_dict(c.execute("select * from handoffs where shift=?", (earlier[-1],)).fetchone()) if earlier else None
    status = c.execute("select status from shifts where id=?", (sid,)).fetchone()
    return {"shift": shift_info(sid, status["status"] if status else "next"), "today": today, "carried": carried,
            "handoff": handoff, "received": received}


class NewNote(BaseModel):
    text: str
    type: str = "open"
    station: str | None = None
    source: str = "supervisor"
    severity: str = "low"


@app.post("/notes")
def add_note(n: NewNote):
    with db() as c:
        nid = c.execute("insert into notes(shift,ts,station,type,text,source,severity) values (?,?,?,?,?,?,?)",
                        (active(), now(), n.station, n.type, n.text, n.source, n.severity)).lastrowid
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
        if p.status:
            c.execute("update notes set closed_shift=? where id=?", (active() if p.status == "closed" else None, nid))
    return get_note(nid)


class LogEntry(BaseModel):
    kind: str = "action"  # action | response
    text: str
    by: str = "Supervisor"
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


# ---- Handoffs: passing one moves the calendar to the next shift ----
@app.get("/handoffs")
def handoffs(days: int = 3):
    since = (dt.datetime.now() - dt.timedelta(days=days)).isoformat()
    return [{**handoff_dict(r), "shift_label": shift_info(r["shift"], "passed")["label"]}
            for r in db().execute("select * from handoffs where ts>=? order by ts", (since,))]


class Handoff(BaseModel):
    paragraph: str


@app.post("/handoffs")
def pass_shift(h: Handoff):
    sid = active()
    s = shift(sid)
    groups = groups_for(s["carried"] + s["today"])
    nxt = next_shift(sid)
    with db() as c:
        hid = c.execute("insert into handoffs(shift,ts,paragraph,groups) values (?,?,?,?)",
                        (sid, now(), h.paragraph, json.dumps(groups))).lastrowid
        c.execute("update shifts set status='passed' where id=?", (sid,))
        c.execute("insert into shifts values (?, 'active')", (nxt,))
    return {"id": hid, "pdf_url": f"/data/handoffs/{hid}/pdf", "passed": sid, "active": nxt}


@app.post("/handoffs/{hid}/confirm")
def confirm_handoff(hid: int):
    with db() as c:
        c.execute("update handoffs set confirmed=? where id=?", (now(), hid))
    return handoff_dict(db().execute("select * from handoffs where id=?", (hid,)).fetchone())


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

    line(f"Doors - handoff {shift_info(h['shift'], '')['when']}", 18, "B", 10)
    line(f"Passed {h['ts'].replace('T', ' ')}", 9)
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


@app.post("/reset")
def reset():
    seed()
    try:
        httpx.post(AGENT_WEBHOOK.replace("/events", "/refresh"), timeout=3)
    except httpx.HTTPError:
        pass
    return {"ok": True}


# ---- Demo control page: the "real systems" screen ----
@app.get("/", response_class=HTMLResponse)
def home():
    t = lambda rows: "<table>" + "".join("<tr>" + "".join(f"<td>{v}</td>" for v in r) + "</tr>" for r in rows) + "</table>"
    btn = lambda url, label: f"<button onclick=\"fetch('{url}',{{method:'POST'}}).then(()=>location.reload())\">{label}</button> "
    fire = "".join(btn(f"/line/trigger/{i}", f"Fire: {s['text']}") + "<br>" for i, s in enumerate(SCRIPTED))
    st = t([(k, v) for k, v in LINE["stations"].items()])
    hr = t([(e["id"], e["name"], e["stations"], "present" if e["present"] else "absent", e["performance"], e["notes"]) for e in employees()])
    sts = t([(s["id"], s["employee"]["name"] if s["employee"] else "empty") for s in stations()])
    tk = t([(k["id"], k["ts"][11:16], k["station"], k["text"], k["status"]) for k in tickets()]) or "none"
    cal = t([(s["label"], s["status"]) for s in shifts()])
    lg = t([(r["ts"][11:16], r["text"][:60], r["kind"], r["ltext"]) for r in db().execute(
        "select l.ts, n.text, l.kind, l.text as ltext from log l join notes n on n.id=l.note_id order by l.id desc limit 15")])
    return f"""<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="4"><style>body{{font-family:sans-serif;margin:20px;display:grid;grid-template-columns:1fr 1fr;gap:0 30px}}
    table{{border-collapse:collapse}}td{{border:1px solid #ccc;padding:4px 8px;font-size:14px}}h3{{margin:18px 0 6px}}button{{margin:3px 0}}</style></head><body>
    <div><h3>Line (MES) · Doors · {LINE['output']}/{LINE['target']}</h3>{fire}{st}<h3>Station staffing (SAP HR)</h3>{sts}<h3>Maintenance tickets</h3>{tk}</div>
    <div><h3>Shifts</h3>{cal}{btn('/reset', 'Reset demo')}<h3>SAP HR</h3>{hr}<h3>Shift log · actions & responses</h3>{lg}</div></body></html>"""


if __name__ == "__main__":
    uvicorn.run(app, port=8001, timeout_graceful_shutdown=1)
    os._exit(0)  # don't wait on leftover connections or MCP processes
