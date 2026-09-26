import httpx
from mcp.server.mcpserver import MCPServer

API = "http://localhost:8001/hr"
mcp = MCPServer("sap-hr")


@mcp.tool()
def list_employees(line: str | None = None) -> list:
    """List employees with role, line, certifications and performance. Optional line filter, e.g. 'L3'."""
    return httpx.get(f"{API}/employees", params={"line": line} if line else None).json()


@mcp.tool()
def get_employee_report(employee: str) -> dict:
    """HR report for one employee. Accepts an ID (E101) or part of a name."""
    return httpx.get(f"{API}/employees/{employee}").json()


@mcp.tool()
def update_employee(employee: str, performance: str | None = None, notes: str | None = None) -> dict:
    """Update an employee's performance rating and/or notes in SAP. Only call after the supervisor explicitly confirmed."""
    return httpx.patch(f"{API}/employees/{employee}", json={"performance": performance, "notes": notes}).json()


if __name__ == "__main__":
    mcp.run()
