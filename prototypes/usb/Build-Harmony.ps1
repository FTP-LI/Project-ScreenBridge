param(
    [string]$DevEcoHome = 'C:\Program Files\Huawei\DevEco Studio'
)
$ErrorActionPreference = 'Stop'
$projectDir = Join-Path $PSScriptRoot 'harmony'
$nodeExe = Join-Path $DevEcoHome 'tools\node\node.exe'
$ohpm = Join-Path $DevEcoHome 'tools\ohpm\bin\ohpm.bat'
$hvigor = Join-Path $DevEcoHome 'tools\hvigor\bin\hvigorw.js'
foreach ($required in @($nodeExe, $ohpm, $hvigor, (Join-Path $DevEcoHome 'sdk'))) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing development tool: $required" }
}
$profile = Join-Path $projectDir 'build-profile.json5'
if (-not (Test-Path -LiteralPath $profile)) {
    Copy-Item -LiteralPath (Join-Path $projectDir 'build-profile.template.json5') -Destination $profile
}
$oldPath = $env:PATH
$oldSdk = $env:DEVECO_SDK_HOME
$oldJava = $env:JAVA_HOME
Push-Location $projectDir
try {
    $env:PATH = (Join-Path $DevEcoHome 'tools\node') + ';' + (Join-Path $DevEcoHome 'tools\ohpm\bin') + ';' + $oldPath
    $env:DEVECO_SDK_HOME = Join-Path $DevEcoHome 'sdk'
    $env:JAVA_HOME = Join-Path $DevEcoHome 'jbr'
    & $ohpm install
    if ($LASTEXITCODE -ne 0) { throw "ohpm install failed: $LASTEXITCODE" }
    $buildOutput = @(& $nodeExe $hvigor --mode module -p product=default -p module=entry@default assembleHap --no-daemon 2>&1)
    $buildExit = $LASTEXITCODE
    $buildOutput | ForEach-Object { Write-Output $_ }
    if ($buildExit -ne 0 -or ($buildOutput -join "`n") -match 'BUILD FAILED') {
        throw "Harmony build failed: $buildExit"
    }
    Get-ChildItem -LiteralPath 'entry\build\default\outputs\default' -Filter '*.hap' |
        Select-Object Name, Length
} finally {
    Pop-Location
    $env:PATH = $oldPath
    $env:DEVECO_SDK_HOME = $oldSdk
    $env:JAVA_HOME = $oldJava
}
