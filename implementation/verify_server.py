from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastmcp import Client

try:
    from .init_db import create_database
    from .mcp_server import build_server
except ImportError:  # pragma: no cover - supports `python verify_server.py`
    from init_db import create_database
    from mcp_server import build_server


def _content_text(value: Any) -> str:
    if hasattr(value, "structured_content") and value.structured_content is not None:
        return json.dumps(value.structured_content, indent=2)
    if hasattr(value, "content"):
        parts = []
        for item in value.content:
            parts.append(getattr(item, "text", str(item)))
        return "\n".join(parts)
    return str(value)


async def run_verification() -> None:
    db_path = Path(__file__).with_name(".verify.sqlite3")
    try:
        create_database(db_path, reset=True)
        server = build_server(db_path)

        async with Client(server) as client:
            await client.ping()
            print("PASS: server responds to ping")

            tools = await client.list_tools()
            tool_names = sorted(tool.name for tool in tools)
            assert tool_names == ["aggregate", "insert", "search"]
            print(f"PASS: tools discovered: {', '.join(tool_names)}")

            resources = await client.list_resources()
            resource_uris = sorted(str(resource.uri) for resource in resources)
            assert "schema://database" in resource_uris
            print(f"PASS: resources discovered: {', '.join(resource_uris)}")

            templates = await client.list_resource_templates()
            template_uris = sorted(str(template.uriTemplate) for template in templates)
            assert "schema://table/{table_name}" in template_uris
            print(f"PASS: resource templates discovered: {', '.join(template_uris)}")

            full_schema = await client.read_resource("schema://database")
            assert "students" in _content_text(full_schema)
            print("PASS: schema://database is readable")

            students_schema = await client.read_resource("schema://table/students")
            assert "cohort" in _content_text(students_schema)
            print("PASS: schema://table/students is readable")

            search_result = await client.call_tool(
                "search",
                {
                    "table": "students",
                    "filters": {"cohort": "A1"},
                    "columns": ["name", "cohort", "score"],
                    "order_by": "score",
                    "descending": True,
                    "limit": 5,
                },
            )
            assert "Ana Nguyen" in _content_text(search_result)
            print("PASS: search returns A1 students")

            insert_result = await client.call_tool(
                "insert",
                {
                    "table": "students",
                    "values": {
                        "name": "Linh Vo",
                        "cohort": "A1",
                        "email": "linh.vo@example.edu",
                        "age": 21,
                        "score": 89.0,
                    },
                },
            )
            assert "Linh Vo" in _content_text(insert_result)
            print("PASS: insert returns inserted row")

            aggregate_result = await client.call_tool(
                "aggregate",
                {
                    "table": "students",
                    "metric": "avg",
                    "column": "score",
                    "group_by": "cohort",
                },
            )
            assert "A1" in _content_text(aggregate_result)
            print("PASS: aggregate returns average score by cohort")

            fastmcp_logger = logging.getLogger("fastmcp")
            previous_level = fastmcp_logger.level
            fastmcp_logger.setLevel(logging.CRITICAL)
            try:
                await client.call_tool("search", {"table": "missing_table"})
            except Exception as exc:
                print(f"PASS: invalid search is rejected: {exc}")
            else:
                raise AssertionError("Invalid search unexpectedly succeeded.")
            finally:
                fastmcp_logger.setLevel(previous_level)
    finally:
        try:
            db_path.unlink()
        except FileNotFoundError:
            pass
        except PermissionError:
            pass


def main() -> None:
    asyncio.run(run_verification())


if __name__ == "__main__":
    main()
