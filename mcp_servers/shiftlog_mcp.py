import httpx
from mcp.server.mcpserver import MCPServer

API = "http://localhost:8001"
mcp = MCPServer("shift-log")


@mcp.tool()
def get_shift_log(shift: str = "current") -> dict:
    """Issues and notes of a shift ('current' = the active shift, or an id like 2026-09-25-night), with open items
    carried from earlier shifts, every logged action/response, and the handoff received from the previous shift."""
    return httpx.get(f"{API}/shift/{shift}").json()


@mcp.tool()
def get_handoffs(days: int = 3) -> list:
    """Handoff reports passed between shifts in the last N days, oldest first."""
    return httpx.get(f"{API}/handoffs", params={"days": days}).json()


@mcp.tool()
def close_issue(note_id: int) -> dict:
    """Mark an issue/note as resolved (moves it to 'Closed today')."""
    return httpx.patch(f"{API}/notes/{note_id}", json={"status": "closed"}).json()


if __name__ == "__main__":
    mcp.run()
