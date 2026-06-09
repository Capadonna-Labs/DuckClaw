# Diagnostic: git pull invalid path on Windows (session 97f3cb)
$logPath = Join-Path (Get-Location) "debug-97f3cb.log"
$sessionId = "97f3cb"
function Write-DebugLog($hypothesisId, $message, $data) {
    $entry = @{
        sessionId = $sessionId
        hypothesisId = $hypothesisId
        location = "scripts/debug_git_pull_paths.ps1"
        message = $message
        data = $data
        timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        runId = "pre-fix"
    } | ConvertTo-Json -Compress
    Add-Content -Path $logPath -Value $entry -Encoding UTF8
}

$invalid = @()
git ls-tree -r --name-only origin/main | ForEach-Object {
    if ($_ -match '[:<>\"|?*]') { $invalid += $_ }
}
Write-DebugLog "H1" "colon_or_reserved_chars_in_paths" @{ count = $invalid.Count; paths = $invalid }

$protect = git config --get core.protectNTFS
$longpaths = git config --get core.longpaths
Write-DebugLog "H4" "git_windows_config" @{ core.protectNTFS = $protect; core.longpaths = $longpaths }

$mergeOut = git merge FETCH_HEAD 2>&1 | Out-String
Write-DebugLog "H2" "merge_repro_output" @{ output = $mergeOut.Trim(); exitCode = $LASTEXITCODE }

Write-Host "Logged to $logPath"
Write-Host "Invalid paths: $($invalid.Count)"
