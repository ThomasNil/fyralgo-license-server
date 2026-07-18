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

# Runs a native command through cmd.exe so its stderr output (git/docker both
# write routine status info there, not just errors) never gets wrapped into
# PowerShell ErrorRecord objects - with $ErrorActionPreference = "Stop" that
# wrapping turns harmless stderr chatter into a script-terminating exception.
# Success/failure is judged solely by the real exit code.
function Run($cmd) {
    $output = & cmd /c "$cmd 2>&1"
    $output | ForEach-Object { Log $_ }
    return $LASTEXITCODE -eq 0
}

try {
    Set-Location $RepoDir

    Run "git fetch origin main" | Out-Null

    $local = git rev-parse HEAD
    $remote = git rev-parse origin/main

    if ($local -eq $remote) {
        exit 0
    }

    Log "New commit detected: $local -> $remote"

    if (-not (Run "git pull --ff-only origin main")) {
        Log "DEPLOY FAILED: git pull failed"
        exit 1
    }

    Log "git pull ok, running docker compose up -d --build"
    if (-not (Run "docker compose up -d --build")) {
        Log "DEPLOY FAILED: docker compose up --build failed"
        exit 1
    }

    # Caddyfile is volume-mounted, not baked into an image, so `up -d --build`
    # alone never picks up changes to it. Reload explicitly every deploy
    # (cheap no-op if unchanged, zero-downtime if it did change).
    Log "Reloading Caddy config"
    Run "docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile" | Out-Null

    Log "Deploy finished OK"
} catch {
    Log "DEPLOY FAILED: $_"
}
