<#
Before the Ice Goes Out, for a playtest: asks for the week's seed, starts the game with Thespis beside it (this repo's
engine code, run by a Python that has Thespis's packages), and shows where the week's record was saved.

  .\play.ps1              asks for the seed (Enter plays 19, the first week of the playtest guide)
  .\play.ps1 -Seed 12     plays seed 12
  .\play.ps1 -Editor      opens the Godot editor instead, with Thespis set up the same way

Double-click play.cmd beside it to run this without a PowerShell window. Set $env:GODOT to use another Godot, and
$env:THESPIS_PYTHON to use another Python.
#>
param([int]$Seed = -1, [switch]$Editor)

$ErrorActionPreference = 'Stop'
$game = $PSScriptRoot
$repo = (Resolve-Path (Join-Path $game '..\..')).Path

function Find-First([string[]]$paths) {
    foreach ($p in $paths) { if ($p -and (Test-Path $p)) { return (Resolve-Path $p).Path } }
    return $null
}

$python = Find-First @($env:THESPIS_PYTHON,
    (Join-Path $repo '.venv\Scripts\python.exe'),
    (Join-Path $repo '..\Thespis\.venv\Scripts\python.exe'))
if (-not $python) { throw "No Python with Thespis found: set `$env:THESPIS_PYTHON to one (a .venv's python.exe)." }

$godotDir = Join-Path $env:USERPROFILE 'OneDrive\Desktop\Godot_v4.7.2-stable_win64.exe~1'
$exe = if ($Editor) { 'Godot_v4.7.2-stable_win64.exe' } else { 'Godot_v4.7.2-stable_win64_console.exe' }
$godot = Find-First @($env:GODOT, (Join-Path $godotDir $exe), (Get-Command godot -ErrorAction SilentlyContinue).Source)
if (-not $godot) { throw "No Godot 4.7 found: set `$env:GODOT to its .exe." }

# Thespis runs as the game's sidecar, from this repo's code rather than whatever copy the Python has installed
$env:THESPIS_SIDECAR = ConvertTo-Json -Compress @(($python -replace '\\', '/'), '-m', 'thespis')
$env:PYTHONPATH = $repo

if ($Editor) {
    Write-Host "Opening the editor. To pick the week: Project Settings > Editor > Run > Main Run Args: -- --seed=19"
    & $godot --path $game -e
    return
}

if ($Seed -lt 0) {
    $answer = Read-Host 'Which week? Seed number (Enter for 19; the guide goes 19, 12, 21, 2, 7, 3)'
    $Seed = if ($answer.Trim() -match '^\d+$') { [int]$answer.Trim() } else { 19 }
}

$records = Join-Path $env:APPDATA 'Godot\app_userdata\Before the Ice Goes Out\playtest'
$before = if (Test-Path $records) { @(Get-ChildItem $records -Filter *.md | ForEach-Object FullName) } else { @() }

Write-Host "Seed $Seed. The town is waking up; this window shows Thespis and, at the end, the record."
& $godot --path $game -- --seed=$Seed

$new = if (Test-Path $records) {
    @(Get-ChildItem $records -Filter *.md | Where-Object { $before -notcontains $_.FullName } | Sort-Object LastWriteTime)
} else { @() }
if ($new.Count) {
    Write-Host ''
    Write-Host 'The week''s record:'
    $new | ForEach-Object { Write-Host "  $($_.FullName)"; Write-Host "  $([IO.Path]::ChangeExtension($_.FullName, '.json'))" }
    if ((Read-Host 'Open the folder? (Y/n)') -notmatch '^[nN]') { Invoke-Item $records }
} else {
    Write-Host "No new record in $records (it's written when the steamer comes, or when the window is closed)."
}
