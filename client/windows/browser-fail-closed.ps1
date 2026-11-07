#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Chrome / Edge fail-closed policy for a protected domain list (docs/07, layer A).

.DESCRIPTION
  Writes per-user browser policies:
    ProxySettings     inline mandatory PAC: protected domains -> PROXY 127.0.0.1:<Port> only (no DIRECT);
                      everything else -> PROXY 127.0.0.1:<Port>; DIRECT
    WebRtcIPHandling  disable_non_proxied_udp
  The first Install saves the previous values; Remove restores them.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\client\windows\browser-fail-closed.ps1 `
    -Action Install -DomainsFile .\templates\protected-domains.example.json -Port 3067
#>
param(
    [ValidateSet('Install', 'Remove')][string]$Action = 'Install',
    [string]$DomainsFile = (Join-Path $PSScriptRoot '..\..\templates\protected-domains.example.json'),
    [ValidateRange(1, 65535)][int]$Port = 3067
)
$ErrorActionPreference = 'Stop'
$stateDir = Join-Path $env:LOCALAPPDATA 'ProxyFailClosed'
$backupFile = Join-Path $stateDir 'browser-policy-backup.json'
$targets = @('HKCU:\Software\Policies\Google\Chrome', 'HKCU:\Software\Policies\Microsoft\Edge')
$valueNames = @('ProxySettings', 'WebRtcIPHandling')

if ($Action -eq 'Remove') {
    if (!(Test-Path -LiteralPath $backupFile)) { throw 'No saved policy backup found.' }
    $saved = Get-Content -Raw -Encoding UTF8 -LiteralPath $backupFile | ConvertFrom-Json
    foreach ($entry in $saved) {
        if ($entry.Exists) {
            New-Item -Path $entry.Path -Force | Out-Null
            New-ItemProperty -LiteralPath $entry.Path -Name $entry.Name -PropertyType String -Value $entry.Value -Force | Out-Null
        } elseif (Test-Path -LiteralPath $entry.Path) {
            Remove-ItemProperty -LiteralPath $entry.Path -Name $entry.Name -ErrorAction SilentlyContinue
        }
    }
    Remove-Item -LiteralPath $backupFile -Force
    Write-Output 'Original browser policies restored. Reload browser policies or restart the browsers.'
    exit
}

# Windows PowerShell 5.1 emits a JSON array as one object; foreach enumerates it explicitly.
$raw = Get-Content -Raw -Encoding UTF8 -LiteralPath $DomainsFile | ConvertFrom-Json
$domains = @(foreach ($item in $raw) {
    $name = "$item".Trim().ToLower()
    if ($name -match '^[a-z0-9.-]+\.[a-z0-9-]+$') { $name }
})
if ($domains.Count -eq 0) { throw "No valid domains in $DomainsFile" }

if (!(Test-Path -LiteralPath $backupFile)) {
    New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
    $saved = foreach ($target in $targets) {
        $props = if (Test-Path -LiteralPath $target) { Get-ItemProperty -LiteralPath $target } else { $null }
        foreach ($name in $valueNames) {
            $prop = if ($props) { $props.PSObject.Properties[$name] } else { $null }
            [pscustomobject]@{Path = $target; Name = $name; Exists = ($null -ne $prop); Value = if ($prop) { $prop.Value } else { $null } }
        }
    }
    $saved | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 -LiteralPath $backupFile
}

$domainJson = ConvertTo-Json -Compress -InputObject @($domains)
$pac = @"
function FindProxyForURL(url, host) {
  host = host.toLowerCase();
  var protectedDomains = $domainJson;
  for (var i = 0; i < protectedDomains.length; i++) {
    var d = protectedDomains[i];
    if (host === d || (host.length > d.length && host.substring(host.length-d.length-1) === '.'+d)) {
      return 'PROXY 127.0.0.1:$Port';
    }
  }
  if (host === 'localhost' || host.indexOf('.') < 0 || host.indexOf('127.') === 0 || host === '[::1]') return 'DIRECT';
  return 'PROXY 127.0.0.1:$Port; DIRECT';
}
"@
$pacUrl = 'data:application/x-ns-proxy-autoconfig;base64,' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pac))
$policy = @{ProxyMode = 'pac_script'; ProxyPacUrl = $pacUrl; ProxyPacMandatory = $true } | ConvertTo-Json -Compress
foreach ($target in $targets) {
    New-Item -Path $target -Force | Out-Null
    New-ItemProperty -LiteralPath $target -Name ProxySettings -PropertyType String -Value $policy -Force | Out-Null
    New-ItemProperty -LiteralPath $target -Name WebRtcIPHandling -PropertyType String -Value 'disable_non_proxied_udp' -Force | Out-Null
}
Write-Output "Installed for this Windows user (Chrome, Edge): $($domains.Count) protected domains require 127.0.0.1:$Port with no DIRECT fallback."
Write-Output 'Reload chrome://policy and edge://policy, or restart the browsers. Other Windows users must install separately.'
