<#
.SYNOPSIS
    One command that reproduces the project's acceptance checks.

.DESCRIPTION
    Runs the environment-independent stages (unit tests, current-tool schema,
    JavaScript syntax and behavior regressions) and optional native domain checks
    against one lab. Writes a JSON report and returns a meaningful exit code.

    Every stage records its own status; a failing stage never hides the others.
    Python here cannot always write inside the repository, so the report and all
    scratch files live in the workspace `work/` tree.

.PARAMETER Native
    Also run tools/check_native_domains.py against -Lab. That starts VRoid
    Studio, so the lab must be free and its crash key absent.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\run_checks.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\run_checks.ps1 -Native -Lab <prepared lab>
#>
param(
    [string]$Lab = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'lab-test'),
    [string]$Python = '',
    [string]$Out = '',
    [switch]$Native,
    [switch]$SkipUnit,
    [switch]$SkipTools,
    [switch]$SkipJs,
    [switch]$Manifest,
    [switch]$Provenance,
    [string]$Tag = ''
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $repo
$workRoot = Join-Path $workspace 'work'
if (-not (Test-Path $workRoot)) { $workRoot = Join-Path $env:TEMP 'vroid-mcp-checks' }
$scratch = Join-Path $workRoot 'temp'
New-Item -ItemType Directory -Force -Path $scratch | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $scratch 'pytest-base') | Out-Null

# Pin TEMP/TMP for every child process. Without this, pytest creates session
# directories under a TEMP path this account cannot write and every test that
# needs tmp_path fails during setup rather than in its assertions.
$env:TEMP = $scratch
$env:TMP = $scratch

if (-not $Out) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $Out = Join-Path $workRoot "checks\$stamp"
}
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$reportPath = Join-Path $Out 'checks.json'

if (-not $Python) {
    $candidate = Join-Path $repo '.venv\Scripts\python.exe'
    if (Test-Path $candidate) { $Python = $candidate }
}
if (-not (Test-Path $Python)) { throw "Python interpreter not found: $Python" }

# PowerShell cannot wrap a list built with `New-Object ...List[object]` in @();
# build it with ::new() and read back with ToArray().
$results = [System.Collections.Generic.List[object]]::new()
$started = Get-Date
$toolCount = $null
$toolsetHash = $null

function Add-Result {
    param([string]$Name, [string]$Status, [double]$Seconds, $Detail, [string]$Output = '')
    $row = [ordered]@{
        name    = $Name
        status  = $Status
        seconds = [math]::Round($Seconds, 2)
        detail  = $Detail
    }
    if ($Output) { $row.output = $Output }
    $results.Add([pscustomobject]$row)
    $colour = switch ($Status) { 'pass' { 'Green' } 'fail' { 'Red' } 'skipped' { 'Yellow' } default { 'Gray' } }
    Write-Host ("[{0,-7}] {1,-24} {2,6:N1}s {3}" -f $Status, $Name, $Seconds, $(if ($Detail -is [string]) { $Detail } else { '' })) -ForegroundColor $colour
}

# A native tool that writes to stderr becomes an error record, and with
# ErrorActionPreference=Stop that would end the runner before it records the
# stage. Running it through cmd keeps both streams plain text in one log file,
# so a drift report or a failing test reads as text and the exit code decides.
function Invoke-Logged {
    param([string]$Exe, [string[]]$Arguments, [string]$Log)
    $quoted = @('"' + $Exe + '"')
    foreach ($argument in $Arguments) {
        $quoted += if ($argument -match '[\s"]') { '"' + ($argument -replace '"', '\"') + '"' } else { $argument }
    }
    $line = ($quoted -join ' ') + ' > "' + $Log + '" 2>&1'
    & cmd.exe /c $line | Out-Null
    $code = $LASTEXITCODE
    if (Test-Path $Log) { Get-Content $Log | ForEach-Object { Write-Host $_ } }
    return $code
}

# ---------------------------------------------------------------- environment
function Read-GitMetadata {
    param([string[]]$Arguments)
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) { return $null }
    $process = New-Object System.Diagnostics.Process
    try {
        $info = New-Object System.Diagnostics.ProcessStartInfo
        $info.FileName = $git.Source
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        # Windows filenames cannot contain quotes; double terminal slashes so
        # the closing quote remains a delimiter in the Win32 argument parser.
        $quotedRepo = '"' + ($repo -replace '(\\+)$', '$1$1') + '"'
        $info.Arguments = '-C ' + $quotedRepo + ' ' + ($Arguments -join ' ')
        $process.StartInfo = $info
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(5000)) {
            $process.Kill()
            return $null
        }
        if ($process.ExitCode -ne 0) { return $null }
        return $stdout.GetAwaiter().GetResult().Trim()
    }
    catch { return $null }
    finally { $process.Dispose() }
}

$envStarted = Get-Date
$gitHead = Read-GitMetadata -Arguments @('rev-parse', '--short', 'HEAD')
$gitBranch = Read-GitMetadata -Arguments @('rev-parse', '--abbrev-ref', 'HEAD')
$gitState = Read-GitMetadata -Arguments @('status', '--porcelain=v1')
$envDetail = [ordered]@{
    repo        = $repo
    python      = (& $Python --version 2>&1 | Out-String).Trim()
    temp        = $env:TEMP
    node        = if (Get-Command node -ErrorAction SilentlyContinue) { (& node --version) } else { $null }
    git_head    = $gitHead
    git_branch  = $gitBranch
    git_dirty   = if ($null -eq $gitState) { $null } else { [bool]$gitState }
    tag         = $Tag
}
Add-Result 'environment' 'pass' ((Get-Date) - $envStarted).TotalSeconds $envDetail

# --------------------------------------------------------------------- unit
if (-not $SkipUnit) {
    $stage = Get-Date
    $log = Join-Path $Out 'unit.log'
    $pytestArgs = @('-m', 'pytest', 'tests', '-q', '-p', 'no:cacheprovider',
                    "--basetemp=$(Join-Path $scratch 'pytest-base')")
    $code = Invoke-Logged -Exe $Python -Arguments $pytestArgs -Log $log
    $tail = (Get-Content $log -Tail 3) -join ' '
    $detail = [ordered]@{ exit_code = $code; summary = $tail.Trim(); log = $log }
    Add-Result 'unit' $(if ($code -eq 0) { 'pass' } else { 'fail' }) ((Get-Date) - $stage).TotalSeconds $detail
}

# -------------------------------------------------------------------- tools
if (-not $SkipTools) {
    $stage = Get-Date
    $manifestScript = Join-Path $repo 'tools\tool_manifest.py'
    $log = Join-Path $Out 'tools.log'
    # Redirect both streams to the log first: a drift report goes to stderr and
    # would otherwise abort the runner under ErrorActionPreference=Stop.
    $code = Invoke-Logged -Exe $Python -Arguments @($manifestScript) -Log $log
    $text = (Get-Content $log -Raw)
    if ($text -match '(\d+) tools, (sha256:[0-9a-f]+)') {
        $toolCount = [int]$matches[1]
        $toolsetHash = $matches[2]
    }
    $detail = [ordered]@{ exit_code = $code; tool_count = $toolCount; toolset_hash = $toolsetHash; log = $log }
    Add-Result 'tools' $(if ($code -eq 0) { 'pass' } else { 'fail' }) ((Get-Date) - $stage).TotalSeconds $detail
}

# ---------------------------------------------------------- source manifest
if ($Manifest) {
    $stage = Get-Date
    $manifestPath = Join-Path $repo 'pipeline\source-manifest.json'
    $log = Join-Path $Out 'source-manifest.log'
    if (-not (Test-Path $manifestPath)) {
        Add-Result 'source-manifest' 'fail' 0 "missing $manifestPath; regenerate with tools/source_manifest.py"
    }
    else {
        $code = Invoke-Logged -Exe $Python -Arguments @((Join-Path $repo 'tools\source_manifest.py'), '--check', $manifestPath) -Log $log
        $detail = [ordered]@{ exit_code = $code; manifest = $manifestPath; log = $log }
        Add-Result 'source-manifest' $(if ($code -eq 0) { 'pass' } else { 'fail' }) ((Get-Date) - $stage).TotalSeconds $detail
    }
}

# ------------------------------------------------------------- provenance
# The licence story depends on inherited text being gone, so this is measured
# the same way the tool set is: a threshold, a report and an exit code.
if ($Provenance) {
    $stage = Get-Date
    $log = Join-Path $Out 'provenance.log'
    $provenanceJson = Join-Path $Out 'provenance.json'
    $code = Invoke-Logged -Exe $Python -Arguments @((Join-Path $repo 'tools\check_provenance.py'),
        '--max-ratio', '0.10', '--json', $provenanceJson) -Log $log
    $rewritten = $null
    $totalPaths = $null
    $pending = @()
    $line = Select-String -Path $log -Pattern '^PROVENANCE (\{.*\})$' | Select-Object -Last 1
    if ($line) {
        $parsed = $line.Matches[0].Groups[1].Value | ConvertFrom-Json
        $rewritten = $parsed.rewritten
        $totalPaths = $parsed.paths
        $pending = @($parsed.pending)
    }
    $detail = [ordered]@{
        exit_code       = $code
        rewritten       = $rewritten
        inherited_paths = $totalPaths
        pending         = $pending
        report          = $provenanceJson
    }
    Add-Result 'provenance' $(if ($code -eq 0) { 'pass' } else { 'fail' }) ((Get-Date) - $stage).TotalSeconds $detail
}

# ----------------------------------------------------------------------- js
if (-not $SkipJs) {
    $stage = Get-Date
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) {
        Add-Result 'js' 'skipped' ((Get-Date) - $stage).TotalSeconds 'node not on PATH'
    }
    else {
        $failed = @()
        $files = Get-ChildItem (Join-Path $repo 'agent') -Filter *.js -File
        foreach ($file in $files) {
            & node --check $file.FullName *> $null
            if ($LASTEXITCODE -ne 0) { $failed += $file.Name }
        }
        $regressions = @()
        foreach ($test in (Get-ChildItem (Join-Path $repo 'tests') -Filter '*_test.js' -File)) {
            $testLog = Join-Path $Out ($test.BaseName + '.log')
            $testCode = Invoke-Logged -Exe $node.Source -Arguments @($test.FullName) -Log $testLog
            $regressions += [ordered]@{ name = $test.Name; exit_code = $testCode; log = $testLog }
            if ($testCode -ne 0) { $failed += $test.Name }
        }
        $detail = [ordered]@{ files = $files.Count; failed = $failed; behavior_regressions = $regressions }
        Add-Result 'js' $(if ($failed.Count -eq 0) { 'pass' } else { 'fail' }) ((Get-Date) - $stage).TotalSeconds $detail
    }
}

# -------------------------------------------------------------------- native
if ($Native) {
    $stage = Get-Date
    $log = Join-Path $Out 'native.log'
    $domainReport = Join-Path $Out 'native-domains.json'
    $code = Invoke-Logged -Exe $Python -Arguments @((Join-Path $repo 'tools\check_native_domains.py'), '--lab', $Lab, '--json', $domainReport) -Log $log
    $parsed = $null
    if (Test-Path $domainReport) { $parsed = Get-Content $domainReport -Raw | ConvertFrom-Json }
    $status = switch ($code) {
        0 { 'pass' }
        2 { 'blocked' }
        default { 'fail' }
    }
    $detail = [ordered]@{
        exit_code = $code
        lab       = $Lab
        reason    = $parsed.reason
        checks    = @($parsed.checks | ForEach-Object { [ordered]@{ domain = $_.domain; status = $_.status; error = $_.error; reason = $_.reason } })
        report    = $domainReport
    }
    Add-Result 'native-domains' $status ((Get-Date) - $stage).TotalSeconds $detail
}
else {
    Add-Result 'native-domains' 'skipped' 0 'requires -Native and an exclusive lab'
}

# -------------------------------------------------------------------- report
$failureStates = @('fail', 'blocked')
$failed = @($results | Where-Object { $failureStates -contains $_.status })
$body = [ordered]@{
    schema     = 'vroid-checks-v1'
    started    = $started.ToString('o')
    finished   = (Get-Date).ToString('o')
    seconds    = [math]::Round(((Get-Date) - $started).TotalSeconds, 2)
    repo       = $repo
    lab        = $Lab
    native     = [bool]$Native
    tool_count = $toolCount
    toolset_hash = $toolsetHash
    stages     = $results.ToArray()
    ok         = ($failed.Count -eq 0)
    exit_code  = $(if ($failed.Count -eq 0) { 0 } else { 1 })
}
$body | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding utf8

Write-Host ''
Write-Host ("report: {0}" -f $reportPath)
if ($toolCount) { Write-Host ("tool set: {0} tools {1}" -f $toolCount, $toolsetHash) }
if ($failed.Count -eq 0) {
    Write-Host 'CHECKS PASSED' -ForegroundColor Green
    exit 0
}
Write-Host ("CHECKS FAILED: " + (($failed | ForEach-Object { "$($_.name)=$($_.status)" }) -join ', ')) -ForegroundColor Red
exit 1
