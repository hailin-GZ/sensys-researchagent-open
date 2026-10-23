$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'runtime\.venv\Scripts\python.exe'
$owned = Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $pythonPath -and ($_.CommandLine -match '-m agent (?:worker|dialog-worker)(\s|$)' -or $_.CommandLine -match 'web-redesign[/\\]server.py serve' -or $_.CommandLine -match 'admin[/\\]server.py serve') }
foreach ($process in $owned) { Stop-Process -Id $process.ProcessId; Write-Host "Stopped SENSYS process $($process.ProcessId)." }
Write-Host 'Active requests may have unknown billed usage; the next start conservatively settles and pauses them.'

