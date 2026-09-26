import httpx
from mcp.server.mcpserver import MCPServer

API = "http://localhost:8001"
mcp = MCPServer("maintenance")


@mcp.tool()
def open_ticket(station: str, description: str) -> dict:
    """Open a maintenance ticket for a station. Returns the ticket number."""
    return httpx.post(f"{API}/tickets", json={"station": station, "text": description}).json()


@mcp.tool()
def list_tickets() -> list:
    """All maintenance tickets, newest first."""
    return httpx.get(f"{API}/tickets").json()


if __name__ == "__main__":
    mcp.run()
