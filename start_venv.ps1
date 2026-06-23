param(
    [switch]$Install,
    [switch]$NoShell
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"
$RunningOnWindows = if (Get-Variable IsWindows -ErrorAction SilentlyContinue) {
    $IsWindows
} else {
    $env:OS -eq "Windows_NT"
}

Set-Location $ProjectRoot

$PreferredVenvDirectory = Join-Path $ProjectRoot "venv"
$DefaultVenvDirectory = Join-Path $ProjectRoot ".venv"

if (Test-Path -LiteralPath $PreferredVenvDirectory) {
    $VenvDirectory = $PreferredVenvDirectory
} else {
    $VenvDirectory = $DefaultVenvDirectory
}

if ($RunningOnWindows) {
    $VenvPython = Join-Path $VenvDirectory "Scripts\python.exe"
    $ActivateScript = Join-Path $VenvDirectory "Scripts\Activate.ps1"
} else {
    $VenvPython = Join-Path $VenvDirectory "bin/python"
    $ActivateScript = Join-Path $VenvDirectory "bin/Activate.ps1"
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    $Python = Get-Command python3 -ErrorAction SilentlyContinue
    if (-not $Python) {
        $Python = Get-Command python -ErrorAction SilentlyContinue
    }
    if (-not $Python) {
        throw "Python was not found on PATH. Install Python 3.11 or newer and try again."
    }

    Write-Host "Creating virtual environment in $VenvDirectory..." -ForegroundColor Cyan
    & $Python.Source -m venv $VenvDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Python could not create the virtual environment."
    }

    $Install = $true
}

if ($Install) {
    Write-Host "Installing project dependencies..." -ForegroundColor Cyan
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "pip could not be upgraded."
    }

    & $VenvPython -m pip install -r $RequirementsFile
    if ($LASTEXITCODE -ne 0) {
        throw "Project dependencies could not be installed."
    }
}

if ($NoShell) {
    Write-Host "Virtual environment is ready: $VenvDirectory" -ForegroundColor Green
    return
}

Write-Host "Opening an activated project shell..." -ForegroundColor Green
$PowerShell = if ($RunningOnWindows) { "powershell.exe" } else { "pwsh" }
& $PowerShell -NoLogo -NoExit -ExecutionPolicy Bypass -Command `
    "& '$ActivateScript'; Set-Location '$ProjectRoot'; Write-Host 'Visualizer virtual environment activated.' -ForegroundColor Green"
