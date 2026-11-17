<#
.SYNOPSIS
    Exports the computers Active Directory knows about to discovery.csv for cmdbreview. Read-only.

.DESCRIPTION
    For every computer object: name, operating system, IPv4 address and the last logon date (lastLogonTimestamp, replicated, so it
    can be up to two weeks behind), as the "Active Directory" discovery source. Uses Get-ADComputer from the ActiveDirectory module
    (RSAT); it changes nothing. Disabled computers are left out unless -IncludeDisabled.

    The other discovery sources (Intune, vCenter, a network scan, your discovery tool) export to the same columns:
    Source, Name, Serial, IP, OS, Location, LastSeen. Append them to the same file or keep one file per source and join them.
    cis.csv is your CMDB export (docs/data-format.md has every column).

.EXAMPLE
    .\scripts\Export-DiscoveryAD.ps1 -SearchBase "OU=Computers,DC=contoso,DC=local" -OutputFolder .\data
#>
[CmdletBinding()]
param(
    [string] $SearchBase,
    [string] $OutputFolder = ".\data",
    [switch] $IncludeDisabled
)

$ErrorActionPreference = "Stop"
Import-Module ActiveDirectory
New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null

$params = @{ Filter = "*"; Properties = @("OperatingSystem", "IPv4Address", "LastLogonDate", "Enabled", "DNSHostName") }
if ($SearchBase) { $params.SearchBase = $SearchBase }

$rows = Get-ADComputer @params |
    Where-Object { $IncludeDisabled -or $_.Enabled } |
    ForEach-Object {
        [pscustomobject]@{
            Source   = "Active Directory"
            Name     = $_.Name
            Serial   = ""
            IP       = $_.IPv4Address
            OS       = $_.OperatingSystem
            Location = ""
            LastSeen = if ($_.LastLogonDate) { $_.LastLogonDate.ToString("yyyy-MM-dd") } else { "" }
        }
    }

$path = Join-Path $OutputFolder "discovery.csv"
$rows | Export-Csv -Path $path -NoTypeInformation -Encoding UTF8
Write-Host "discovery.csv: $(@($rows).Count) computers from Active Directory"
