$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
    $Python = "python"
}

npx -y @modelcontextprotocol/inspector $Python (Join-Path $ScriptDir "mcp_server.py")

