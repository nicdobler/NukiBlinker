#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Configure Windows Firewall rules for NukiBlinker.

.DESCRIPTION
    Creates inbound firewall rules so LAN devices (speakers, Nuki Bridge,
    phones) can reach the NukiBlinker web UI and audio server on port 8080.

    Run this once on the Docker host (Mini PC) as Administrator.
#>

$Port = 8080
$RuleName = "NukiBlinker (TCP $Port)"

# Remove existing rule if present
$existing = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
if ($existing) {
    Remove-NetFirewallRule -DisplayName $RuleName
    Write-Host "Removed existing rule: $RuleName" -ForegroundColor Yellow
}

# Create inbound TCP rule
New-NetFirewallRule `
    -DisplayName $RuleName `
    -Description "Allow LAN access to NukiBlinker web UI and audio server" `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort $Port `
    -Action Allow `
    -Profile Private `
    | Out-Null

Write-Host "Firewall rule created: $RuleName (TCP $Port, Private profile)" -ForegroundColor Green
Write-Host ""
Write-Host "LAN devices can now reach http://<this-PC-IP>:$Port" -ForegroundColor Cyan
