import httpx
from mcp.server.mcpserver import MCPServer

API = "http://localhost:8001"
mcp = MCPServer("production-line")


@mcp.tool()
def get_line_status() -> dict:
    """Live status of the Doors line: output vs target and state of each station."""
    return httpx.get(f"{API}/line/status").json()


if __name__ == "__main__":
    mcp.run()
