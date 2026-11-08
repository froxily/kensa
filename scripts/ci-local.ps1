#Requires -Version 5.1
<#
.SYNOPSIS
  Runs every check the CI pipeline runs, locally. Installs and downloads nothing.

.DESCRIPTION
  Backend: ruff (lint + format), mypy (strict), pytest.
  Frontend: eslint, prettier, tsc, vitest, vite build, Playwright end-to-end + axe.
  Infra: docker compose config validation.
  DB-backed tests are skipped (with a reason) when the local PostgreSQL is not running.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ci-local.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ci-local.ps1 -SkipFrontend
#>
[CmdletBinding()]
param(
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    [switch]$SkipE2E,
    [switch]$SkipInfra
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$results = New-Object System.Collections.Generic.List[object]

function Invoke-Step {
    param([string]$Name, [string]$WorkDir, [scriptblock]$Command)
    Write-Host ""
    Write-Host "=== $Name" -ForegroundColor Cyan
    $watch = [Diagnostics.Stopwatch]::StartNew()
    Push-Location $WorkDir
    try {
        $global:LASTEXITCODE = 0
        & $Command
        $code = $LASTEXITCODE
    } catch {
        Write-Host $_ -ForegroundColor Red
        $code = 1
    } finally {
        Pop-Location
    }
    $watch.Stop()
    $status = if ($code -eq 0) { "PASS" } else { "FAIL (exit $code)" }
    $results.Add([pscustomobject]@{
        Step    = $Name
        Result  = $status
        Seconds = [math]::Round($watch.Elapsed.TotalSeconds, 1)
    })
}

function Add-Failure {
    param([string]$Name, [string]$Reason)
    Write-Host ""
    Write-Host "=== $Name" -ForegroundColor Cyan
    Write-Host $Reason -ForegroundColor Red
    $results.Add([pscustomobject]@{ Step = $Name; Result = "FAIL ($Reason)"; Seconds = 0 })
}

if (-not $SkipBackend) {
    if (-not (Test-Path (Join-Path $backend ".venv"))) {
        Add-Failure "backend" "backend/.venv missing - run 'uv sync' in backend/ (approved dependencies only)"
    } else {
        # --no-sync: never install or update packages from this script.
        Invoke-Step "backend: ruff check"   $backend { uv run --no-sync ruff check . ../scripts }
        Invoke-Step "backend: ruff format"  $backend { uv run --no-sync ruff format --check . ../scripts }
        Invoke-Step "backend: mypy"         $backend { uv run --no-sync mypy }
        Invoke-Step "backend: pytest"       $backend { uv run --no-sync pytest }
    }
}

if (-not $SkipFrontend) {
    if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
        Add-Failure "frontend" "frontend/node_modules missing - run 'npm install' in frontend/ (approved dependencies only)"
    } else {
        Invoke-Step "frontend: eslint"      $frontend { npm run -s lint }
        Invoke-Step "frontend: prettier"    $frontend { npm run -s format:check }
        Invoke-Step "frontend: typecheck"   $frontend { npm run -s typecheck }
        Invoke-Step "frontend: vitest"      $frontend { npm run -s test }
        Invoke-Step "frontend: build"       $frontend { npm run -s build }
        if (-not $SkipE2E) {
            # Real frontend + real backend (rules-only provider, own database) + axe checks.
            # Needs the Compose database; uses the cached Playwright Chromium (no download).
            Invoke-Step "frontend: e2e + axe" $frontend { npx playwright test }
        }
    }
}

if (-not $SkipInfra) {
    Invoke-Step "infra: compose config" $root { docker compose config --quiet }
}

Write-Host ""
Write-Host "=== Summary" -ForegroundColor Cyan
$results | Format-Table -AutoSize | Out-String | Write-Host
$failed = @($results | Where-Object { $_.Result -ne "PASS" })
if ($failed.Count -gt 0) {
    Write-Host "$($failed.Count) step(s) failed." -ForegroundColor Red
    exit 1
}
Write-Host "All $($results.Count) steps passed." -ForegroundColor Green
exit 0
