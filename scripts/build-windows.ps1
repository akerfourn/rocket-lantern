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
    $version = & $UvPath run --locked --group build python -c "from importlib.metadata import version; print(version('rocket-lantern'))"
    if ($LASTEXITCODE -ne 0) { throw "Cannot read the application version." }
    & $UvPath run --locked --group build python -c "import platform; assert platform.machine().lower() in ('amd64', 'x86_64'), 'Windows x64 Python is required'"
    if ($LASTEXITCODE -ne 0) { throw "Invalid Python architecture." }
    & $UvPath run --locked --group build python scripts\export-icons.py
    if ($LASTEXITCODE -ne 0) { throw "Icon export failed." }
    & $UvPath run --locked --group build python scripts\compile-translations.py
    if ($LASTEXITCODE -ne 0) { throw "Translation compilation failed." }
    $assetDirectory = Join-Path $projectDirectory "src\rocket_lantern\assets"
    & $UvPath run --locked --group build pyinstaller --noconfirm --clean --onedir --windowed `
        --name RocketLantern --paths src --specpath build --workpath build\pyinstaller `
        --icon "$assetDirectory\rocket-lantern.ico" `
        --add-data "$assetDirectory;rocket_lantern/assets" `
        --distpath dist packaging\windows\launcher.py
    if ($LASTEXITCODE -ne 0) { throw "Executable build failed." }
    $bundleDirectory = Join-Path $projectDirectory "dist\RocketLantern"
    $smoke = Start-Process -FilePath (Join-Path $bundleDirectory "RocketLantern.exe") `
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
    $archive = Join-Path $outputDirectory "RocketLantern-$version-windows-x64-portable.zip"
    Compress-Archive -LiteralPath $bundleDirectory -DestinationPath $archive -Force
    Get-ChildItem -LiteralPath $outputDirectory -Filter "RocketLantern-$version-windows-x64-*" -File |
        Get-FileHash -Algorithm SHA256 | Format-Table Hash, Path -AutoSize
} finally {
    Pop-Location
}
