# Registers the "Arbiter Watchdog" scheduled task (every 5 min).
# Runs through the bundled hidden_run.vbs so the 5-minute ticks never flash a
# console window. Every parameter is passed through to watchdog.ps1 and baked
# into the task, e.g.:
#   .\install-tasks.ps1                                      # self-starting watchdog
#   .\install-tasks.ps1 -Controller C:\path\to\server.ps1    # defer to your own controller
#
# Register-ScheduledTask can need elevation (Access is denied unelevated); the
# schtasks fallback below creates the same 5-minute task as the current user
# without elevation. The elevated path additionally gets an at-logon trigger
# and battery-friendly settings, but the 5-minute tick alone already covers
# reboot recovery.
param(
    [string]$TaskName = 'Arbiter Watchdog',
    [int]$Port = 5002,
    [string]$Name = 'arbiter',
    [string]$Tunnel = '',
    [string]$Controller = '',
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'

$watchdog = Join-Path $PSScriptRoot 'watchdog.ps1'
$vbs = Join-Path $PSScriptRoot 'hidden_run.vbs'
if ($Controller -and -not (Test-Path $Controller)) { throw "controller not found at $Controller" }

# Only non-default args, so the command stays under schtasks' 261-char /tr limit.
$wdArgs = @()
if ($Port -ne 5002) { $wdArgs += @('-Port', $Port) }
if ($Name -ne 'arbiter') { $wdArgs += @('-Name', $Name) }
if ($Tunnel) { $wdArgs += @('-Tunnel', $Tunnel) }
if ($Python -ne 'python') { $wdArgs += @('-Python', $Python) }
if ($Controller) { $wdArgs += @('-Controller', (Resolve-Path $Controller).Path) }
$quoted = (@('powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $watchdog) + $wdArgs |
    ForEach-Object { "`"$_`"" }) -join ' '
$argString = "//B //Nologo `"$vbs`" $quoted"

try {
    $action = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument $argString
    $triggers = @(
        (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
            -RepetitionInterval (New-TimeSpan -Minutes 5) `
            -RepetitionDuration (New-TimeSpan -Days 3650)),
        (New-ScheduledTaskTrigger -AtLogOn)
    )
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
    Register-ScheduledTask -TaskName $TaskName -Action $action `
        -Trigger $triggers -Settings $settings -Force -ErrorAction Stop | Out-Null
    Write-Host "Registered task: $TaskName (every 5 min + at logon)"
} catch {
    Write-Host "Register-ScheduledTask failed ($($_.Exception.Message.Trim())) - falling back to schtasks"
    schtasks /create /tn "$TaskName" /sc minute /mo 5 /tr "wscript.exe $argString" /f
    if ($LASTEXITCODE -ne 0) { throw "schtasks fallback failed with exit code $LASTEXITCODE" }
    Write-Host "Registered task: $TaskName (every 5 min, current user)"
}
