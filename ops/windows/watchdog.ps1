# Arbiter watchdog - keeps the app (and its tunnel, if you run one) alive on Windows.
# Registered by install-tasks.ps1 as "Arbiter Watchdog" (every 5 min + at logon).
#
# Probe cheaply FIRST, act only on pieces that are actually down. Two modes:
#   -Controller <script>  hand restarts to your own service controller, called as
#                         `<script> start -Service <Name>-api|<Name>-tunnel`
#   (no controller)       start `python -m arbiter serve` and, when
#                         ops\cloudflared-config.yml exists, `cloudflared tunnel run`
# Never capture controller output: its Start-Process children hold inherited
# pipes open (the '| Out-Null' form once wedged a watchdog task for 8+ hours).
#
# Settings: parameters win; otherwise an optional, gitignored
# ops\windows\watchdog.local.psd1 (a hashtable with any of the parameter names)
# supplies them; otherwise the defaults below.
#
# Safe to run by hand:  powershell -ExecutionPolicy Bypass -File watchdog.ps1

param(
    [int]$Port = 0,
    [string]$Name = '',
    [string]$Tunnel = '',
    [string]$Controller = '',
    [string]$Python = ''
)

$ErrorActionPreference = 'Continue'

$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$TunnelConfig = Join-Path $Root 'ops\cloudflared-config.yml'
$LogDir = Join-Path $PSScriptRoot 'logs'
$LogFile = Join-Path $LogDir 'watchdog.log'

$local = @{}
$localFile = Join-Path $PSScriptRoot 'watchdog.local.psd1'
if (Test-Path $localFile) { $local = Import-PowerShellDataFile $localFile }
function Pick([object]$Given, [string]$Key, [object]$Default) {
    if ($Given) { return $Given }
    if ($local.ContainsKey($Key) -and $local[$Key]) { return $local[$Key] }
    return $Default
}
$Port = [int](Pick $Port 'Port' 5002)
$Name = Pick $Name 'Name' 'arbiter'
$Tunnel = Pick $Tunnel 'Tunnel' $Name
$Controller = Pick $Controller 'Controller' ''
$Python = Pick $Python 'Python' 'python'

function Write-Log {
    param([string]$Message)
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
    Add-Content -Path $LogFile -Value ("{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
}

function Rotate-Log {
    if ((Test-Path $LogFile) -and ((Get-Item $LogFile).Length -gt 512KB)) {
        $tail = Get-Content $LogFile -Tail 1500
        Set-Content -Path $LogFile -Value $tail
    }
}

function Test-App {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 8
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

function Test-Tunnel {
    return [bool](Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match "run\s+$([regex]::Escape($Tunnel))(\s|$)" })
}

function Start-Piece {
    param([string]$Svc)
    if ($Controller) {
        # Start-Process -Wait waits on the controller process itself, never on
        # pipes its persistent children inherit.
        Start-Process powershell.exe -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', $Controller, 'start', '-Service', $Svc -WindowStyle Hidden -Wait
    } elseif ($Svc -eq "$Name-api") {
        if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
        Start-Process $Python -ArgumentList '-u', '-m', 'arbiter', 'serve', '--port', $Port `
            -WorkingDirectory $Root -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $LogDir 'app.log') -RedirectStandardError (Join-Path $LogDir 'app.err.log')
    } else {
        Start-Process cloudflared -ArgumentList 'tunnel', '--config', $TunnelConfig, 'run', $Tunnel `
            -WorkingDirectory $Root -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $LogDir 'tunnel.log') -RedirectStandardError (Join-Path $LogDir 'tunnel.err.log')
    }
}

Rotate-Log

# The tunnel is optional: without a config (and no controller owning it) it isn't watched.
$watchTunnel = [bool]$Controller -or (Test-Path $TunnelConfig)

$down = @()
if (-not (Test-App)) { $down += "$Name-api" }
if ($watchTunnel -and -not (Test-Tunnel)) { $down += "$Name-tunnel" }

if (-not $down) {
    Write-Log 'all up'
} else {
    foreach ($svc in $down) {
        Write-Log "$svc DOWN -> start"
        Start-Piece $svc
    }
    Start-Sleep -Seconds 20
    Write-Log ("post-start: app={0} tunnel={1}" -f (Test-App), $(if ($watchTunnel) { Test-Tunnel } else { 'n/a' }))
}
