import httpx
from mcp.server.mcpserver import MCPServer

API = "http://localhost:8001"
mcp = MCPServer("sap-hr")


@mcp.tool()
def list_employees(station: str | None = None) -> list:
    """Employees with role, certified stations, presence today, performance and notes. Optional station filter, e.g. '14'."""
    return httpx.get(f"{API}/hr/employees", params={"station": station} if station else None).json()


@mcp.tool()
def get_employee(employee: str) -> dict:
    """HR record for one employee, by ID (E203) or part of the name."""
    return httpx.get(f"{API}/hr/employees/{employee}").json()


@mcp.tool()
def update_employee(employee: str, performance: str | None = None, notes: str | None = None) -> dict:
    """Update an employee's performance rating and/or notes in SAP HR."""
    return httpx.patch(f"{API}/hr/employees/{employee}", json={"performance": performance, "notes": notes}).json()


@mcp.tool()
def get_station_staffing() -> list:
    """Who is assigned to each station on this shift."""
    return httpx.get(f"{API}/stations").json()


@mcp.tool()
def assign_station(station: str, employee: str) -> dict:
    """Assign a certified, present employee to a station (e.g. station '14', employee 'Nora')."""
    return httpx.post(f"{API}/stations/{station}/assign", json={"employee": employee}).json()


if __name__ == "__main__":
    mcp.run()
