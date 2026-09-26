import httpx
from mcp.server.mcpserver import MCPServer

API = "http://localhost:8001"
mcp = MCPServer("shift-log")


@mcp.tool()
def get_shift_log(shift: str = "d26") -> dict:
    """Issues and notes of a shift (today 'd26'), with open items carried from earlier shifts and every logged action/response."""
    return httpx.get(f"{API}/shift/{shift}").json()


@mcp.tool()
def get_handoffs(days: int = 3) -> list:
    """Handoff reports passed between shifts in the last N days."""
    return httpx.get(f"{API}/handoffs", params={"days": days}).json()


@mcp.tool()
def close_issue(note_id: int) -> dict:
    """Mark an issue/note as resolved (moves it to 'Closed today')."""
    return httpx.patch(f"{API}/notes/{note_id}", json={"status": "closed"}).json()


if __name__ == "__main__":
    mcp.run()
