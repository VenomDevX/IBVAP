<#
.SYNOPSIS
  One-click local start for IBVAP: Docker -> Supabase -> backend (8002) -> frontend (3001) -> Chrome.

.DESCRIPTION
  Each step is skipped when that service is already up, except the frontend:
  whatever holds port 3001 is always killed and a fresh server is started.
  Run through start-ibvap.bat, or directly:
    powershell -ExecutionPolicy Bypass -File scripts\start-ibvap.ps1 [-Rebuild] [-NoBrowser]
#>
param(
    [switch]$Rebuild,     # always rebuild the frontend
    [switch]$NoBrowser    # do not open Chrome
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDir  = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$appUrl      = "http://localhost:3001"

function Step($text)  { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Info($text)  { Write-Host "    $text" }
function Done($text)  { Write-Host "    $text" -ForegroundColor Green }

function Test-Http($url, $timeoutSec = 3) {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec $timeoutSec
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Wait-Until([scriptblock]$condition, [int]$timeoutSec, [string]$what) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (& $condition) { return }
        Start-Sleep -Seconds 2
    }
    throw "$what did not become ready within $timeoutSec seconds."
}

function Test-Docker {
    & docker info *> $null
    return $LASTEXITCODE -eq 0
}

# ---------------------------------------------------------------- 1. Docker
Step "Docker"
if (Test-Docker) {
    Done "Docker is running."
} else {
    $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        throw "Docker is not running and Docker Desktop was not found at $dockerDesktop."
    }
    Info "Starting Docker Desktop (this can take a minute)..."
    Start-Process -FilePath $dockerDesktop | Out-Null
    Wait-Until { Test-Docker } 240 "Docker"
    Done "Docker is running."
}

# ---------------------------------------------------------------- 2. Supabase
Step "Supabase (auth)"
if (Test-Http "http://127.0.0.1:54321/auth/v1/health") {
    Done "Supabase is running on 54321."
} else {
    Info "Starting Supabase containers..."
    Push-Location $projectRoot
    try {
        & npx.cmd --yes supabase start
        if ($LASTEXITCODE -ne 0) { throw "npx supabase start failed." }
    } finally {
        Pop-Location
    }
    Wait-Until { Test-Http "http://127.0.0.1:54321/auth/v1/health" } 120 "Supabase"
    Done "Supabase is running on 54321."
}

# ---------------------------------------------------------------- 3. Backend
Step "Backend API (8002)"
if (Test-Http "http://127.0.0.1:8002/api/health/live") {
    Done "Backend is already running."
} else {
    $pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $pythonExe)) { $pythonExe = Join-Path $backendDir "venv\Scripts\python.exe" }
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw "Python virtual environment not found. Create .venv and install backend/requirements.txt first."
    }
    Info "Starting backend (logs: backend\.local-backend.err.log)..."
    $backend = Start-Process -FilePath $pythonExe `
        -ArgumentList "main.py", "--port", "8002" `
        -WorkingDirectory $backendDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $backendDir ".local-backend.out.log") `
        -RedirectStandardError (Join-Path $backendDir ".local-backend.err.log") `
        -PassThru
    Wait-Until {
        if ($backend.HasExited) { throw "Backend exited during startup. See backend\.local-backend.err.log." }
        Test-Http "http://127.0.0.1:8002/api/health/live"
    } 180 "Backend API"
    Done "Backend API is up. Cameras keep loading in the background."
}

# ---------------------------------------------------------------- 4. Free port 3001
Step "Port 3001"
$listeners = Get-NetTCPConnection -LocalPort 3001 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
if ($listeners) {
    foreach ($processId in $listeners) {
        $name = (Get-Process -Id $processId -ErrorAction SilentlyContinue).ProcessName
        Info "Stopping old process on 3001: $name (PID $processId)"
        & taskkill.exe /PID $processId /T /F | Out-Null
    }
    Wait-Until { -not (Get-NetTCPConnection -LocalPort 3001 -State Listen -ErrorAction SilentlyContinue) } 20 "Port 3001 release"
    Done "Port 3001 is free."
} else {
    Done "Nothing was running on 3001."
}

# ---------------------------------------------------------------- 5. Frontend
Step "Frontend (3001)"
Push-Location $frontendDir
try {
    if (-not (Test-Path -LiteralPath "node_modules")) {
        Info "Installing frontend packages..."
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    }

    $builtAt = if (Test-Path -LiteralPath "out\index.html") { (Get-Item "out\index.html").LastWriteTime } else { $null }
    $sources = @("app", "src", "public") | Where-Object { Test-Path $_ } |
        ForEach-Object { Get-ChildItem $_ -Recurse -File }
    $sources += Get-Item "package.json", "next.config.ts" -ErrorAction SilentlyContinue
    $newestSource = ($sources | Measure-Object -Property LastWriteTime -Maximum).Maximum

    if ($Rebuild -or -not $builtAt -or $newestSource -gt $builtAt) {
        Info "Building the frontend (the build is missing or older than the code)..."
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    } else {
        Info "Build is up to date."
    }

    # Its own window so the server keeps running after this script ends.
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/k", "title IBVAP frontend (3001) && node scripts\serve-static.mjs" `
        -WorkingDirectory $frontendDir `
        -WindowStyle Minimized | Out-Null
    Wait-Until { Test-Http "http://127.0.0.1:3001/login/" } 30 "Frontend"
    Done "Frontend is serving $appUrl (minimized window 'IBVAP frontend')."
} finally {
    Pop-Location
}

# ---------------------------------------------------------------- 6. Chrome
if (-not $NoBrowser) {
    Step "Chrome"
    $chrome = @(
        (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
        (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if ($chrome) {
        Start-Process -FilePath $chrome -ArgumentList $appUrl | Out-Null
        Done "Opened $appUrl in Chrome."
    } else {
        Start-Process $appUrl | Out-Null
        Done "Chrome not found; opened $appUrl in the default browser."
    }
}

Write-Host "`nIBVAP is running. Sign in at $appUrl" -ForegroundColor Green
