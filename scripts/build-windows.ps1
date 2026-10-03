param(
    [string]$UvPath = "uv",
    [string]$IsccPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$projectDirectory = Split-Path -Parent $PSScriptRoot
Push-Location $projectDirectory
try {
    if ($env:OS -ne "Windows_NT") { throw "This build must run on Windows." }
    if ($IsccPath -eq "") {
        $compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($null -ne $compiler) {
            $IsccPath = $compiler.Source
        } else {
            $IsccPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        }
    }
    if (-not (Test-Path -LiteralPath $IsccPath -PathType Leaf)) {
        throw "Install Inno Setup 6 or supply -IsccPath with the compiler path."
    }
    & $UvPath sync --locked --group build
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
    $version = & $UvPath run --locked --group build python -c "from importlib.metadata import version; print(version('rl-winloose'))"
    if ($LASTEXITCODE -ne 0) { throw "Cannot read the application version." }
    & $UvPath run --locked --group build python -c "import platform; assert platform.machine().lower() in ('amd64', 'x86_64'), 'Windows x64 Python is required'"
    if ($LASTEXITCODE -ne 0) { throw "Invalid Python architecture." }
    & $UvPath run --locked --group build pyinstaller --noconfirm --clean --onedir --windowed `
        --name RLWinLoss --paths src --specpath build --workpath build\pyinstaller `
        --distpath dist packaging\windows\launcher.py
    if ($LASTEXITCODE -ne 0) { throw "Executable build failed." }
    $bundleDirectory = Join-Path $projectDirectory "dist\RLWinLoss"
    $smoke = Start-Process -FilePath (Join-Path $bundleDirectory "RLWinLoss.exe") `
        -ArgumentList '--smoke-test' -WindowStyle Hidden -PassThru
    if (-not $smoke.WaitForExit(30000)) {
        $smoke.Kill()
        throw "Executable smoke test timed out."
    }
    if ($smoke.ExitCode -ne 0) { throw "Executable smoke test failed." }
    $outputDirectory = Join-Path $projectDirectory "dist\installers"
    & $IsccPath "/DAppVersion=$version" "/DBundleDirectory=$bundleDirectory" `
        "/DOutputDirectory=$outputDirectory" packaging\windows\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }
    $archive = Join-Path $outputDirectory "RLWinLoss-$version-windows-x64-portable.zip"
    Compress-Archive -LiteralPath $bundleDirectory -DestinationPath $archive -Force
    Get-ChildItem -LiteralPath $outputDirectory -File | Where-Object Extension -In ".exe", ".zip" |
        Get-FileHash -Algorithm SHA256 | Format-Table Hash, Path -AutoSize
} finally {
    Pop-Location
}
