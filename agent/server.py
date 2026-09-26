"""AI side of Passdown: connects the MCP servers and serves the AI endpoints on :8000."""
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import openai
from openai import AsyncOpenAI
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
DATA = "http://localhost:8001"

# Connected systems. To add one: write an MCP server in mcp_servers/ and add an entry here.
SYSTEMS = [
    {"file": "line_mcp.py", "name": "Line dashboard", "about": "Live status of the Doors line",
     "examples": ["How is the line doing?"]},
    {"file": "hr_mcp.py", "name": "SAP HR", "about": "People, certifications, staffing",
     "examples": ["Who is certified for station 14?", "Who has been absent this month?"]},
    {"file": "maintenance_mcp.py", "name": "Maintenance", "about": "Maintenance tickets",
     "examples": ["Which tickets are open?"]},
    {"file": "shiftlog_mcp.py", "name": "Shift log", "about": "Issues, responses and handoffs",
     "examples": ["Summarize the last 3 days", "What is still open from last night?"]},
]

# Any OpenAI-compatible provider. Default: Gemini. Ollama: LLM_BASE_URL=http://localhost:11434/v1
BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
MODEL = os.getenv("LLM_MODEL", "gemini-3.8-flash")
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY") or "none"
# Tried in order when the main model is overloaded (503) or rate limited (429), e.g. LLM_FALLBACKS=model-a,model-b
FALLBACKS = [m.strip() for m in os.getenv("LLM_FALLBACKS", "").split(",") if m.strip()]

CONTEXT = """You work inside Passdown, the shift notebook of the supervisor of the Doors line (stations 12 and 14) in a car plant.
Current shift: 'd26' (Sat 26 Sep, day). Previous: 'n25'. Use tools for facts; never invent people, numbers or events.
Write like Passdown: short, plain, factual sentences. No markdown."""

llm = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY, max_retries=0)
tools, route, subscribers = [], {}, set()


def clean(schema):
    """Simplify MCP JSON schemas for providers with strict schema support (e.g. Gemini)."""
    if isinstance(schema, list):
        return [clean(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    s = {k: clean(v) for k, v in schema.items() if k not in ("title", "default", "additionalProperties")}
    opts = [o for o in s.pop("anyOf", []) if o.get("type") != "null"]
    if opts:
        s.update(opts[0])
    return s


def final(name, props, required=None):
    return {"type": "function", "function": {"name": name, "description": "Return your final result with this.",
            "parameters": {"type": "object", "properties": props, "required": required or list(props)}}}


async def complete(**kw):
    """Retry busy/rate-limited calls with backoff, trying fallback models on each round."""
    error = None
    for attempt in range(4):
        for model in [MODEL] + FALLBACKS:
            try:
                return await llm.chat.completions.create(model=model, **kw)
            except (openai.InternalServerError, openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError) as e:
                error = e
                print(f"{model} busy ({getattr(e, 'status_code', 'no connection')}), trying next")
        await asyncio.sleep(2 ** attempt)
    raise error


async def ask_llm(task, final_tool, history=None, use_tools=True):
    """Run a tool loop until the model calls final_tool; returns its arguments."""
    msgs = [{"role": "system", "content": CONTEXT}] + (history or []) + [{"role": "user", "content": task}]
    fn = (tools if use_tools else []) + [final_tool]
    name = final_tool["function"]["name"]
    for _ in range(8):
        r = await complete(messages=msgs, tools=fn, tool_choice="required")
        m = r.choices[0].message
        msgs.append(m.model_dump(exclude_none=True))  # keeps provider extras (e.g. Gemini thought signatures)
        for tc in m.tool_calls or []:
            args = json.loads(tc.function.arguments or "{}")
            if tc.function.name == name:
                return args
            try:
                res = await route[tc.function.name].call_tool(tc.function.name, args)
                out = "\n".join(c.text for c in res.content if hasattr(c, "text"))
            except Exception as e:
                out = f"Error: {e}"
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": out})
    raise RuntimeError("The model did not finish.")


def notify(msg="refresh"):
    for q in subscribers:
        q.put_nowait(msg)


async def data(method, path, **kw):
    async with httpx.AsyncClient(base_url=DATA) as c:
        r = await c.request(method, path, **kw)
        r.raise_for_status()
        return r.json()


@asynccontextmanager
async def lifespan(app):
    async with AsyncExitStack() as stack:
        for s in SYSTEMS:
            params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_servers" / s["file"])])
            r, w = await stack.enter_async_context(stdio_client(params))
            sess = await stack.enter_async_context(ClientSession(r, w))
            await sess.initialize()
            s["tools"] = []
            for t in (await sess.list_tools()).tools:
                tools.append({"type": "function", "function": {
                    "name": t.name, "description": t.description or "", "parameters": clean(t.input_schema)}})
                route[t.name] = sess
                s["tools"].append(t.name)
        yield


app = FastAPI(lifespan=lifespan)


@app.exception_handler(Exception)
async def ai_error(request: Request, e: Exception):
    return PlainTextResponse(f"The assistant is unavailable: {str(e)[:150]}", status_code=502)


# ---- A new issue arrives from the line: add one factual line and suggested actions ----
async def enrich(note):
    try:
        r = await ask_llm(
            f"New issue from the line, already in the shift log: {json.dumps(note)}. Check context with tools "
            "(line status, staffing, who is certified and present for that station, earlier notes, open tickets). "
            "ai_line: one factual line, max 12 words, e.g. 'Second lift problem today · Nora is certified'. "
            "suggestions: 2-3 actions your tools can carry out, max 5 words each, e.g. 'Open maintenance ticket', 'Assign Nora to station 14'.",
            final("enrich", {"ai_line": {"type": "string"}, "suggestions": {"type": "array", "items": {"type": "string"}}}))
        await data("PATCH", f"/notes/{note['id']}", json={"ai_line": r["ai_line"], "suggestions": r["suggestions"][:3]})
    except Exception as e:
        print("enrich failed:", e)
        await data("PATCH", f"/notes/{note['id']}", json={"ai_line": "Logged from the line · systems check unavailable"})
    notify()


@app.post("/events")
async def on_event(note: dict):
    notify()
    asyncio.create_task(enrich(note))
    return {"ok": True}


# ---- Carry out a suggested action (after the supervisor confirmed it) ----
class Act(BaseModel):
    action: str


@app.post("/api/notes/{nid}/act")
async def act(nid: int, a: Act):
    note = await data("GET", f"/notes/{nid}")
    r = await ask_llm(
        f"The supervisor confirmed this action for issue {json.dumps(note)}: '{a.action}'. Carry it out with your tools. "
        "result: one past-tense sentence for the log naming what the system returned, e.g. 'Nora assigned to station 14' "
        "or 'Maintenance ticket #4801 opened'. If it failed, say why.",
        final("done", {"result": {"type": "string"}, "system": {"type": "string", "description": "Which system did it"}}))
    await data("POST", f"/notes/{nid}/log", json={"kind": "action", "text": r["result"], "data": {"system": r.get("system")}})
    await data("PATCH", f"/notes/{nid}", json={"suggestions": [s for s in note["suggestions"] if s != a.action]})
    notify()
    return r


# ---- Turn the supervisor's own words into a standard response record ----
class Words(BaseModel):
    text: str


@app.post("/api/notes/{nid}/structure")
async def structure(nid: int, w: Words):
    note = await data("GET", f"/notes/{nid}")
    return await ask_llm(
        f"Issue: {json.dumps(note['text'])}. The supervisor described the response in their own words: {json.dumps(w.text)}. "
        "Fill the record ONLY from their words; do not add anything. If a field is not mentioned, write 'not stated'. "
        "For done_by you may look up names in SAP HR to write the full name. Keep each field short.",
        final("record", {"action_taken": {"type": "string"}, "done_by": {"type": "string"},
                         "status": {"type": "string", "enum": ["resolved", "temporary", "escalated", "not stated"]},
                         "follow_up": {"type": "string"}}))


# ---- Sort a free note into a Passdown type ----
@app.post("/api/classify")
async def classify(w: Words):
    return await ask_llm(
        f"Sort this shift note: {json.dumps(w.text)}. Types: open (still open problem), part (missing part), quality, "
        "machine (machine down), method (done differently than the official instruction). Station is '12', '14' or empty.",
        final("sort", {"type": {"type": "string", "enum": ["open", "part", "quality", "machine", "method"]},
                       "station": {"type": "string"}}), use_tools=False)


# ---- Draft the handoff paragraph from the log ----
@app.post("/api/handoff")
async def handoff():
    shift, staffing, tickets = await asyncio.gather(data("GET", "/shift/d26"), data("GET", "/stations"), data("GET", "/tickets"))
    return await ask_llm(
        f"Write the handoff for the night shift from this data only. Shift log: {json.dumps(shift)}. "
        f"Staffing: {json.dumps(staffing)}. Maintenance tickets: {json.dumps(tickets)}. "
        "4-6 short sentences: who is on which station, what is still open, what was done, what the next shift must know "
        "(including anything done outside the official method).",
        final("handoff", {"paragraph": {"type": "string"}}), use_tools=False)


# ---- Systems page: list systems and answer questions ----
@app.get("/api/systems")
def systems():
    return [{k: s[k] for k in ("name", "about", "examples", "tools")} | {"connected": True} for s in SYSTEMS]


class Ask(BaseModel):
    text: str
    history: list[dict] = []  # [{role: user|assistant, content}], kept by the page only


@app.post("/api/ask")
async def ask(a: Ask):
    return await ask_llm(
        a.text + "\n\n(Answer in 1-4 short sentences. Do not change anything in any system; if the supervisor wants a change, "
                 "say what you would do. chips: up to 3 short follow-up questions they might ask next. "
                 "sources: names of the systems you used, from: Line dashboard, SAP HR, Maintenance, Shift log.)",
        final("answer", {"answer": {"type": "string"}, "chips": {"type": "array", "items": {"type": "string"}},
                         "sources": {"type": "array", "items": {"type": "string"}}}),
        history=a.history)


@app.get("/api/stream")
async def stream():
    q = asyncio.Queue()
    subscribers.add(q)

    async def gen():
        try:
            yield "data: hello\n\n"
            while True:
                yield f"data: {await q.get()}\n\n"
        finally:
            subscribers.discard(q)
    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    if "--models" in sys.argv:  # list the models your key can use
        async def show():
            async for m in llm.models.list():
                print(m.id)
        asyncio.run(show())
    else:
        uvicorn.run(app, port=8000, timeout_graceful_shutdown=1)
        os._exit(0)  # don't wait on leftover connections or MCP processes
