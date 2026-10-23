$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'runtime\.venv\Scripts\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
if (-not $env:SENSYS_ALLOW_BENCHMARK_DNS) { $env:SENSYS_ALLOW_BENCHMARK_DNS = '1' }
$logDir = Join-Path $projectRoot 'runtime\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$processRecords = @()
& $pythonPath -c "import sys;from pathlib import Path;root=Path(sys.argv[1]);sys.path[:0]=[str(root),str(root/'web-redesign')];from agent import store;store.init()" $projectRoot
if ($LASTEXITCODE -ne 0) { throw 'SENSYS database initialization failed; no new process started.' }
foreach ($entry in @(@{name='worker';args=@('-m','agent','worker');port=0},@{name='dialog-worker';args=@('-m','agent','dialog-worker');port=0},@{name='user';args=@('web-redesign/server.py','serve');port=8766},@{name='admin';args=@('admin/server.py','serve');port=8767})) {
    if ($entry.port -gt 0 -and (Get-NetTCPConnection -LocalPort $entry.port -State Listen -ErrorAction SilentlyContinue)) { Write-Host "$($entry.name) port $($entry.port) already listening; not restarted."; continue }
    if ($entry.port -eq 0) {
        $workerPattern = '-m agent ' + $entry.name + '(\s|$)'
        $existing = Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $pythonPath -and $_.CommandLine -match $workerPattern }
        if ($existing) { Write-Host 'Agent worker already running.'; continue }
    }
    $proc = Start-Process -FilePath $pythonPath -ArgumentList $entry.args -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "$($entry.name).out.log") -RedirectStandardError (Join-Path $logDir "$($entry.name).err.log")
    $processRecords += @{ name=$entry.name;pid=$proc.Id;started=(Get-Date).ToString('o') }
}
if ($processRecords.Count) { $processRecords | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logDir 'processes.json') -Encoding utf8 }
Write-Host 'User: http://127.0.0.1:8766/'
Write-Host 'Admin: http://127.0.0.1:8767/'
