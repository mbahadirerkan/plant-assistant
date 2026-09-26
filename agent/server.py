"""Agent: threads + Claude tool loop over MCP servers. Serves the chat UI on :8000."""
import asyncio
import datetime as dt
import json
import sys
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

import os

import uvicorn
from openai import AsyncOpenAI
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
MCP_SERVERS = ["hr_mcp.py", "line_mcp.py", "handover_mcp.py"]  # add a server here to add capabilities
# Any OpenAI-compatible provider. Default: Gemini (free tier). Ollama: LLM_BASE_URL=http://localhost:11434/v1
BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
MODEL = os.getenv("LLM_MODEL", "gemini-3.8-flash")
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY") or "none"

SYSTEM = f"""You are the assistant of a shift supervisor in a car plant (lines L1 body shop, L2 paint, L3 welding).
Today is {dt.date.today()}. Use tools to get real data; never invent numbers or people.
Always finish by calling `respond` with: summary (one line), body (short, plain text, may use - bullets), and exactly 3 actions (short next steps the supervisor may tap).
Before any change to HR data, show what will change and offer "Confirm" as the first action; only call update tools after the supervisor confirms.
For a shift report: gather the shift events, write the report, save it with save_report, and attach the pdf_url."""

RESPOND = {
    "name": "respond",
    "description": "Send your reply to the supervisor. Every turn must end with this.",
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "body": {"type": "string"},
            "actions": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
            "attachments": {"type": "array", "items": {"type": "object", "properties": {
                "label": {"type": "string"}, "url": {"type": "string"}}, "required": ["label", "url"]}},
        },
        "required": ["summary", "body", "actions"],
    },
}

llm = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
tools, route = [], {}
threads: dict[str, dict] = {}
subscribers: set[asyncio.Queue] = set()


def new_thread(title, event=None, first=None):
    t = {"id": uuid.uuid4().hex[:8], "title": title, "event": event, "created": dt.datetime.now().isoformat(timespec="seconds"),
         "unread": True, "busy": False, "history": [], "messages": [], "lock": asyncio.Lock()}
    if first:
        t["messages"].append({"role": "assistant", **first})
    threads[t["id"]] = t
    notify(t["id"])
    return t


def notify(tid):
    for q in subscribers:
        q.put_nowait(tid)


def public(t, full=False):
    last = t["messages"][-1] if t["messages"] else {}
    d = {k: t[k] for k in ("id", "title", "event", "created", "unread", "busy")}
    d["preview"] = last.get("summary") or last.get("text", "")
    if full:
        d["messages"] = t["messages"]
    return d


async def run_agent(t, text):
    h = t["history"]
    h.append({"role": "user", "content": text})
    used = []
    fn_tools = [{"type": "function", "function": f} for f in tools + [RESPOND]]
    for _ in range(10):
        resp = await llm.chat.completions.create(model=MODEL, messages=[{"role": "system", "content": SYSTEM}] + h,
                                                 tools=fn_tools, tool_choice="required")
        msg = resp.choices[0].message
        h.append(msg.model_dump(exclude_none=True))  # keeps provider extras (e.g. Gemini thought signatures)
        reply = None
        for tc in msg.tool_calls or []:
            name, args = tc.function.name, json.loads(tc.function.arguments or "{}")
            if name == "respond":
                reply, out = args, "Shown to supervisor."
            else:
                used.append(name)
                try:
                    r = await route[name].call_tool(name, args)
                    out = "\n".join(c.text for c in r.content if hasattr(c, "text"))
                except Exception as e:
                    out = f"Error: {e}"
            h.append({"role": "tool", "tool_call_id": tc.id, "content": out})
        if not msg.tool_calls and msg.content:  # model answered in plain text
            reply = {"summary": msg.content.split("\n")[0][:120], "body": msg.content, "actions": []}
        if reply:
            reply.setdefault("actions", [])
            return {**reply, "tools": used}
    return {"summary": "Could not finish.", "body": "Please try again.", "actions": [], "tools": used}


async def handle(t, text, show_user=True):
    async with t["lock"]:
        if show_user:
            t["messages"].append({"role": "supervisor", "text": text})
        t["busy"] = True
        notify(t["id"])
        try:
            reply = await run_agent(t, text)
        except Exception as e:
            reply = {"summary": "Error", "body": str(e), "actions": []}
        t["messages"].append({"role": "assistant", **reply})
        t["busy"], t["unread"] = False, True
        notify(t["id"])


@asynccontextmanager
async def lifespan(app):
    async with AsyncExitStack() as stack:
        for f in MCP_SERVERS:
            params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_servers" / f)])
            r, w = await stack.enter_async_context(stdio_client(params))
            s = await stack.enter_async_context(ClientSession(r, w))
            await s.initialize()
            for tl in (await s.list_tools()).tools:
                tools.append({"name": tl.name, "description": tl.description or "", "parameters": tl.input_schema})
                route[tl.name] = s
        new_thread("General", first={"summary": "Ask me anything about your shift.", "body": "I can reach SAP HR, the line dashboard and the shift log.",
                                     "actions": ["Give me the last shift's report", "Summarize the last 3 days", "How are the lines doing?"]})
        yield


app = FastAPI(lifespan=lifespan)


@app.post("/events")
async def on_event(e: dict):
    t = new_thread(f"{e['line']} {e['station']} · {e['type']} ({e['severity']})", event=e)
    prompt = (f"New production event (already logged to the shift log): {json.dumps(e)}. "
              "Explain it to the supervisor with context from the line and who on that line is certified to help, then suggest 3 actions.")
    asyncio.create_task(handle(t, prompt, show_user=False))
    return {"thread": t["id"]}


class Msg(BaseModel):
    text: str


@app.get("/threads")
def list_threads():
    return [public(t) for t in sorted(threads.values(), key=lambda t: t["created"], reverse=True)]


@app.get("/threads/{tid}")
def get_thread(tid: str):
    if tid not in threads:
        raise HTTPException(404)
    threads[tid]["unread"] = False
    return public(threads[tid], full=True)


@app.post("/threads/{tid}/messages")
async def post_message(tid: str, m: Msg):
    if tid not in threads:
        raise HTTPException(404)
    asyncio.create_task(handle(threads[tid], m.text))
    return {"ok": True}


@app.get("/stream")
async def stream():
    q = asyncio.Queue()
    subscribers.add(q)

    async def gen():
        try:
            while True:
                yield f"data: {await q.get()}\n\n"
        finally:
            subscribers.discard(q)
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/")
def index():
    return FileResponse(Path(__file__).with_name("index.html"))


if __name__ == "__main__":
    uvicorn.run(app, port=8000)
