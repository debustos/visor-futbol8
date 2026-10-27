param([switch]$UnaVez)
$ErrorActionPreference = 'Stop'
$taskViewerRoot = $PSScriptRoot
$taskWorkspaceRoot = Split-Path (Split-Path $taskViewerRoot -Parent) -Parent
$taskPython = Join-Path $taskWorkspaceRoot 'work\vision-env\Scripts\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'No se encuentra el entorno de Python del proyecto.' }
Push-Location -LiteralPath $taskViewerRoot
try {
    if ($UnaVez) { & $taskPython -B -m f8.revision.review_learning --root $taskViewerRoot --once }
    else { & $taskPython -B -m f8.revision.review_learning --root $taskViewerRoot --watch }
    if ($LASTEXITCODE -ne 0) { throw 'El aprendizaje terminó con un error. Consulta aprendizaje\gXXXXXX\worker.log.' }
} finally { Pop-Location }
