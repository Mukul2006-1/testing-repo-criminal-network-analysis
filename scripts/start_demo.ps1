# Demo startup for Windows (no Docker needed).
# Starts Neo4j (local install), the FastAPI backend (loads .env) and both
# frontends. Re-run safely: already-running services are left alone.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Neo4jHome = "C:\Users\Lenovo\neo4j-local\neo4j-community-5.26.29"

function Test-Port($Port) {
    try {
        $c = New-Object Net.Sockets.TcpClient
        $r = $c.BeginConnect("127.0.0.1", $Port, $null, $null)
        $ok = $r.AsyncWaitHandle.WaitOne(1500) -and $c.Connected
        $c.Close()
        return $ok
    } catch { return $false }
}

# 1. Neo4j (Bolt 7687)
if (-not (Test-Port 7687)) {
    $jdk = Get-ChildItem "C:\Users\Lenovo\neo4j-local\jdk" -Directory |
        Select-Object -First 1 -ExpandProperty FullName
    $env:JAVA_HOME = $jdk
    Write-Output "Starting Neo4j..."
    Start-Process -FilePath "$Neo4jHome\bin\neo4j.bat" -ArgumentList "console" `
        -WorkingDirectory $Neo4jHome -WindowStyle Hidden
    for ($i = 0; $i -lt 24 -and -not (Test-Port 7687); $i++) { Start-Sleep 5 }
    if (-not (Test-Port 7687)) { throw "Neo4j did not open Bolt 7687 in time." }
} else { Write-Output "Neo4j already up (7687)." }

# 2. Backend (8000) with .env
if (-not (Test-Port 8000)) {
    Get-Content "$Repo\.env" | Where-Object { $_ -match "=" } | ForEach-Object {
        $k, $v = $_ -split "=", 2; Set-Item "env:$k" $v
    }
    if (-not $env:NEO4J_PASSWORD) { throw ".env is missing NEO4J_PASSWORD." }
    Write-Output "Starting backend..."
    Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn",
        "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
        -WorkingDirectory "$Repo\backend"
    Start-Sleep 8
}
$health = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 10 |
    Select-Object -ExpandProperty Content
Write-Output "Backend: $health"

# 3. Frontends (5173 classic, 5174 reimagined)
foreach ($app in @(@{dir = "frontend"; port = 5173}, @{dir = "frontend-reimagined"; port = 5174})) {
    if (-not (Test-Port $app.port)) {
        Write-Output "Starting $($app.dir)..."
        Start-Process -FilePath "cmd" -ArgumentList "/c", "npm", "run", "dev",
            "--", "--host", "127.0.0.1", "--port", $app.port `
            -WorkingDirectory "$Repo\$($app.dir)"
    } else { Write-Output "$($app.dir) already up ($($app.port))." }
}

Write-Output ""
Write-Output "Demo ready:"
Write-Output "  Classic UI:    http://localhost:5173"
Write-Output "  Reimagined UI: http://localhost:5174"
Write-Output "  Backend:       http://localhost:8000/health"
Write-Output "  Neo4j browser: http://localhost:7474"
