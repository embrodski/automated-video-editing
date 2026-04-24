<#
.SYNOPSIS
  Poll an output folder until all expected *-colorcorr*.mp4 files exist, logging every N seconds.

.DESCRIPTION
  Appends a timestamped line to a log file each interval, compares total bytes across expected
  files to detect lack of growth, and warns if ffmpeg is still running but nothing grew for
  two consecutive checks. If encoder processes are gone but outputs are still incomplete for
  two consecutive checks, reports an error. Exits 0 when all files exist and meet -MinBytes.

.PARAMETER OutputDir
  Folder where corrected outputs are written.

.PARAMETER ExpectedBasenames
  Exact filenames to wait for (e.g. Clip-colorcorr.mp4).

.PARAMETER IntervalSeconds
  Seconds between checks (default 300 = five minutes).

.PARAMETER MinBytes
  Minimum file size to treat as present (default 10MB); avoids treating an empty handle as done.

.PARAMETER LogPath
  Log file path. Default: <OutputDir>\colorcorr_monitor.log
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDir,

    [Parameter(Mandatory = $true)]
    [string[]] $ExpectedBasenames,

    [int] $IntervalSeconds = 300,

    [long] $MinBytes = 10MB,

    [string] $LogPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

if (-not (Test-Path -LiteralPath $OutputDir)) {
    Write-Error "OutputDir does not exist: $OutputDir"
    exit 2
}

if (-not $LogPath) {
    $LogPath = Join-Path $OutputDir "colorcorr_monitor.log"
}

function Write-Log {
    param([string] $Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
    Write-Host $line
}

function Test-EncodeProcesses {
    $ffmpeg = Get-Process -Name "ffmpeg" -ErrorAction SilentlyContinue
    if ($ffmpeg) { return $true }
    $py = Get-Process -Name "python","pythonw" -ErrorAction SilentlyContinue
    return [bool]$py
}

function Get-ExpectedPaths {
    foreach ($name in $ExpectedBasenames) {
        Join-Path $OutputDir $name
    }
}

function Get-FileSnapshot {
    $paths = Get-ExpectedPaths
    $rows = @()
    $total = [long]0
    foreach ($p in $paths) {
        if (Test-Path -LiteralPath $p) {
            $i = Get-Item -LiteralPath $p
            $total += $i.Length
            $rows += [pscustomobject]@{ Path = $p; Name = $i.Name; Bytes = $i.Length; Missing = $false }
        }
        else {
            $rows += [pscustomobject]@{ Path = $p; Name = Split-Path $p -Leaf; Bytes = 0; Missing = $true }
        }
    }
    [pscustomobject]@{ Rows = $rows; TotalBytes = $total }
}

function Test-AllComplete {
    param($Snapshot)
    foreach ($r in $Snapshot.Rows) {
        if ($r.Missing -or $r.Bytes -lt $MinBytes) { return $false }
    }
    return $true
}

Write-Log "monitor_colorcorr started (interval ${IntervalSeconds}s, minBytes $MinBytes, log $LogPath)"
Write-Log ("expecting: {0}" -f ($ExpectedBasenames -join ", "))

$iteration = 0
$prevTotal = [long]-1
$noGrowthStreak = 0
$noProcessStreak = 0

while ($true) {
    $iteration++
    $snap = Get-FileSnapshot
    $enc = Test-EncodeProcesses

    foreach ($r in $snap.Rows) {
        if ($r.Missing) {
            Write-Log ("check #{0}  {1}  MISSING" -f $iteration, $r.Name)
        }
        else {
            Write-Log ("check #{0}  {1}  {2:N0} bytes" -f $iteration, $r.Name, $r.Bytes)
        }
    }
    Write-Log ("check #{0}  total_bytes={1:N0}  encoder_processes={2}" -f $iteration, $snap.TotalBytes, $enc)

    if (Test-AllComplete $snap) {
        Write-Log "=== COMPLETE: all expected files present and >= MinBytes ==="
        exit 0
    }

    if ($snap.TotalBytes -eq $prevTotal) {
        $noGrowthStreak++
    }
    else {
        $noGrowthStreak = 0
    }
    $prevTotal = $snap.TotalBytes

    if (-not $enc) {
        $noProcessStreak++
    }
    else {
        $noProcessStreak = 0
    }

    if ($noGrowthStreak -ge 2 -and $enc) {
        Write-Log "WARNING: total output size unchanged for two checks while ffmpeg/python still running; disk stall or hung encode possible."
    }

    if ($noProcessStreak -ge 2 -and -not $enc) {
        Write-Log "ERROR: encoder-related processes absent for two checks but outputs still incomplete. Render may have crashed or exited early."
        exit 1
    }

    Start-Sleep -Seconds $IntervalSeconds
}
