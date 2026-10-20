param([int]$Port = 8768, [string]$PythonPath)
$ErrorActionPreference = 'Stop'
$taskViewerRoot = $PSScriptRoot
$taskWorkspaceRoot = Split-Path (Split-Path $taskViewerRoot -Parent) -Parent
$taskWorkRoot = Join-Path $taskWorkspaceRoot 'work'
$env:TEMP = Join-Path $taskWorkRoot 'tmp'
$env:TMP = $env:TEMP
$env:TORCH_HOME = Join-Path $taskWorkRoot 'torch-cache'
$env:HF_HOME = Join-Path $taskWorkRoot 'hf-cache'
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
if (-not $PythonPath) { $PythonPath = Join-Path $taskWorkspaceRoot 'work\vision-env\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'No se encuentra Python. Usa -PythonPath con la ruta de tu entorno. Consulta README.md.' }
$taskViewerUrl = "http://127.0.0.1:$Port"
$taskExistingViewer = $null
try { $taskExistingViewer = Invoke-RestMethod -Uri "$taskViewerUrl/api/bootstrap" -TimeoutSec 2 } catch {}
if (-not $taskExistingViewer) {
    $taskServerScript = Join-Path $taskViewerRoot 'server.py'
    Start-Process -FilePath $PythonPath -ArgumentList @('-u', ('"' + $taskServerScript + '"'), '--port', $Port) -WorkingDirectory $taskViewerRoot -WindowStyle Hidden
    for ($taskAttempt = 0; $taskAttempt -lt 30; $taskAttempt++) {
        try { $taskExistingViewer = Invoke-RestMethod -Uri "$taskViewerUrl/api/bootstrap" -TimeoutSec 1; break } catch { Start-Sleep -Milliseconds 200 }
    }
    if (-not $taskExistingViewer) { throw 'El visor no responde. Ejecuta server.py desde un terminal para ver el error.' }
}
Start-Process $taskViewerUrl
Write-Host "Visor disponible: $taskViewerUrl"
