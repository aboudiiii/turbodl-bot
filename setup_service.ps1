# Registers TurboDLBotService as a Windows background service.
# Elevated:   NSSM (true Windows service, boot start).
# Unelevated: Task Scheduler via a hidden VBS launcher (logon start).
# Safe to re-run; existing registrations are replaced.
param(
    [string]$ProjectDir = (Split-Path -Parent $MyInvocation.MyCommand.Path),
    [string]$PythonExe = (Get-Command python).Source,
    [string]$ServiceName = "TurboDLBotService"
)

$ErrorActionPreference = "Stop"
$BotScript = Join-Path $ProjectDir "bot.py"
$LogDir = Join-Path $ProjectDir "logs"
$LogFile = Join-Path $LogDir "service_output.log"
$Nssm = Join-Path $ProjectDir "service\nssm\nssm-2.24\win64\nssm.exe"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not (Test-Path $BotScript)) { throw "bot.py not found at $BotScript" }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Write-Output "Elevated: $isAdmin"

# --- Elevated path: real service via NSSM ---------------------------------
if ($isAdmin -and (Test-Path $Nssm)) {
    try {
        # Only call remove if the service exists (nssm hangs otherwise).
        if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
            & $Nssm stop $ServiceName 2>$null | Out-Null
            & $Nssm remove $ServiceName confirm 2>$null | Out-Null
        }
        & $Nssm install $ServiceName $PythonExe $BotScript
        & $Nssm set $ServiceName AppDirectory $ProjectDir
        & $Nssm set $ServiceName DisplayName "TurboDL Bot Service"
        & $Nssm set $ServiceName Description "TurboDL Telegram bot (bot.py) - runs continuously in the background."
        & $Nssm set $ServiceName Start SERVICE_AUTO_START
        & $Nssm set $ServiceName AppStdout $LogFile
        & $Nssm set $ServiceName AppStderr $LogFile
        & $Nssm set $ServiceName AppRotateFiles 1
        & $Nssm set $ServiceName AppRotateOnline 1
        & $Nssm set $ServiceName AppRotateBytes 10485760
        & $Nssm set $ServiceName AppStdoutCreationDisposition 4
        & $Nssm set $ServiceName AppStderrCreationDisposition 4

        Write-Output "NSSM: starting service..."
        & $Nssm start $ServiceName
        Start-Sleep -Seconds 4
        $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -eq "Running") {
            Write-Output "SUCCESS via NSSM: $ServiceName is $($svc.Status)."
            exit 0
        }
        Write-Output "NSSM service not running; trying fallback..."
    } catch {
        Write-Output "NSSM path failed: $($_.Exception.Message)"
    }
}

# --- Unelevated fallback: Task Scheduler + hidden launcher -----------------
Write-Output "Registering via Task Scheduler..."
# Native tools write errors to stderr; do not let EAP=Stop escalate them.
$ErrorActionPreference = "Continue"

# Launchers live in a space-free dir so /tr needs no nested quoting.
$LauncherDir = Join-Path $env:LOCALAPPDATA "TurboDLBot"
New-Item -ItemType Directory -Force -Path $LauncherDir | Out-Null

# Launcher batch: sets working directory, captures stdout+stderr to the log.
$Bat = Join-Path $LauncherDir "run_bot.bat"
"@echo off`r`ncd /d `"$ProjectDir`"`r`n`"$PythonExe`" `"$BotScript`" >> `"$LogFile`" 2>&1`r`n" |
    Set-Content -Path $Bat -Encoding ASCII

# VBS wrapper: launches the batch fully hidden (no console window).
$Vbs = Join-Path $LauncherDir "run_bot.vbs"
$VbsContent = @'
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "__PROJECT__"
sh.Run """__BAT__""", 0, False
'@
$VbsContent = $VbsContent.Replace("__PROJECT__", $ProjectDir).Replace("__BAT__", $Bat)
Set-Content -Path $Vbs -Value $VbsContent -Encoding ASCII

# Replace any previous registration of the same name.
schtasks /delete /tn $ServiceName /f | Out-Null

$schedName = $ServiceName
$Wscript = Join-Path $env:SystemRoot "System32\wscript.exe"
$Tr = "$Wscript $Vbs"
if ($isAdmin) {
    schtasks /create /f /tn $schedName /tr $Tr /sc onstart /ru SYSTEM /rl HIGHEST | Out-Null
}
if ($isAdmin -and $LASTEXITCODE -eq 0) {
    Write-Output "Registered as ONSTART scheduled task."
} else {
    schtasks /create /f /tn $schedName /tr $Tr /sc onlogon | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Output "Registered as ONLOGON scheduled task."
    } else {
        # Last resort: HKCU Run key autostart (always permitted).
        Write-Output "Task Scheduler denied; using HKCU Run-key autostart."
        $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
        if (-not (Test-Path $runKey)) { New-Item -Path $runKey -Force | Out-Null }
        Set-ItemProperty -Path $runKey -Name $schedName -Value "`"$Wscript`" `"$Vbs`""
        Write-Output "Registered Run-key entry '$schedName'."
    }
}

# Start the bot right now.
Write-Output "Starting bot..."
& $Wscript $Vbs
Start-Sleep -Seconds 6
$py = Get-Process python -ErrorAction SilentlyContinue
if ($py) {
    Write-Output ("SUCCESS: python running (PID " + (($py.Id) -join ",") + "), started via '$schedName'.")
} else {
    Write-Output "WARNING: no python process detected; check $LogFile"
}
$query = schtasks /query /tn $schedName /fo LIST 2>$null
if ($query) { Write-Output ($query | Select-String "TaskName|Status|Task To Run" | ForEach-Object { $_.ToString().Trim() }) }