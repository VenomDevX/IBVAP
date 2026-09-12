param(
    [switch]$Dev,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    $pythonExe = Join-Path $backendDir "venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python virtual environment not found. Create .venv and install backend/requirements.txt first."
}

$backendProcess = $null
$backendAlreadyRunning = $false
try {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8002/api/health" -TimeoutSec 2
        $backendAlreadyRunning = $health.status -eq "ok"
    } catch {
        $backendAlreadyRunning = $false
    }

    if (-not $backendAlreadyRunning) {
        $backendProcess = Start-Process `
            -FilePath $pythonExe `
            -ArgumentList "main.py", "--port", "8002" `
            -WorkingDirectory $backendDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $backendDir ".local-backend.out.log") `
            -RedirectStandardError (Join-Path $backendDir ".local-backend.err.log") `
            -PassThru

        $ready = $false
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            Start-Sleep -Seconds 1
            if ($backendProcess.HasExited) {
                throw "Backend exited during startup. See backend/.local-backend.err.log."
            }
            try {
                $health = Invoke-RestMethod -Uri "http://127.0.0.1:8002/api/health" -TimeoutSec 2
                if ($health.status -eq "ok") {
                    $ready = $true
                    break
                }
            } catch {}
        }
        if (-not $ready) {
            throw "Backend did not become healthy on port 8002 within 60 seconds."
        }
    }

    Push-Location $frontendDir
    try {
        if ($Dev) {
            & npm.cmd run dev
        } else {
            if (-not $SkipBuild) {
                $previousApiBase = $env:NEXT_PUBLIC_API_BASE
                $previousWsBase = $env:NEXT_PUBLIC_WS_BASE
                try {
                    # A local static build talks directly to FastAPI. Docker's
                    # nginx build still uses frontend/.env.production instead.
                    $env:NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8002"
                    $env:NEXT_PUBLIC_WS_BASE = "ws://127.0.0.1:8002"
                    & npm.cmd run build
                    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
                } finally {
                    $env:NEXT_PUBLIC_API_BASE = $previousApiBase
                    $env:NEXT_PUBLIC_WS_BASE = $previousWsBase
                }
            }
            & $pythonExe -m http.server 3001 --bind 127.0.0.1 --directory (Join-Path $frontendDir "out")
        }
    } finally {
        Pop-Location
    }
} finally {
    if ($backendProcess -and -not $backendProcess.HasExited) {
        & taskkill.exe /PID $backendProcess.Id /T /F | Out-Null
    }
}
