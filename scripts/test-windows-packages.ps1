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
Invoke-TestProcess $installer @(
    '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/PIPELINETEST=1',
    '/NOCLOSEAPPLICATIONS',
    "/DIR=`"$installed`"", "/LOG=`"$log`""
)
Write-Output 'Silent installation passed (isolated, no registry entry or shortcuts).'
$uninstaller = Join-Path $installed 'unins000.exe'
try {
    Invoke-TestProcess (Join-Path $installed 'RocketLantern.exe') @('--smoke-test') 30000
    Write-Output 'Installed executable smoke test passed.'
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
Invoke-TestProcess (Join-Path $portable 'RocketLantern\RocketLantern.exe') @('--smoke-test') 30000
Write-Output 'Extracted portable ZIP smoke test passed.'
& (Join-Path $projectDirectory '.venv\Scripts\python.exe') `
    (Join-Path $PSScriptRoot 'test-release-publication.py') --package-version $PackageVersion
if ($LASTEXITCODE -ne 0) { throw 'Publication validation failed.' }
Write-Output "Test logs and portable extraction retained in $testRoot"
