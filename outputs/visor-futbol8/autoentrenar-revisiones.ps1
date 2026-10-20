param([switch]$UnaVez)
$ErrorActionPreference = 'Stop'
$taskViewerRoot = $PSScriptRoot
$taskWorkspaceRoot = Split-Path (Split-Path $taskViewerRoot -Parent) -Parent
$taskPython = Join-Path $taskWorkspaceRoot 'work\vision-env\Scripts\python.exe'
$taskTrainer = Join-Path $taskViewerRoot 'review_learning.py'
$env:PYTHONIOENCODING = 'utf-8'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'No se encuentra el entorno de Python del proyecto.' }
if ($UnaVez) { & $taskPython -B $taskTrainer --root $taskViewerRoot --once }
else { & $taskPython -B $taskTrainer --root $taskViewerRoot --watch }
if ($LASTEXITCODE -ne 0) { throw 'El aprendizaje terminó con un error. Consulta aprendizaje\gXXXXXX\worker.log.' }
