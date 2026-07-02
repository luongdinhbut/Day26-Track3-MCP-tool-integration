from __future__ import annotations

import asyncio

from fastmcp import Client

from implementation.init_db import create_database
from implementation.mcp_server import build_server


def test_fastmcp_tools_and_resources_are_discoverable(tmp_path):
    async def run():
        db_path = tmp_path / "lab.sqlite3"
        create_database(db_path, reset=True)
        server = build_server(db_path)

        async with Client(server) as client:
            tools = await client.list_tools()
            assert sorted(tool.name for tool in tools) == [
                "aggregate",
                "insert",
                "search",
            ]

            resources = await client.list_resources()
            assert "schema://database" in {str(resource.uri) for resource in resources}

            templates = await client.list_resource_templates()
            assert "schema://table/{table_name}" in {
                str(template.uriTemplate) for template in templates
            }

            schema = await client.read_resource("schema://table/students")
            assert "cohort" in str(schema)

            result = await client.call_tool(
                "aggregate",
                {"table": "students", "metric": "count", "group_by": "cohort"},
            )
            assert "A1" in str(result)

    asyncio.run(run())

