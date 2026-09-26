"""Fake plant systems: SAP HR, production line (MES), shift log. Reseeded on every start."""
import datetime as dt
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
app = FastAPI()

LINES = {
    "L1": {"name": "Body shop", "status": "running", "output": 412, "target": 450},
    "L2": {"name": "Paint", "status": "running", "output": 380, "target": 400},
    "L3": {"name": "Welding", "status": "running", "output": 298, "target": 320},
}

SCRIPTED = [
    {"line": "L3", "station": "S5", "severity": "high", "type": "equipment",
     "message": "Welding robot WR-5 temperature 92C (limit 85C). Cycle time +18%, line slowed.",
     "status": "degraded"},
    {"line": "L1", "station": "S2", "severity": "medium", "type": "quality",
     "message": "Torque tool TT-2 calibration drift: 6 of last 40 bolts under spec.",
     "status": "quality hold"},
]


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def ts(delta_hours=0):
    return (dt.datetime.now() - dt.timedelta(hours=delta_hours)).isoformat(timespec="seconds")


def seed():
    DB.unlink(missing_ok=True)
    c = db()
    c.executescript("""
    create table employees(id text primary key, name text, role text, line text, certifications text,
        performance text, absences_30d int, overtime_h int, notes text);
    create table events(id integer primary key, ts text, line text, station text, severity text, type text, message text);
    create table reports(id integer primary key, ts text, title text, content text);
    """)
    c.executemany("insert into employees values (?,?,?,?,?,?,?,?,?)", [
        ("E101", "Ayse Yilmaz", "Welding operator", "L3", "welding robot, forklift", "Excellent", 0, 6, ""),
        ("E102", "Mehmet Kaya", "Welding operator", "L3", "welding robot", "Needs improvement", 3, 0, "Late twice this month"),
        ("E103", "Ali Demir", "Assembly operator", "L1", "torque tools, welding robot", "Good", 1, 4, ""),
        ("E104", "Zeynep Celik", "Quality inspector", "L1", "torque calibration, QA", "Excellent", 0, 10, ""),
        ("E105", "Can Aydin", "Paint technician", "L2", "paint booth", "Good", 2, 2, ""),
    ])
    c.executemany("insert into events(ts,line,station,severity,type,message) values (?,?,?,?,?,?)", [
        (ts(70), "L2", "S1", "low", "equipment", "Paint booth filter change due"),
        (ts(50), "L3", "S5", "medium", "equipment", "WR-5 temperature 87C, recovered after cooldown"),
        (ts(26), "L1", "S4", "high", "safety", "Light curtain fault, station stopped 25 min"),
    ])
    c.executemany("insert into reports(ts,title,content) values (?,?,?)", [
        (ts(64), "Shift report - 3 days ago", "Output 1190/1170. Paint filter change done. No incidents."),
        (ts(40), "Shift report - 2 days ago", "Output 1102/1170. WR-5 overheating once, cooled down. Mehmet late."),
        (ts(16), "Shift report - yesterday", "Output 1050/1170. L1 light curtain fault, 25 min stop. Maintenance replaced sensor."),
    ])
    c.commit()


seed()


def log_event(e):
    with db() as c:
        cur = c.execute("insert into events(ts,line,station,severity,type,message) values (?,?,?,?,?,?)",
                        (ts(), e["line"], e["station"], e["severity"], e["type"], e["message"]))
        return {"id": cur.lastrowid, "ts": ts(), **{k: e[k] for k in ("line", "station", "severity", "type", "message")}}


# ---- SAP HR ----
@app.get("/hr/employees")
def employees(line: str | None = None):
    q, args = "select * from employees", ()
    if line:
        q, args = q + " where line=?", (line,)
    return [dict(r) for r in db().execute(q, args)]


@app.get("/hr/employees/{eid}")
def employee(eid: str):
    r = db().execute("select * from employees where id=? or name like ?", (eid, f"%{eid}%")).fetchone()
    if not r:
        raise HTTPException(404, "employee not found")
    return dict(r)


class EmpUpdate(BaseModel):
    performance: str | None = None
    notes: str | None = None


@app.patch("/hr/employees/{eid}")
def update_employee(eid: str, u: EmpUpdate):
    e = employee(eid)
    changes = {k: v for k, v in u.model_dump().items() if v is not None}
    with db() as c:
        for k, v in changes.items():
            c.execute(f"update employees set {k}=? where id=?", (v, e["id"]))
    log_event({"line": e["line"], "station": "-", "severity": "info", "type": "hr_change",
               "message": f"HR record of {e['name']} updated: {changes}"})
    return employee(e["id"])


# ---- Production line ----
@app.get("/line/status")
def line_status():
    return LINES


@app.post("/line/trigger/{n}")
def trigger(n: int):
    s = SCRIPTED[n % len(SCRIPTED)]
    LINES[s["line"]]["status"] = s["status"]
    LINES[s["line"]]["output"] -= 25
    event = log_event(s)
    try:
        httpx.post(AGENT_WEBHOOK, json=event, timeout=3)
    except httpx.HTTPError:
        pass
    return event


# ---- Shift log / handover ----
@app.get("/log/events")
def events(hours: int = 8, line: str | None = None):
    q, args = "select * from events where ts>=?", [ts(hours)]
    if line:
        q += " and line=?"
        args.append(line)
    return [dict(r) for r in db().execute(q + " order by ts", args)]


@app.get("/log/reports")
def reports(days: int = 3):
    return [dict(r) for r in db().execute("select * from reports where ts>=? order by ts", (ts(days * 24),))]


class Report(BaseModel):
    title: str
    content: str


@app.post("/log/reports")
def save_report(r: Report):
    with db() as c:
        rid = c.execute("insert into reports(ts,title,content) values (?,?,?)", (ts(), r.title, r.content)).lastrowid
    return {"id": rid, "pdf_url": f"http://localhost:8001/log/reports/{rid}/pdf"}


@app.get("/log/reports/{rid}/pdf")
def report_pdf(rid: int):
    r = db().execute("select * from reports where id=?", (rid,)).fetchone()
    if not r:
        raise HTTPException(404)
    safe = lambda s: s.translate(str.maketrans("şŞıİğĞçÇöÖüÜ", "sSiIgGcCoOuU")).encode("latin-1", "replace").decode("latin-1")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 10, safe(r["title"]))
    pdf.set_font("Helvetica", size=9)
    pdf.cell(0, 6, r["ts"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, safe(r["content"].replace("**", "")))
    return Response(bytes(pdf.output()), media_type="application/pdf")


# ---- Demo control page (fake SAP + dashboard) ----
@app.get("/", response_class=HTMLResponse)
def home():
    lines = "".join(f"<tr><td>{k}</td><td>{v['name']}</td><td>{v['status']}</td><td>{v['output']}/{v['target']}</td></tr>" for k, v in LINES.items())
    emps = "".join(f"<tr><td>{e['id']}</td><td>{e['name']}</td><td>{e['line']}</td><td>{e['performance']}</td><td>{e['notes']}</td></tr>" for e in employees())
    evs = "".join(f"<tr><td>{e['ts']}</td><td>{e['line']}</td><td>{e['severity']}</td><td>{e['message']}</td></tr>" for e in reversed(events(72)))
    btns = "".join(f"<button onclick=\"fetch('/line/trigger/{i}',{{method:'POST'}}).then(()=>location.reload())\">Fire: {s['line']} {s['type']}</button> " for i, s in enumerate(SCRIPTED))
    return f"""<html><head><meta http-equiv="refresh" content="5"><style>body{{font-family:sans-serif;margin:20px}}
    table{{border-collapse:collapse;margin-bottom:20px}}td{{border:1px solid #ccc;padding:4px 8px}}</style></head><body>
    <h2>Production dashboard</h2>{btns}<table>{lines}</table>
    <h2>SAP HR</h2><table>{emps}</table><h2>Shift log</h2><table>{evs}</table></body></html>"""


if __name__ == "__main__":
    uvicorn.run(app, port=8001)
