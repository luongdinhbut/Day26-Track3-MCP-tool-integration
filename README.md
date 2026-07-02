# SQLite FastMCP Database Lab

This repository contains a completed FastMCP lab server backed by SQLite. It
exposes three MCP tools (`search`, `insert`, and `aggregate`) plus schema
resources for the full database and individual tables.

## Project Structure

```text
implementation/
  __init__.py
  db.py                 # SQLite adapter, validation, safe SQL construction
  init_db.py            # reproducible schema and seed data
  mcp_server.py         # FastMCP server
  verify_server.py      # repeatable MCP client smoke test
  start_inspector.ps1   # MCP Inspector helper for PowerShell
  start_inspector.sh    # MCP Inspector helper for bash
  tests/
    test_db.py
    test_server.py
pseudocode/             # original starter pseudocode
requirements.txt
pytest.ini
```

## Setup

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe implementation\init_db.py
```

Bash:

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe implementation/init_db.py
```

The database is created at `implementation/lab.sqlite3`. The MCP server also
creates it automatically if the file is missing.

To use a different database path, set `SQLITE_LAB_DB` before starting the
server.

## Run The Server

```powershell
.\.venv\Scripts\python.exe implementation\mcp_server.py
```

FastMCP runs over stdio by default, which is the transport expected by local MCP
clients.

## Tools

### `search`

Search validated tables with filters, selected columns, ordering, limit, and
offset.

Example arguments:

```json
{
  "table": "students",
  "filters": { "cohort": "A1" },
  "columns": ["name", "cohort", "score"],
  "order_by": "score",
  "descending": true,
  "limit": 5
}
```

Supported filter operators:

```text
eq, ne, gt, gte, lt, lte, like, in, not_in, is_null, not_null
```

Filters can use shorthand:

```json
{ "cohort": "A1" }
```

Or explicit filter objects:

```json
[
  { "column": "score", "operator": "gte", "value": 90 }
]
```

### `insert`

Insert one row into a validated table and return the inserted row.

Example arguments:

```json
{
  "table": "students",
  "values": {
    "name": "Linh Vo",
    "cohort": "A1",
    "email": "linh.vo@example.edu",
    "age": 21,
    "score": 89.0
  }
}
```

### `aggregate`

Compute `count`, `avg`, `sum`, `min`, or `max`. `avg` and `sum` require a
numeric column.

Example arguments:

```json
{
  "table": "students",
  "metric": "avg",
  "column": "score",
  "group_by": "cohort"
}
```

## Resources

The server exposes:

```text
schema://database
schema://table/{table_name}
```

Examples:

```text
schema://database
schema://table/students
schema://table/courses
schema://table/enrollments
```

## Safety And Validation

The SQLite adapter rejects:

- unknown table names
- unknown column names
- unsupported filter operators
- invalid aggregate requests
- empty inserts
- invalid pagination values

Values are always bound through SQLite parameters. Table and column identifiers
are only interpolated after they have been checked against the live schema.

## Verification

Run automated tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Run the MCP client smoke test:

```powershell
.\.venv\Scripts\python.exe implementation\verify_server.py
```

Expected smoke-test checks:

- server responds to ping
- `search`, `insert`, and `aggregate` are discoverable
- `schema://database` is discoverable and readable
- `schema://table/{table_name}` is discoverable and readable
- valid `search`, `insert`, and `aggregate` calls succeed
- invalid table search is rejected with a clear error

## MCP Inspector

PowerShell:

```powershell
.\implementation\start_inspector.ps1
```

Bash:

```bash
./implementation/start_inspector.sh
```

Manual equivalent:

```bash
npx -y @modelcontextprotocol/inspector /ABSOLUTE/PATH/TO/python /ABSOLUTE/PATH/TO/implementation/mcp_server.py
```

In Inspector, confirm that the three tools and both schema resources are visible,
then run the example calls above plus an invalid call such as:

```json
{ "table": "missing_table" }
```

## Client Configuration Examples

Use absolute paths for local MCP clients.

### Claude Code `.mcp.json`

```json
{
  "mcpServers": {
    "sqlite-lab": {
      "type": "stdio",
      "command": "/ABSOLUTE/PATH/TO/.venv/Scripts/python.exe",
      "args": ["/ABSOLUTE/PATH/TO/implementation/mcp_server.py"],
      "env": {}
    }
  }
}
```

### Codex `~/.codex/config.toml`

```toml
[mcp_servers.sqlite_lab]
command = "/ABSOLUTE/PATH/TO/.venv/Scripts/python.exe"
args = ["/ABSOLUTE/PATH/TO/implementation/mcp_server.py"]
```

### Gemini CLI

```bash
gemini mcp add sqlite-lab /ABSOLUTE/PATH/TO/.venv/Scripts/python.exe /ABSOLUTE/PATH/TO/implementation/mcp_server.py --description "SQLite lab FastMCP server" --timeout 10000
gemini mcp list
gemini --allowed-mcp-server-names sqlite-lab --yolo -p "Use the sqlite-lab MCP server and show me the top 2 students by score."
```

## Demo Script

For a short demo video or live walkthrough:

1. Run `implementation/init_db.py`.
2. Run `implementation/verify_server.py` and show the PASS lines.
3. Open MCP Inspector and show tool/resource discovery.
4. Call `search` for students in cohort `A1`.
5. Call `insert` with a new student.
6. Call `aggregate` for average `score` grouped by `cohort`.
7. Read `schema://database` and `schema://table/students`.
8. Call `search` with `missing_table` to show validation.

