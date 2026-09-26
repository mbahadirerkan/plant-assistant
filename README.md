# Plant Supervisor Assistant (MVP)

```
backends/app.py      fake SAP HR + line dashboard + shift log  (:8001, reseeds on start)
mcp_servers/*.py     one MCP adapter per system
agent/server.py      threads + Claude tool loop, chat UI       (:8000)
```

Run (two terminals):
```
pip install -r requirements.txt
python backends/app.py
$env:GEMINI_API_KEY="..."; python agent/server.py
```
Chat: http://localhost:8000 · Demo control / fake SAP: http://localhost:8001 ("Fire" buttons send line warnings)

Add a capability: new MCP server in `mcp_servers/`, add its filename to `MCP_SERVERS` in `agent/server.py`.
