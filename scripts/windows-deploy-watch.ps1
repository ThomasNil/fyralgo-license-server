# Polls origin/main for new commits and redeploys via Docker when found.
# Runs from a Windows Scheduled Task (see README/deploy notes).

$ErrorActionPreference = "Stop"
$RepoDir = "C:\BPS-License-Server"
$LogFile = "C:\BPS-License-Server\deploy.log"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $LogFile -Value $line
}

Set-Location $RepoDir

git fetch origin main 2>&1 | Out-Null

$local = git rev-parse HEAD
$remote = git rev-parse origin/main

if ($local -eq $remote) {
    exit 0
}

Log "New commit detected: $local -> $remote"

try {
    git pull --ff-only origin main 2>&1 | ForEach-Object { Log $_ }
    Log "git pull ok, running docker compose up -d --build"
    docker compose up -d --build 2>&1 | ForEach-Object { Log $_ }
    Log "Deploy finished OK"
} catch {
    Log "DEPLOY FAILED: $_"
}
