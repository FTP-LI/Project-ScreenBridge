<#
.SYNOPSIS
  Preview or remove superseded self-signed ScreenBridge IDD driver packages.

.DESCRIPTION
  Default is a dry run: it only lists candidates and writes an audit snapshot.
  Only packages with Provider = ScreenBridge, original INF = screenbridgeidd.inf
  and signer containing "ScreenBridge Development" are candidates. The USB
  WinUSB package (oem121.inf) and the current IDD package are kept by default.
  Use -Apply in an elevated Windows PowerShell session to actually delete.
  Never removes packages from other providers or any USB/display driver that is
  not a superseded ScreenBridge IDD package.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\Clean-OldDisplayDrivers.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\Clean-OldDisplayDrivers.ps1 -Apply

.NOTES
  The local execution policy is Restricted. Process-scoped Bypass only affects
  this one invocation and does not change machine or user policy.
#>
param(
    [switch]$Apply,
    [string[]]$Keep = @('oem121.inf', 'oem138.inf'),
    [string]$AuditDir = ''
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if ([string]::IsNullOrEmpty($AuditDir)) { $AuditDir = Join-Path $root 'work' }
if (-not (Test-Path -LiteralPath $AuditDir)) { New-Item -ItemType Directory -Path $AuditDir | Out-Null }

$raw = @(pnputil /enum-drivers 2>$null)
$text = $raw -join "`n"
Set-Content -LiteralPath (Join-Path $AuditDir 's0-driver-audit-before.txt') -Value $text -Encoding UTF8

# Match on ASCII values only. pnputil prints localized key names; Windows
# PowerShell 5.1 reads UTF-8 scripts without BOM as ANSI, so non-ASCII
# literals in regex would be corrupted. Key names are therefore wildcarded.
$blocks = [regex]::Split($text, "(?m)(?=^[^\r\n:]*:\s*oem\d+\.inf\s*$)")
$candidates = @()
foreach ($block in $blocks) {
    if ($block -notmatch '(?m)^[^\r\n:]*:\s*(oem\d+\.inf)\s*$') { continue }
    $oem = $Matches[1]
    if ($block -notmatch '(?m)^[^\r\n:]*:\s*ScreenBridge\s*$') { continue }
    if ($block -notmatch '(?m)^[^\r\n:]*:\s*screenbridgeidd\.inf\s*$') { continue }
    if ($block -notmatch 'ScreenBridge Development') { continue }
    $version = ''
    if ($block -match '(?m)^[^\r\n:]*:\s*(\d{1,2}/\d{1,2}/\d{4}\s+[\d.]+)') { $version = $Matches[1] }
    if ($Keep -contains $oem) { continue }
    $candidates += [pscustomobject]@{ Oem = $oem; Original = 'screenbridgeidd.inf'; Version = $version }
}

if ($candidates.Count -eq 0) {
    Write-Output 'No superseded ScreenBridge IDD packages found.'
    exit 0
}

Write-Output 'Superseded ScreenBridge IDD packages (dry-run list):'
$candidates | Format-Table Oem, Original, Version -AutoSize | Out-String | Write-Output
Write-Output ('Kept by default: ' + ($Keep -join ', '))
Write-Output ('Audit snapshot: ' + (Join-Path $AuditDir 's0-driver-audit-before.txt'))

if (-not $Apply) {
    Write-Output 'DRY RUN: nothing was removed. Re-run with -Apply in an elevated session.'
    exit 0
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Output 'ERROR: elevation required. Open an administrator PowerShell session and re-run with -Apply.'
    exit 1
}

$connected = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_18D1|VID_12D1' })
if ($connected.Count -gt 0) {
    Write-Output 'ERROR: a target USB device is connected. Disconnect it before removing driver packages.'
    exit 1
}

foreach ($item in $candidates) {
    Write-Output ('Removing ' + $item.Oem + ' (' + $item.Version + ')')
    $output = @(pnputil /delete-driver $item.Oem /uninstall /force 2>&1)
    $code = $LASTEXITCODE
    $output | ForEach-Object { Write-Output ('  ' + $_) }
    if ($code -ne 0) {
        Write-Output ('ERROR: pnputil failed for ' + $item.Oem + ' with exit code ' + $code + '. Stopping.')
        exit 1
    }
}

$after = @(pnputil /enum-drivers 2>$null)
Set-Content -LiteralPath (Join-Path $AuditDir 's0-driver-audit-after.txt') -Value ($after -join "`n") -Encoding UTF8
Write-Output 'Done. Before/after audit snapshots are in the work directory.'
