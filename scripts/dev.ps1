$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"

$venvPython = Join-Path $backendDir "venv\\Scripts\\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

Start-Process -FilePath $python -ArgumentList @(
  "-m", "uvicorn",
  "app:app",
  "--reload",
  "--host", "127.0.0.1",
  "--port", "8000"
) -WorkingDirectory $backendDir

Start-Process -FilePath $python -ArgumentList @(
  "-m", "http.server",
  "5500",
  "--directory", $frontendDir
) -WorkingDirectory $root

Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "Frontend: http://127.0.0.1:5500"
