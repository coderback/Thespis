<#
.SYNOPSIS
  Assigns Ahmed to his issues once he has accepted the repo invitation.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\assign-teammate.ps1
#>
param(
  [string]$Owner = "coderback",
  [string]$Repo = "Thespis",
  [string]$Teammate = "AhmedBokaniUsman"
)
$Full = "$Owner/$Repo"
$done = 0; $failed = 0
foreach ($label in @("owner:ahmed", "owner:both")) {
  $nums = @(gh issue list --repo $Full --state all --label $label --limit 200 --json number --jq '.[].number')
  foreach ($n in $nums) {
    gh issue edit $n --repo $Full --add-assignee $Teammate *> $null
    if ($LASTEXITCODE -eq 0) { $done++ } else { $failed++ }
  }
}
Write-Host "Assigned $Teammate to $done issues."
if ($failed -gt 0) { Write-Host "$failed failed. Has $Teammate accepted the invitation yet?" -ForegroundColor Yellow }
