#Requires -Version 5.1
<#
.SYNOPSIS
  只读检查指定 USB 身份的 PnP 状态、设备接口和本机构建工具。
.DESCRIPTION
  不安装驱动，不切换 USB 模式，不启动 HDC。输出脱敏 JSON：不含实例路径、序列号或计算机名。
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [Parameter(Mandatory = $true)]
    [uint16]$VendorId,
    [Parameter(Mandatory = $true)]
    [uint16]$ProductId
)

$ErrorActionPreference = 'Stop'

function ConvertTo-HexId {
    param([uint16]$Value)
    return '{0:x4}' -f $Value
}

function Get-PropertyMap {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InstanceId
    )
    $names = @(
        'DEVPKEY_Device_ProblemCode',
        'DEVPKEY_Device_Service',
        'DEVPKEY_Device_DriverInfPath',
        'DEVPKEY_Device_DriverProvider',
        'DEVPKEY_Device_CompatibleIds'
    )
    $map = @{}
    $props = @(Get-PnpDeviceProperty -InstanceId $InstanceId -KeyName $names -ErrorAction SilentlyContinue)
    foreach ($prop in $props) {
        $map[$prop.KeyName] = $prop.Data
    }
    return $map
}

function Test-InterfacePresent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InstanceId
    )
    $regPath = Join-Path 'HKLM:\SYSTEM\CurrentControlSet\Enum' $InstanceId
    if (-not (Test-Path -LiteralPath $regPath)) {
        return $false
    }
    $paramPath = Join-Path $regPath 'Device Parameters'
    if (-not (Test-Path -LiteralPath $paramPath)) {
        return $false
    }
    $item = Get-ItemProperty -LiteralPath $paramPath
    foreach ($name in @('DeviceInterfaceGUID', 'DeviceInterfaceGUIDs')) {
        if ($item.PSObject.Properties.Name -contains $name) {
            $value = $item.$name
            if ($null -ne $value -and -not [string]::IsNullOrWhiteSpace([string]$value)) {
                return $true
            }
        }
    }
    return $false
}

function Get-ToolRecord {
    param(
        [bool]$Present,
        [string]$Version,
        [string]$Path,
        [string]$Note
    )
    $record = [ordered]@{
        present = $Present
        version = $Version
        path    = $Path
    }
    if ($Note) {
        $record.note = $Note
    }
    return $record
}

function Resolve-ExistingCommand {
    param([Parameter(Mandatory = $true)][string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        return $cmd.Source
    }
    return $null
}

function Find-KitTool {
    param([Parameter(Mandatory = $true)][string]$FileName)
    $roots = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Windows Kits'),
        (Join-Path $env:ProgramFiles 'Windows Kits')
    )
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }
        $hit = Get-ChildItem -LiteralPath $root -Filter $FileName -Recurse -File -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($hit) {
            return $hit.FullName
        }
    }
    return $null
}

function Get-FileVersionText {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    $info = (Get-Item -LiteralPath $Path).VersionInfo
    if ($info.ProductVersion) {
        return [string]$info.ProductVersion
    }
    if ($info.FileVersion) {
        return [string]$info.FileVersion
    }
    return $null
}

function Get-PythonFacts {
    param([string]$PythonPath)
    $facts = @{
        version = $null
        pyusb   = $null
        error   = $null
    }
    if (-not (Test-Path -LiteralPath $PythonPath)) {
        return $facts
    }
    $version = & $PythonPath -c "import sys; print(sys.version.split()[0])" 2>&1
    if ($LASTEXITCODE -eq 0) {
        $facts.version = ([string]$version).Trim()
    } else {
        $facts.error = ([string]$version).Trim()
        return $facts
    }
    $pyusb = & $PythonPath -c "import usb; print(getattr(usb, '__version__', 'unknown'))" 2>&1
    if ($LASTEXITCODE -eq 0) {
        $facts.pyusb = ([string]$pyusb).Trim()
    } else {
        $facts.error = ([string]$pyusb).Trim()
    }
    return $facts
}

function Get-DevEcoVersion {
    param([string]$InstallRoot)
    $infoPath = Join-Path $InstallRoot 'product-info.json'
    if (-not (Test-Path -LiteralPath $infoPath)) {
        return $null
    }
    $info = Get-Content -LiteralPath $infoPath -Raw | ConvertFrom-Json
    return [string]$info.version
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$pythonRelative = 'work/venv/Scripts/python.exe'
$pythonPath = Join-Path $repoRoot ($pythonRelative -replace '/', '\')
$devEcoHome = 'C:\Program Files\Huawei\DevEco Studio'
$nodePath = Join-Path $devEcoHome 'tools\node\node.exe'
$sdk10 = 'C:\Program Files (x86)\Windows Kits\10'
$kits81 = 'C:\Program Files (x86)\Windows Kits\8.1'
$vsRoots = @(
    'C:\Program Files\Microsoft Visual Studio',
    'C:\Program Files (x86)\Microsoft Visual Studio'
)

$pythonFacts = Get-PythonFacts -PythonPath $pythonPath
$nodeVersion = $null
if (Test-Path -LiteralPath $nodePath) {
    $nodeVersion = (& $nodePath --version 2>&1 | Out-String).Trim()
}

$clPath = Resolve-ExistingCommand 'cl'
$pwshPath = Resolve-ExistingCommand 'pwsh'
$signPath = Find-KitTool 'signtool.exe'
if (-not $signPath) { $signPath = Resolve-ExistingCommand 'signtool' }
$infVerifPath = Find-KitTool 'infverif.exe'
if (-not $infVerifPath) { $infVerifPath = Resolve-ExistingCommand 'infverif' }
$inf2CatPath = Find-KitTool 'inf2cat.exe'
if (-not $inf2CatPath) { $inf2CatPath = Resolve-ExistingCommand 'inf2cat' }

$vsPresent = $false
foreach ($vsRoot in $vsRoots) {
    if (Test-Path -LiteralPath $vsRoot) {
        $vsPresent = $true
    }
}

$needle = 'VID_{0:X4}&PID_{1:X4}' -f $VendorId, $ProductId
$present = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match [regex]::Escape($needle) })
$devices = @()
foreach ($device in $present) {
    $props = Get-PropertyMap -InstanceId $device.InstanceId
    $problem = $props['DEVPKEY_Device_ProblemCode']
    $problemCode = $null
    if ($null -ne $problem -and "$problem" -ne '') {
        $problemCode = [int]$problem
    }
    $compat = @($props['DEVPKEY_Device_CompatibleIds'])
    $service = $props['DEVPKEY_Device_Service']
    $inf = $props['DEVPKEY_Device_DriverInfPath']
    $provider = $props['DEVPKEY_Device_DriverProvider']
    $devices += [ordered]@{
        vendor_id               = ConvertTo-HexId $VendorId
        product_id              = ConvertTo-HexId $ProductId
        status                  = [string]$device.Status
        class                   = [string]$device.Class
        problem_code            = $problemCode
        service                 = $(if ([string]::IsNullOrWhiteSpace([string]$service)) { $null } else { [string]$service })
        inf                     = $(if ([string]::IsNullOrWhiteSpace([string]$inf)) { $null } else { [string]$inf })
        provider                = $(if ([string]::IsNullOrWhiteSpace([string]$provider)) { $null } else { [string]$provider })
        interface_present       = (Test-InterfacePresent -InstanceId $device.InstanceId)
        winusb_compatible_id    = [bool]($compat | Where-Object { "$_" -match 'MS_COMP_WINUSB' })
    }
}

$ready = @($devices | Where-Object {
        $_.problem_code -eq 0 -and $_.service -and $_.interface_present
    })
$canAttempt = ($devices.Count -eq 1 -and $ready.Count -eq 1)
$hdcRunning = [bool]@(Get-Process -Name 'hdc' -ErrorAction SilentlyContinue)

$report = [ordered]@{
    observed_at_utc    = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    query              = [ordered]@{
        vendor_id  = ConvertTo-HexId $VendorId
        product_id = ConvertTo-HexId $ProductId
    }
    host               = [ordered]@{
        os_caption   = [string](Get-CimInstance Win32_OperatingSystem).Caption
        os_version   = [string](Get-CimInstance Win32_OperatingSystem).Version
        architecture = 'x64'
    }
    tools              = [ordered]@{
        powershell     = (Get-ToolRecord $true $PSVersionTable.PSVersion.ToString() 'Windows PowerShell' $null)
        python         = (Get-ToolRecord (Test-Path -LiteralPath $pythonPath) $pythonFacts.version $pythonRelative $pythonFacts.error)
        pyusb          = (Get-ToolRecord ([bool]$pythonFacts.pyusb) $pythonFacts.pyusb $null $null)
        node           = (Get-ToolRecord (Test-Path -LiteralPath $nodePath) $nodeVersion $nodePath $null)
        deveco         = (Get-ToolRecord (Test-Path -LiteralPath $devEcoHome) (Get-DevEcoVersion $devEcoHome) $devEcoHome $null)
        visual_studio  = (Get-ToolRecord ($vsPresent -or [bool]$clPath) $(if ($clPath) { Get-FileVersionText $clPath } else { $null }) $clPath $(if ($vsPresent -or $clPath) { $null } else { 'Visual Studio and cl.exe were not found' }))
        windows_sdk_10 = (Get-ToolRecord (Test-Path -LiteralPath $sdk10) $null $(if (Test-Path -LiteralPath $sdk10) { $sdk10 } else { $null }) $(if (Test-Path -LiteralPath $sdk10) { $null } else { 'default Windows 10 SDK path is absent' }))
        wdk            = (Get-ToolRecord (Test-Path -LiteralPath $sdk10) $null $(if (Test-Path -LiteralPath $sdk10) { $sdk10 } else { $null }) $(if (Test-Path -LiteralPath $sdk10) { $null } else { 'default Windows 10 WDK path is absent' }))
        signtool       = (Get-ToolRecord ([bool]$signPath) $(if ($signPath) { Get-FileVersionText $signPath } else { $null }) $signPath $null)
        infverif       = (Get-ToolRecord ([bool]$infVerifPath) $(if ($infVerifPath) { Get-FileVersionText $infVerifPath } else { $null }) $infVerifPath $null)
        inf2cat        = (Get-ToolRecord ([bool]$inf2CatPath) $(if ($inf2CatPath) { Get-FileVersionText $inf2CatPath } else { $null }) $inf2CatPath $null)
        pwsh           = (Get-ToolRecord ([bool]$pwshPath) $null $pwshPath 'PowerShell 7 is optional; this script runs on Windows PowerShell 5.1')
        windows_kits_8_1 = (Get-ToolRecord (Test-Path -LiteralPath $kits81) $null $(if (Test-Path -LiteralPath $kits81) { $kits81 } else { $null }) 'Windows Kits 8.1 is not a Windows 11 WDK')
    }
    devices            = $devices
    present_count      = $devices.Count
    can_attempt_access = $canAttempt
    hdc_process_running = $hdcRunning
}

if (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = Join-Path (Get-Location) $OutputPath
}
if ($devices.Count -eq 0) {
    $devicesJson = '[]'
} elseif ($devices.Count -eq 1) {
    $devicesJson = '[' + ($devices[0] | ConvertTo-Json -Depth 5) + ']'
} else {
    $devicesJson = ($devices | ConvertTo-Json -Depth 5)
}
$report.devices = @()
$json = $report | ConvertTo-Json -Depth 6
$json = [regex]::Replace($json, '"devices"\s*:\s*(\[\s*\]|null)', ('"devices": ' + $devicesJson), 1)
$parent = Split-Path -Parent $OutputPath
if ($parent -and -not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent | Out-Null
}
[System.IO.File]::WriteAllText($OutputPath, $json + "`n", [System.Text.UTF8Encoding]::new($false))
Write-Output ("observed={0} present_count={1} can_attempt_access={2} hdc_process_running={3}" -f $report.observed_at_utc, $report.present_count, $report.can_attempt_access, $report.hdc_process_running)
