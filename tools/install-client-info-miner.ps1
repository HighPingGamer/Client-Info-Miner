$ErrorActionPreference = "Stop"

function Write-Step($text) {
    Write-Host ""
    Write-Host "== $text ==" -ForegroundColor Cyan
}

function Read-Choice($prompt, $valid) {
    do {
        $choice = Read-Host $prompt
    } while ($valid -notcontains $choice)
    return $choice
}

function Copy-Package($sourceRoot, $installRoot) {
    Write-Step "Copying Client Info Miner"
    New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
    $exclude = @(".git", ".venv", "runtime", "Scraper Data", "__pycache__", ".pytest_cache")
    Get-ChildItem -LiteralPath $sourceRoot -Force | ForEach-Object {
        if ($exclude -contains $_.Name) { return }
        $dest = Join-Path $installRoot $_.Name
        Copy-Item -LiteralPath $_.FullName -Destination $dest -Recurse -Force
    }
}

function Ensure-PortablePython($installRoot) {
    Write-Step "Checking portable Python"
    $runtime = Join-Path $installRoot "runtime"
    $pythonDir = Join-Path $runtime "python"
    $pythonExe = Join-Path $pythonDir "python.exe"
    if (Test-Path $pythonExe) {
        Write-Host "Portable Python already exists."
        return $pythonExe
    }

    New-Item -ItemType Directory -Force -Path $runtime | Out-Null
    $zipPath = Join-Path $runtime "python-3.11.9-embed-amd64.zip"
    $pythonUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"

    Write-Host "Downloading portable Python 3.11.9..."
    Invoke-WebRequest -Uri $pythonUrl -OutFile $zipPath
    Expand-Archive -LiteralPath $zipPath -DestinationPath $pythonDir -Force

    $pth = Join-Path $pythonDir "python311._pth"
    if (Test-Path $pth) {
        (Get-Content $pth) -replace "#import site", "import site" | Set-Content $pth
    }

    $getPip = Join-Path $runtime "get-pip.py"
    Write-Host "Installing pip into portable Python..."
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
    & $pythonExe $getPip
    if ($LASTEXITCODE -ne 0) { throw "pip installation failed" }
    return $pythonExe
}

function Install-PythonPackages($pythonExe, $installRoot) {
    Write-Step "Installing Python packages"
    & $pythonExe -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
    & $pythonExe -m pip install -r (Join-Path $installRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Python package installation failed" }

    Write-Step "Installing Playwright browser"
    & $pythonExe -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "Playwright browser installation failed" }
}

function Test-Ollama {
    $cmd = Get-Command "ollama" -ErrorAction SilentlyContinue
    return $null -ne $cmd
}

function Setup-Ollama {
    Write-Step "Checking Ollama"
    if (Test-Ollama) {
        Write-Host "Ollama is installed."
    } else {
        Write-Host "Ollama is needed for the report builder AI step."
        $install = Read-Choice "Install Ollama using winget if available? 1 = yes, 2 = skip" @("1", "2")
        if ($install -eq "1") {
            $winget = Get-Command "winget" -ErrorAction SilentlyContinue
            if ($null -eq $winget) {
                Write-Host "winget was not found. Please install Ollama manually from https://ollama.com/download"
            } else {
                winget install Ollama.Ollama --accept-source-agreements --accept-package-agreements
            }
        }
    }

    if (Test-Ollama) {
        $pull = Read-Choice "Pull the llama3.1 model now? This can be large. 1 = yes, 2 = skip" @("1", "2")
        if ($pull -eq "1") {
            ollama pull llama3.1
        }
    }
}

function Create-Shortcut($installRoot) {
    Write-Step "Creating launcher shortcut"
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktop "Client Info Miner.lnk"
    $target = Join-Path $installRoot "Run-ClientInfoMiner.cmd"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $target
    $shortcut.WorkingDirectory = $installRoot
    $shortcut.Description = "Run Client Info Miner"
    $shortcut.Save()
    Write-Host "Shortcut created: $shortcutPath"
}

$sourceRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Write-Host "Client Info Miner installer"
Write-Host "This installs a local copy with portable Python and dependencies."

$choice = Read-Choice "Install location: 1 = Desktop, 2 = choose a drive/folder" @("1", "2")
if ($choice -eq "1") {
    $installRoot = Join-Path ([Environment]::GetFolderPath("Desktop")) "Client Info Miner"
} else {
    $custom = Read-Host "Paste the folder or drive path to install into"
    if ([string]::IsNullOrWhiteSpace($custom)) { throw "No install path provided" }
    $installRoot = Join-Path $custom "Client Info Miner"
}

Copy-Package $sourceRoot $installRoot
$pythonExe = Ensure-PortablePython $installRoot
Install-PythonPackages $pythonExe $installRoot
Setup-Ollama
Create-Shortcut $installRoot

Write-Step "Done"
Write-Host "Installed to: $installRoot"
Write-Host "Double-click 'Client Info Miner' on your Desktop, or run:"
Write-Host (Join-Path $installRoot "Run-ClientInfoMiner.cmd")
