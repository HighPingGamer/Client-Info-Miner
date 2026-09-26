$ErrorActionPreference = "Stop"

function Find-Python($root) {
    $portable = Join-Path $root "runtime\python\python.exe"
    if (Test-Path $portable) { return $portable }
    $python = Get-Command "python" -ErrorAction SilentlyContinue
    if ($python) { return $python.Source }
    $py = Get-Command "py" -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    throw "Python was not found. Please run Install-ClientInfoMiner.cmd first."
}

function Run-Step($pythonExe, $scriptPath) {
    & $pythonExe $scriptPath
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $scriptPath"
    }
}

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$pythonExe = Find-Python $root
$scraper = Join-Path $root "src\scrapper.py"
$reportBuilder = Join-Path $root "src\report_builder.py"
$dataDir = Join-Path $root "Scraper Data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

Write-Host ""
Write-Host "Client Info Miner" -ForegroundColor Cyan
Write-Host "Data folder: $dataDir"
Write-Host ""
Write-Host "1. Scan a company website"
Write-Host "2. Build report from scanned data"
Write-Host "3. Scan website, then build report"
Write-Host "4. Open data folder"
Write-Host "5. Exit"
Write-Host ""
$choice = Read-Host "Choose an option"

switch ($choice) {
    "1" {
        Run-Step $pythonExe $scraper
    }
    "2" {
        Run-Step $pythonExe $reportBuilder
    }
    "3" {
        Run-Step $pythonExe $scraper
        Run-Step $pythonExe $reportBuilder
    }
    "4" {
        Invoke-Item $dataDir
    }
    "5" {
        return
    }
    default {
        Write-Host "Unknown option."
    }
}
