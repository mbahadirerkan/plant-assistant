# Passdown + plant systems (hackathon MVP)

Passdown (the shift notebook, from tarikemal/passdown) running on live plant data, with an AI that reads and acts on the systems through MCP.

```
web/              Passdown UI (React + Vite)                               :5173
agent/server.py   AI: enriches line issues, runs actions, structures responses, drafts handoffs   :8000
mcp_servers/      one adapter per system: line, SAP HR, maintenance, shift log
backends/app.py   fake plant systems + demo control page (reseeds on start)                   :8001
```

Run (three terminals, from this folder):
```
pip install -r requirements.txt
python backends/app.py
$env:GEMINI_API_KEY="..."; python agent/server.py
cd web; npm install; npm run dev
```
App: http://localhost:5173 · Control page (fire line warnings, see SAP/tickets change): http://localhost:8001

Add a system: write an MCP server in `mcp_servers/`, add an entry to `SYSTEMS` in `agent/server.py`.
Busy model (503)? The agent retries, then tries `LLM_FALLBACKS` (comma-separated). List models your key can use: `python agent/server.py --models`.
Other models: set `LLM_MODEL`, or `LLM_BASE_URL` for any OpenAI-compatible provider (e.g. Ollama).
