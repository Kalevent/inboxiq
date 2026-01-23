import os
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from mcp.server.fastmcp import FastMCP, Context, ToolError
except ImportError:
    from mcp.server.fastmcp import FastMCP, Context
    try:
        from mcp.types import ToolError
    except ImportError:
        class ToolError(Exception):  # fallback if types module is unavailable
            pass


DATABASE_URL = (
    os.getenv("MCP_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or os.getenv("DATABASE_DEV_URL")
)

if not DATABASE_URL:
    raise RuntimeError(
        "No database URL found. Set MCP_DATABASE_URL or "
        "SQLALCHEMY_DATABASE_URI_CLOUD / SQLALCHEMY_DATABASE_URI."
    )

mcp = FastMCP("sql-mcp")


def get_conn():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        raise ToolError(f"Failed to connect to database: {e}")


@mcp.tool()
def run_query(sql: str) -> list[dict]:
    """
    Execute a SELECT query. Read-only.
    """
    if not sql.strip().lower().startswith("select"):
        raise ToolError("Only SELECT queries are allowed.")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


@mcp.tool()
def execute(sql: str, requires_human: bool = False) -> str:
    """
    Execute INSERT/UPDATE/DELETE. Destructive operations (DELETE/TRUNCATE/DROP or UPDATE without WHERE)
    require `requires_human=true`.
    """
    normalized = sql.strip().lower()
    if normalized.startswith("select"):
        raise ToolError("Use run_query() for SELECT statements")

    is_destructive = (
        normalized.startswith("delete")
        or normalized.startswith("truncate")
        or normalized.startswith("drop")
    )
    update_without_where = normalized.startswith("update") and " where " not in normalized

    if (is_destructive or update_without_where) and not requires_human:
        raise ToolError("Destructive writes require requires_human=true (DELETE/TRUNCATE/DROP or UPDATE without WHERE)")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()
        return f"OK: {cur.rowcount} rows affected"


if __name__ == "__main__":
    mcp.run()
