# 58:12 shop print helper
#
# Collects receipts from 58:12 and sends them to the printer on this shop's
# network. Run it once: it sets itself to start again whenever this computer
# is switched on, so nobody has to remember.
#
#   Right-click this file and choose "Run with PowerShell".
#   If Windows refuses, open PowerShell and run:
#     powershell -ExecutionPolicy Bypass -File .\print-helper.ps1
#
# To stop it for good:
#     powershell -ExecutionPolicy Bypass -File .\print-helper.ps1 -Uninstall

param(
  [switch]$NoInstall,      # run once now, do not set it to start on its own
  [switch]$Uninstall       # stop it starting on its own, and stop it now
)

$Api   = '__API__'
$Token = '__TOKEN__'

$AppName  = '5812-print-helper'
# LOCALAPPDATA is not set in every environment, and a helper that falls over
# on its first line prints nothing at all (iter423).
$Base = $env:LOCALAPPDATA
if (-not $Base) { $Base = $env:APPDATA }
if (-not $Base) { $Base = $HOME }
$HomeDir  = Join-Path $Base $AppName
$Installed = Join-Path $HomeDir 'print-helper.ps1'
$TaskBoot = '58-12 print helper'
$TaskWatch = '58-12 print helper (keep alive)'
$StopFlag = Join-Path $HomeDir 'stop'

function Remove-Autostart {
  foreach ($t in @($TaskBoot, $TaskWatch)) {
    try { schtasks /delete /tn "$t" /f 2>$null | Out-Null } catch { }
  }
}

if ($Uninstall) {
  Remove-Autostart
  Write-Host "The print helper will no longer start on its own." -ForegroundColor Yellow
  Write-Host "Receipts will go back to the till's own print window." -ForegroundColor DarkGray
  # Ask the running copy to stand down. Reading a flag beats hunting processes,
  # which older Windows PowerShell cannot do by command line (iter423).
  if (-not (Test-Path $HomeDir)) { New-Item -ItemType Directory -Path $HomeDir -Force | Out-Null }
  Set-Content -Path $StopFlag -Value 'stop'
  Start-Sleep -Seconds 6
  Remove-Item $StopFlag -ErrorAction SilentlyContinue
  exit
}

# ---- only one helper at a time ------------------------------------------
# The keep-alive task fires every few minutes; if the helper is already
# running this second copy must bow out rather than print everything twice.
$mutex = New-Object System.Threading.Mutex($false, "Global\$AppName")
if (-not $mutex.WaitOne(0)) {
  Write-Host "The print helper is already running on this computer." -ForegroundColor DarkGray
  exit
}

# ---- start again after a reboot -----------------------------------------
function Install-Autostart {
  try {
    if (-not (Test-Path $HomeDir)) { New-Item -ItemType Directory -Path $HomeDir -Force | Out-Null }
    if ($PSCommandPath -and ($PSCommandPath -ne $Installed)) {
      Copy-Item -LiteralPath $PSCommandPath -Destination $Installed -Force
    }
    $run = "powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Installed`""
    # At logon: the till is signed in all day, so this covers every restart.
    schtasks /create /tn "$TaskBoot" /tr $run /sc onlogon /rl limited /f | Out-Null
    # And every five minutes, in case it was closed or crashed. The lock above
    # means a second copy simply exits.
    schtasks /create /tn "$TaskWatch" /tr $run /sc minute /mo 5 /rl limited /f | Out-Null
    Write-Host "Set to start again whenever this computer is switched on." -ForegroundColor Green
    Write-Host "Copied to $Installed" -ForegroundColor DarkGray
  } catch {
    Write-Host "Could not set it to start on its own: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "It will still print for as long as this window stays open." -ForegroundColor DarkGray
  }
}

if (-not $NoInstall) { Install-Autostart }

Write-Host "58:12 print helper running." -ForegroundColor Green
Write-Host "Talking to $Api" -ForegroundColor DarkGray

while ($true) {
  if (Test-Path $StopFlag) {
    Write-Host "Asked to stop. Goodbye." -ForegroundColor Yellow
    exit
  }
  try {
    $jobs = Invoke-RestMethod -Uri "$Api/screens/$Token/print-jobs" -Method Get -TimeoutSec 30 `
      -Headers @{ 'User-Agent' = '58-12-print-helper/1.0' }
    foreach ($job in @($jobs)) {
      $ok = $false
      $err = ''
      try {
        $bytes = [Convert]::FromBase64String($job.data_b64)
        $client = New-Object System.Net.Sockets.TcpClient
        $connect = $client.BeginConnect($job.host, [int]$job.port, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne(5000)) { throw "no answer from $($job.host):$($job.port)" }
        $client.EndConnect($connect)
        $stream = $client.GetStream()
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush()
        Start-Sleep -Milliseconds 400
        $stream.Close(); $client.Close()
        $ok = $true
        Write-Host ("Printed {0} on {1}" -f $job.title, $job.host) -ForegroundColor Green
      } catch {
        $err = $_.Exception.Message
        Write-Host ("Could not print {0}: {1}" -f $job.title, $err) -ForegroundColor Red
      }
      $body = @{ ok = $ok; error = $err } | ConvertTo-Json
      try {
        Invoke-RestMethod -Uri "$Api/screens/$Token/print-jobs/$($job.id)" -Method Post `
          -Body $body -ContentType 'application/json' -TimeoutSec 30 `
          -Headers @{ 'User-Agent' = '58-12-print-helper/1.0' } | Out-Null
      } catch { Write-Host "Could not report back to 58:12" -ForegroundColor DarkYellow }
    }
  } catch {
    Write-Host "Waiting for 58:12..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 5
  }
  Start-Sleep -Seconds 2
}
