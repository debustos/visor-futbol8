param([int]$Jornada=2, [ValidateSet(1,2)][int]$Parte=1, [switch]$ReusarDetecciones, [switch]$ReusarDorsales)
$ErrorActionPreference='Stop'
$taskWorkspaceRoot=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$taskPython=Join-Path $taskWorkspaceRoot 'work\vision-env\Scripts\python.exe'
if(-not (Test-Path -LiteralPath $taskPython)){throw 'Falta el entorno de modelos. Consulta README.md.'}
$taskContextJson=& $taskPython (Join-Path $PSScriptRoot 'registrar_jornada.py') --round $Jornada --context-half $Parte
if($LASTEXITCODE -ne 0){throw 'Jornada o parte no registrada. Añade primero sus vídeos en el visor.'}
$taskContext=$taskContextJson | ConvertFrom-Json
$taskAnalysisRoot=$taskContext.root
$taskPreviousRoot=$env:FOOTBALL_VIEWER_ROOT
$taskPreviousCache=$env:FOOTBALL_CACHE_ROOT
$taskPreviousSource=$env:FOOTBALL_VIDEO_SOURCE
$env:FOOTBALL_VIEWER_ROOT=$taskAnalysisRoot
$env:FOOTBALL_CACHE_ROOT=$taskContext.cache
$env:FOOTBALL_VIDEO_SOURCE=$taskContext.source
New-Item -ItemType Directory -Force -Path $taskContext.cache | Out-Null
function Invoke-AnalysisStep([string]$TaskScript,[string[]]$TaskArgs){
    & $taskPython (Join-Path $PSScriptRoot $TaskScript) @TaskArgs
    if($LASTEXITCODE -ne 0){
        $taskFailure=@{state='failed';stage=$TaskScript;error="Falló $TaskScript (código $LASTEXITCODE)."}
        $taskFailure | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskAnalysisRoot 'automatic\status.json') -Encoding utf8
        throw $taskFailure.error
    }
}
try {
    Invoke-AnalysisStep 'prepare_video.py' @()
    if(-not $ReusarDetecciones){Invoke-AnalysisStep 'analyze_automatic.py' @('--scan-only')}
    Invoke-AnalysisStep 'temporal_actions.py' @()
    if(-not $ReusarDorsales){Invoke-AnalysisStep 'analyze_automatic.py' @('--resume')}
    Invoke-AnalysisStep 'refine_ball.py' @()
    Invoke-AnalysisStep 'analyze_automatic.py' @('--resume','--reuse-ocr')
    Invoke-AnalysisStep 'extract_appearance_parts.py' @()
    Invoke-AnalysisStep 'upgrade_v3.py' @()
    Invoke-AnalysisStep 'adaptive_ball.py' @()
    Invoke-AnalysisStep 'read_jersey_text.py' @()
    Invoke-AnalysisStep 'repair_identity_v5.py' @()
    Invoke-AnalysisStep 'commit_v5.py' @()
    Invoke-AnalysisStep 'make_gallery.py' @()
    Invoke-AnalysisStep 'export_heatmaps.py' @()
    Invoke-AnalysisStep 'validate_v5.py' @()
    if(-not (Test-Path -LiteralPath (Join-Path $taskAnalysisRoot 'media\primera-compatible.mp4'))){Invoke-AnalysisStep 'make_playback.py' @()}
    Write-Host "Jornada $Jornada, parte $Parte actualizada. El visor incorporará sus fichas, mapas y evidencia al acumulado."
} finally {
    $env:FOOTBALL_VIEWER_ROOT=$taskPreviousRoot
    $env:FOOTBALL_CACHE_ROOT=$taskPreviousCache
    $env:FOOTBALL_VIDEO_SOURCE=$taskPreviousSource
}
