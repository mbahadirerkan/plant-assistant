import httpx
from mcp.server.mcpserver import MCPServer

API = "http://localhost:8001"
mcp = MCPServer("production-line")


@mcp.tool()
def get_line_status() -> dict:
    """Current status, output and target of every production line."""
    return httpx.get(f"{API}/line/status").json()


@mcp.tool()
def get_recent_events(hours: int = 72, line: str | None = None) -> list:
    """Production events (warnings, faults, HR changes) from the last N hours, optionally for one line."""
    return httpx.get(f"{API}/log/events", params={"hours": hours, **({"line": line} if line else {})}).json()


if __name__ == "__main__":
    mcp.run()
