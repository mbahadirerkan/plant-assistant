import httpx
from mcp.server.mcpserver import MCPServer

API = "http://localhost:8001/log"
mcp = MCPServer("handover")


@mcp.tool()
def get_shift_events(hours: int = 8) -> list:
    """All events logged during the current shift (last N hours). Use to write a shift report."""
    return httpx.get(f"{API}/events", params={"hours": hours}).json()


@mcp.tool()
def get_reports(days: int = 3) -> list:
    """Saved shift reports from the last N days."""
    return httpx.get(f"{API}/reports", params={"days": days}).json()


@mcp.tool()
def save_report(title: str, content: str) -> dict:
    """Save a shift/handover report. Returns its id and a pdf_url."""
    return httpx.post(f"{API}/reports", json={"title": title, "content": content}).json()


if __name__ == "__main__":
    mcp.run()
