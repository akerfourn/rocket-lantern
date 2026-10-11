param(
    [Parameter(Mandatory = $true)]
    [string]$PackageVersion
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectDirectory = Split-Path -Parent $PSScriptRoot
$packageDirectory = Join-Path $projectDirectory 'dist\installers'
$installer = Join-Path $packageDirectory "RocketLantern-$PackageVersion-windows-x64-setup.exe"
$archive = Join-Path $packageDirectory "RocketLantern-$PackageVersion-windows-x64-portable.zip"
foreach ($file in @($installer, $archive)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing package: $file" }
}
$testRoot = Join-Path $projectDirectory "build\package-tests\$([guid]::NewGuid())"
New-Item -ItemType Directory -Path $testRoot | Out-Null

function Invoke-TestProcess([string]$File, [string[]]$Arguments, [int]$Timeout = 120000) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit($Timeout)) {
        $process.Kill()
        throw "Process timed out: $File"
    }
    if ($process.ExitCode -ne 0) { throw "Process failed ($($process.ExitCode)): $File" }
}

$installed = Join-Path $testRoot 'installed'
$log = Join-Path $testRoot 'installation.log'
$installArguments = @(
    '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/PIPELINETEST=1',
    '/NOCLOSEAPPLICATIONS',
    "/DIR=`"$installed`"", "/LOG=`"$log`""
)
Invoke-TestProcess $installer $installArguments
Write-Output 'Silent installation passed (isolated, no registry entry or shortcuts).'
$uninstaller = Join-Path $installed 'unins000.exe'
try {
    $smokeArguments = @('--smoke-test', '--expected-version', $PackageVersion)
    Invoke-TestProcess (Join-Path $installed 'RocketLantern.exe') $smokeArguments 30000
    Write-Output 'Installed executable smoke test passed.'

    $internal = Join-Path $installed '_internal'
    $metadata = @(Get-ChildItem -LiteralPath $internal -Directory -Filter 'rocket_lantern-*.dist-info')
    if ($metadata.Count -ne 1) { throw 'Fresh installation must contain exactly one app distribution.' }
    # Reproduce the leftovers from multiple previous updates, using real metadata.
    foreach ($oldVersion in @('0.0.0', '0.0.1')) {
        $oldMetadata = Join-Path $internal "rocket_lantern-$oldVersion.dist-info"
        Copy-Item -LiteralPath $metadata[0].FullName -Destination $oldMetadata -Recurse
        $metadataFile = Join-Path $oldMetadata 'METADATA'
        $contents = Get-Content -LiteralPath $metadataFile -Raw -Encoding UTF8
        $contents = $contents -replace '(?m)^Version: [^\r\n]+', "Version: $oldVersion"
        Set-Content -LiteralPath $metadataFile -Value $contents -Encoding UTF8
    }
    $otherMetadata = Join-Path $internal 'other_package-0.0.0.dist-info'
    New-Item -ItemType Directory -Path $otherMetadata | Out-Null
    $sentinel = Join-Path $otherMetadata 'keep.txt'
    Set-Content -LiteralPath $sentinel -Value 'unrelated package' -Encoding UTF8

    Invoke-TestProcess $installer $installArguments
    $remaining = @(Get-ChildItem -LiteralPath $internal -Directory -Filter 'rocket_lantern-*.dist-info')
    if ($remaining.Count -ne 1 -or $remaining[0].Name -ne $metadata[0].Name) {
        throw 'Upgrade retained stale application metadata.'
    }
    if ((Get-Content -LiteralPath $sentinel -Raw -Encoding UTF8).Trim() -ne 'unrelated package') {
        throw 'Upgrade changed unrelated package metadata.'
    }
    Invoke-TestProcess (Join-Path $installed 'RocketLantern.exe') $smokeArguments 30000
    Write-Output 'Upgrade with stale metadata passed; unrelated package preserved.'
} finally {
    # Only the newly created test installation may be uninstalled.
    $resolved = [IO.Path]::GetFullPath($uninstaller)
    if (-not $resolved.StartsWith([IO.Path]::GetFullPath($testRoot) + '\')) {
        throw 'Uninstaller is outside the test directory.'
    }
    Invoke-TestProcess $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
}
if (Test-Path -LiteralPath (Join-Path $installed 'RocketLantern.exe')) {
    throw 'Uninstall did not remove the installed executable.'
}
Write-Output 'Silent uninstall passed.'
$portable = Join-Path $testRoot 'portable'
Expand-Archive -LiteralPath $archive -DestinationPath $portable
Invoke-TestProcess (Join-Path $portable 'RocketLantern\RocketLantern.exe') `
    @('--smoke-test', '--expected-version', $PackageVersion) 30000
Write-Output 'Extracted portable ZIP smoke test passed.'
& (Join-Path $projectDirectory '.venv\Scripts\python.exe') `
    (Join-Path $PSScriptRoot 'test-release-publication.py') --package-version $PackageVersion
if ($LASTEXITCODE -ne 0) { throw 'Publication validation failed.' }
Write-Output "Test logs and portable extraction retained in $testRoot"
