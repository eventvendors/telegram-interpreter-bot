$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "C:\Users\trans\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$logDir = Join-Path $projectRoot "logs"
$stdoutLog = Join-Path $logDir "bot.out.log"
$stderrLog = Join-Path $logDir "bot.err.log"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

Set-Location $projectRoot

Write-Host "Starting Telegram bot..." -ForegroundColor Cyan
Write-Host "A window will stay open while the bot is running." -ForegroundColor Yellow
Write-Host "If Telegram is temporarily unreachable, the bot will keep retrying automatically." -ForegroundColor Yellow
Write-Host "Close this window or press Ctrl+C to stop the bot." -ForegroundColor Yellow
Write-Host ""

& $python "main.py" 1>> $stdoutLog 2>> $stderrLog
