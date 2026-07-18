# Polls origin/main for new commits and redeploys via Docker when found.
# Runs from a Windows Scheduled Task (see README/deploy notes).

$ErrorActionPreference = "Stop"
$RepoDir = "C:\BPS-License-Server"
$LogFile = "C:\BPS-License-Server\deploy.log"

# The Task Scheduler service can have a stale PATH cached from before Git was
# installed, even when interactive shells find `git` fine. Make sure it's
# discoverable regardless of what the service inherited.
$env:PATH = "$env:PATH;C:\Program Files\Git\cmd"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $LogFile -Value $line
}

try {
    Set-Location $RepoDir

    git fetch origin main 2>&1 | Out-Null

    $local = git rev-parse HEAD
    $remote = git rev-parse origin/main

    if ($local -eq $remote) {
        exit 0
    }

    Log "New commit detected: $local -> $remote"
    git pull --ff-only origin main 2>&1 | ForEach-Object { Log $_ }
    Log "git pull ok, running docker compose up -d --build"
    docker compose up -d --build 2>&1 | ForEach-Object { Log $_ }

    # Caddyfile is volume-mounted, not baked into an image, so `up -d --build`
    # alone never picks up changes to it. Reload explicitly every deploy
    # (cheap no-op if unchanged, zero-downtime if it did change).
    Log "Reloading Caddy config"
    docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile 2>&1 | ForEach-Object { Log $_ }

    Log "Deploy finished OK"
} catch {
    Log "DEPLOY FAILED: $_"
}
