<#
.SYNOPSIS
  Poll every N seconds until Ben/Guest/Wide Render.mp4 all exist and exceed a minimum size.

.DESCRIPTION
  Writes a line to -LogPath each poll. When all three outputs look complete, prints
  ANNOUNCE_MASSIVE_ALL_THREE_COMPLETE (for log watchers) and writes -DoneFlagPath.
#>
param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDir,

    [int] $IntervalSec = 300,

    [long] $MinBytes = (100 * 1024 * 1024),

    [string] $LogPath = $(Join-Path $OutputDir 'massive_triple_watch.log'),

    [string] $DoneFlagPath = $(Join-Path $OutputDir 'MASSIVE_ALL_THREE_COMPLETE.txt')
)

function Get-SafeLength {
    param([string] $Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        return (Get-Item -LiteralPath $Path -ErrorAction Stop).Length
    } catch {
        return $null
    }
}

function Log-Line {
    param([string] $Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $Message"
    Add-Content -LiteralPath $LogPath -Value $line -Encoding utf8
    Write-Host $line
}

$names = @(
    @{ Label = 'Ben';    File = 'Ben Render.mp4' },
    @{ Label = 'Guest'; File = 'Guest Render.mp4' },
    @{ Label = 'Wide';  File = 'Wide Render.mp4' }
)

Log-Line "Watcher started. OutputDir=$OutputDir  IntervalSec=$IntervalSec  MinBytes=$MinBytes"

while ($true) {
    $sizes = @{}
    $ok = $true
    foreach ($n in $names) {
        $p = Join-Path $OutputDir $n.File
        $len = Get-SafeLength -Path $p
        $sizes[$n.Label] = $len
        if ($null -eq $len -or $len -lt $MinBytes) {
            $ok = $false
        }
    }

    $msg = "Ben=$($sizes['Ben']) Guest=$($sizes['Guest']) Wide=$($sizes['Wide'])"
    Log-Line $msg

    if ($ok) {
        $banner = @"

======================================================================
MASSIVE: All three single-camera renders are present and above MinBytes.
  Ben Render.mp4
  Guest Render.mp4
  Wide Render.mp4
======================================================================
ANNOUNCE_MASSIVE_ALL_THREE_COMPLETE
"@
        Write-Host $banner
        Add-Content -LiteralPath $LogPath -Value $banner -Encoding utf8
        @"
Completed at: $(Get-Date -Format 'o')
OutputDir: $OutputDir
Ben bytes: $($sizes['Ben'])
Guest bytes: $($sizes['Guest'])
Wide bytes: $($sizes['Wide'])
"@ | Set-Content -LiteralPath $DoneFlagPath -Encoding utf8
        try { [console]::beep(880, 400) } catch { }
        exit 0
    }

    Start-Sleep -Seconds $IntervalSec
}
