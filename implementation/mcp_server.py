from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

try:
    from .db import SQLiteAdapter, ValidationError
    from .init_db import DEFAULT_DB_PATH, create_database
except ImportError:  # pragma: no cover - supports `python mcp_server.py`
    from db import SQLiteAdapter, ValidationError
    from init_db import DEFAULT_DB_PATH, create_database


def _resolve_db_path(db_path: str | Path | None = None) -> Path:
    return Path(db_path or os.environ.get("SQLITE_LAB_DB") or DEFAULT_DB_PATH)


def _validation_error(exc: ValidationError) -> ToolError:
    return ToolError(str(exc))


def build_server(db_path: str | Path | None = None) -> FastMCP:
    resolved_db_path = _resolve_db_path(db_path)
    if not resolved_db_path.exists():
        create_database(resolved_db_path)

    adapter = SQLiteAdapter(resolved_db_path)
    mcp = FastMCP(
        "SQLite Lab MCP Server",
        instructions=(
            "Use search, insert, aggregate, and schema resources to inspect "
            "the lab SQLite database."
        ),
        mask_error_details=False,
    )

    @mcp.tool(name="search")
    def search(
        table: str,
        filters: dict[str, Any] | list[dict[str, Any]] | None = None,
        columns: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        """
        Search rows in a validated table.

        Filters can be a shorthand object such as {"cohort": "A1"} or a list
        like [{"column": "score", "operator": "gte", "value": 90}].
        Supported operators: eq, ne, gt, gte, lt, lte, like, in, not_in,
        is_null, not_null.
        """
        try:
            return adapter.search(
                table=table,
                filters=filters,
                columns=columns,
                limit=limit,
                offset=offset,
                order_by=order_by,
                descending=descending,
            )
        except ValidationError as exc:
            raise _validation_error(exc) from exc

    @mcp.tool(name="insert")
    def insert(table: str, values: dict[str, Any]) -> dict[str, Any]:
        """Insert one row into a validated table and return the inserted row."""
        try:
            return adapter.insert(table=table, values=values)
        except ValidationError as exc:
            raise _validation_error(exc) from exc

    @mcp.tool(name="aggregate")
    def aggregate(
        table: str,
        metric: str,
        column: str | None = None,
        filters: dict[str, Any] | list[dict[str, Any]] | None = None,
        group_by: str | list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Compute count, avg, sum, min, or max for a validated table.

        Use column for every metric except count(*). group_by accepts one
        column name or a list of column names.
        """
        try:
            return adapter.aggregate(
                table=table,
                metric=metric,
                column=column,
                filters=filters,
                group_by=group_by,
            )
        except ValidationError as exc:
            raise _validation_error(exc) from exc

    @mcp.resource("schema://database")
    def database_schema() -> str:
        """Return the full database schema as formatted JSON."""
        return json.dumps(adapter.database_schema(), indent=2)

    @mcp.resource("schema://table/{table_name}")
    def table_schema(table_name: str) -> str:
        """Return one table schema as formatted JSON."""
        try:
            return json.dumps(adapter.get_table_schema(table_name), indent=2)
        except ValidationError as exc:
            raise _validation_error(exc) from exc

    return mcp


mcp = build_server()


if __name__ == "__main__":
    mcp.run()
