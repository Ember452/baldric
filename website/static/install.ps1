$ErrorActionPreference = "Stop"

$UvInstallerUrl = "https://astral.sh/uv/install.ps1"

function Find-Uv {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    $candidates = @()
    if ($env:UV_INSTALL_DIR) {
        $candidates += Join-Path $env:UV_INSTALL_DIR "uv.exe"
    }
    if ($env:XDG_BIN_HOME) {
        $candidates += Join-Path $env:XDG_BIN_HOME "uv.exe"
    }
    $candidates += Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    $candidates += Join-Path $env:USERPROFILE ".cargo\bin\uv.exe"

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }

    return $null
}

$uv = Find-Uv
if (-not $uv) {
    Write-Host "Baldric uses uv to manage its isolated Python environment."
    Write-Host "uv was not found, so the official uv installer will be run now."

    $installer = Invoke-RestMethod $UvInstallerUrl
    Invoke-Expression $installer

    $uv = Find-Uv
    if (-not $uv) {
        throw "uv was installed but its executable could not be found. Open a new terminal and run: uv tool install baldric"
    }
}

Write-Host "Installing Baldric with $uv ..."
& $uv tool install baldric
if ($LASTEXITCODE -ne 0) {
    throw "uv could not install Baldric."
}

$toolBin = (& $uv tool dir --bin | Select-Object -Last 1).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "uv could not locate its tool executable directory."
}
$baldric = Join-Path $toolBin "baldric.exe"
if (-not (Test-Path -LiteralPath $baldric -PathType Leaf)) {
    throw "Baldric was installed but $baldric was not found."
}

& $baldric --version
if ($LASTEXITCODE -ne 0) {
    throw "Baldric was installed but could not be started."
}
Write-Host "Baldric is installed. Run: baldric"

$pathEntries = $env:PATH -split ";"
if ($toolBin -notin $pathEntries) {
    Write-Host "Restart PowerShell if 'baldric' is not found; $toolBin must be on PATH."
}
