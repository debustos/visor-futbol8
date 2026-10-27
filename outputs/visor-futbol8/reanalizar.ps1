param([int]$Jornada=2, [ValidateSet(1,2)][int]$Parte=1, [switch]$ReusarDetecciones, [switch]$ReusarDorsales)
# Ejecuta las mismas etapas y la misma cola que el botón Analizar (f8/<módulo>/etapas.py),
# en primer plano. El visor muestra el progreso si está abierto.
$ErrorActionPreference='Stop'
$taskWorkspaceRoot=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$taskPython=Join-Path $taskWorkspaceRoot 'work\vision-env\Scripts\python.exe'
if(-not (Test-Path -LiteralPath $taskPython)){throw 'Falta el entorno de modelos. Consulta README.md.'}
$taskOmitir=@()
if($ReusarDetecciones){$taskOmitir+='detection'}
if($ReusarDorsales){$taskOmitir+='jersey'}
$taskArgs=@('-u','-m','f8.plataforma.analysis_worker','--root',$PSScriptRoot,'--round',$Jornada,'--half',$Parte)
if($taskOmitir.Count){$taskArgs+=@('--omit',($taskOmitir -join ','))}
Push-Location -LiteralPath $PSScriptRoot
try {
    & $taskPython @taskArgs
    if($LASTEXITCODE -ne 0){throw "El análisis de la jornada $Jornada, parte $Parte no terminó. Consulta el mensaje anterior."}
} finally { Pop-Location }
