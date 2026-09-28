"""MCP tool wrappers around the customer profile store (Section 4.4).

Single-writer rule (Section 2, constraint #3): upsert_customer_profile is
the write path and must only ever be wired into the DB Manager Agent's
toolset. Worker agents must be given a toolset built from a subset of this
module's tools that excludes upsert_customer_profile entirely -- not just
told not to call it."""

from mcp.server.mcpserver import MCPServer

from db_manager import repository
from schemas.models import CustomerProfile

mcp = MCPServer("db-manager-tools")


@mcp.tool()
def get_customer_profile(customer_id: str) -> CustomerProfile | None:
    """Read-only profile lookup. Safe for worker agents."""
    return repository.get_profile(customer_id)


@mcp.tool()
def upsert_customer_profile(profile: CustomerProfile) -> CustomerProfile:
    """Write path for the customer profile store. DB Manager Agent only."""
    return repository.upsert_profile(profile)


@mcp.tool()
def get_field_history(customer_id: str, field_name: str) -> list[dict]:
    """Read-only versioned-field audit trail lookup. Safe for worker agents."""
    return repository.get_field_history(customer_id, field_name)


if __name__ == "__main__":
    mcp.run()
