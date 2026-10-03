<#
.SYNOPSIS
  One-time setup for the Thespis GitHub repo. Runs as YOU, using your own git and GitHub CLI login.

.DESCRIPTION
  1. Checks git and the GitHub CLI (gh) are installed and that gh is logged in as the repo owner.
  2. Moves the reviewed GitHub config from scripts/github into .github, then makes the first
     commit with your own git identity (no co-author trailers).
  3. Creates the public repo coderback/Thespis and pushes main.
  4. Sets merge rules: squash only, delete branches after merge, auto-merge allowed.
  5. Creates labels and milestones, invites your teammate with write access.
  6. Protects main: no direct pushes, no force-push or deletion, PR plus passing CI required.
  7. Creates the issue series from scripts/issues.json and assigns it.

  Safe to re-run: steps that are already done are skipped.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup-github.ps1
#>
param(
  [string]$Owner = "coderback",
  [string]$Repo = "Thespis",
  [string]$Teammate = "AhmedBokaniUsman",
  [ValidateSet("public", "private")][string]$Visibility = "public",
  [switch]$ForceIssues
)

$ErrorActionPreference = "Continue"
$Full = "$Owner/$Repo"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg) { Write-Host "    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    WARNING: $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host ""; Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }
function Write-Utf8($path, $text) { [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding $false)) }

# ---------------------------------------------------------------- 1. tools and login
Step "Checking git and the GitHub CLI"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail "git is not installed. Install it from https://git-scm.com and re-run." }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  Fail "The GitHub CLI is not installed. Run:  winget install --id GitHub.cli -e   then open a NEW terminal and re-run this script."
}
gh auth status *> $null
if ($LASTEXITCODE -ne 0) {
  Warn "gh is not logged in. Opening the browser login..."
  gh auth login --hostname github.com --git-protocol https --web
  if ($LASTEXITCODE -ne 0) { Fail "GitHub login failed." }
}
$login = (gh api user --jq .login).Trim()
if ($login -ne $Owner) { Fail "gh is logged in as '$login', but the repo belongs to '$Owner'. Run: gh auth login (as $Owner) and re-run." }
$status = (gh auth status 2>&1 | Out-String)
if ($status -notmatch "workflow") {
  Warn "Your GitHub CLI login lacks the 'workflow' permission, which GitHub requires to push the CI file."
  Warn "A browser window will open to add it; approve it there."
  gh auth refresh --hostname github.com --scopes workflow
  if ($LASTEXITCODE -ne 0) { Fail "Could not add the workflow permission. Run: gh auth refresh -h github.com -s workflow" }
}
gh auth setup-git *> $null
Ok "Logged in to GitHub as $login (with workflow permission)"

# ---------------------------------------------------------------- 2. first commit, as you
Step "Preparing the first commit with your git identity"
$gname = (git config user.name)
$gemail = (git config user.email)
if (-not (Test-Path ".git")) {
  git init -b main *> $null
  if ($LASTEXITCODE -ne 0) { git init *> $null; git checkout -b main *> $null }
}
if (-not $gname) {
  $gname = (gh api user --jq '.name // .login').Trim()
  git config user.name "$gname"
}
if (-not $gemail) {
  $uid = (gh api user --jq .id).Trim()
  $gemail = "$uid+$login@users.noreply.github.com"
  git config user.email "$gemail"
}
Ok "Commits will be authored as: $gname <$gemail>"

# Move the GitHub config (CODEOWNERS, PR/issue templates, CI workflow) from scripts/github into .github
if (Test-Path "scripts/github") {
  New-Item -ItemType Directory -Force ".github" | Out-Null
  Copy-Item "scripts/github/*" ".github" -Recurse -Force
  Remove-Item "scripts/github" -Recurse -Force
  Ok "Placed CODEOWNERS, PR and issue templates and the CI workflow in .github/"
}

# Keep PyCharm's sample main.py out of the repo without deleting it from your disk
if ((Test-Path "main.py") -and ((Get-Content "main.py" -Raw) -match "PyCharm")) {
  $exclude = ".git/info/exclude"
  if (-not ((Get-Content $exclude -Raw -ErrorAction SilentlyContinue) -match "(?m)^/main\.py$")) {
    Add-Content $exclude "`n/main.py"
  }
  Ok "PyCharm's sample main.py is left out of the repo (still on your disk; delete it whenever you like)"
}

git rev-parse --verify HEAD *> $null
if ($LASTEXITCODE -ne 0) {
  git add -A
  git commit -m "Initial scaffold: repo structure, CI, contribution rules and issue plan" *> $null
  if ($LASTEXITCODE -ne 0) { Fail "The first commit failed. Run 'git status' to see why." }
  Ok "Created the first commit"
} else {
  Ok "Repository already has commits; skipping"
}

# ---------------------------------------------------------------- 3. create and push the repo
Step "Creating $Full ($Visibility) and pushing main"
gh repo view $Full --json name *> $null
if ($LASTEXITCODE -ne 0) {
  gh repo create $Full "--$Visibility" --source . --remote origin `
    --description "Thespis: an AI/ML toolkit for game developers. First module: Thespis Cast, NPC minds that remember, believe and act offscreen."
  if ($LASTEXITCODE -ne 0) { Fail "Could not create $Full (see the message above)." }
  Ok "Created https://github.com/$Full"
} else {
  Ok "Repo already exists"
}
git remote get-url origin *> $null
if ($LASTEXITCODE -ne 0) { git remote add origin "https://github.com/$Full.git" }
git push -u origin main
if ($LASTEXITCODE -ne 0) {
  Fail "Push failed (see the message above). If it mentions 'workflow', run: gh auth refresh -h github.com -s workflow  then re-run this script."
}
Ok "Pushed main"
gh repo edit $Full --add-topic game-ai --add-topic npc --add-topic llm --add-topic game-development *> $null

# ---------------------------------------------------------------- 4. merge settings
Step "Setting merge rules (squash only, delete merged branches, auto-merge)"
gh api -X PATCH "repos/$Full" -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false `
  -F delete_branch_on_merge=true -F allow_auto_merge=true -F allow_update_branch=true `
  -f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=BLANK -F has_wiki=false *> $null
if ($LASTEXITCODE -eq 0) { Ok "Merge settings applied" } else { Warn "Could not apply merge settings" }

# ---------------------------------------------------------------- 5. labels
Step "Creating labels"
foreach ($d in @("bug", "documentation", "duplicate", "enhancement", "good first issue", "help wanted", "invalid", "question", "wontfix")) {
  gh label delete $d --repo $Full --yes *> $null
}
$labels = @(
  @("owner:tobi", "1d76db", "Tobi owns this"),
  @("owner:ahmed", "5319e7", "Ahmed owns this"),
  @("owner:both", "0e8a16", "Both of us, together"),
  @("area:engine", "c5def5", "thespis/ core and games/ adapters"),
  @("area:client", "d4c5f9", "client/: map, UI, inspector"),
  @("area:shared", "bfdadc", "Contract, integration, docs or decisions for both"),
  @("area:devops", "fef2c0", "Hosting, CI, deployment"),
  @("area:video", "f9d0c4", "Recording, editing, submission"),
  @("type:feature", "a2eeef", "New capability"),
  @("type:task", "ededed", "A piece of work with a done-when check"),
  @("type:test", "bfd4f2", "Tests and harness"),
  @("type:docs", "0075ca", "Documentation"),
  @("type:bug", "d73a4a", "Something is broken"),
  @("P0", "b60205", "The demo cannot ship without this"),
  @("P1", "fbca04", "Important, do after P0"),
  @("P2", "c2e0c6", "Nice to have"),
  @("stretch", "f7c6c7", "Only after Integration 2; behind a feature flag"),
  @("blocked", "000000", "Waiting on something else")
)
foreach ($l in $labels) {
  gh label create $l[0] --color $l[1] --description $l[2] --repo $Full --force *> $null
}
Ok "$($labels.Count) labels ready"

# ---------------------------------------------------------------- 6. milestones
Step "Creating milestones"
$existing = @(gh api "repos/$Full/milestones?state=all&per_page=100" --jq '.[].title')
$milestones = @(
  @("M0 Kickoff", "2026-10-03T11:00:00Z", "Sat 12:00 UK. Contract locked, fixtures, hello-world deployed, models benchmarked, client skeleton."),
  @("M1 Fallback playable", "2026-10-03T17:00:00Z", "Sat 18:00 UK, Integration 1. Demo route playable on the hosted URL with no model."),
  @("M2 Live model on host", "2026-10-03T21:00:00Z", "Sat 22:00 UK, Integration 2. Live-model route and restart test pass on the host."),
  @("M3 Feature freeze", "2026-10-04T08:30:00Z", "Sun 09:30 UK. Bug fixes only after this."),
  @("M4 Submitted", "2026-10-04T11:30:00Z", "Sun 12:30 UK. Video uploaded, form submitted, release tagged. Deadline 14:00."),
  @("Stretch", "2026-10-04T07:30:00Z", "Only after Integration 2. Switch off anything not working by Sun 08:30 UK.")
)
foreach ($m in $milestones) {
  if ($existing -contains $m[0]) { continue }
  gh api "repos/$Full/milestones" -f title="$($m[0])" -f due_on="$($m[1])" -f description="$($m[2])" *> $null
  if ($LASTEXITCODE -ne 0) { Warn "Could not create milestone $($m[0])" }
}
Ok "Milestones ready"

# ---------------------------------------------------------------- 7. invite teammate
Step "Inviting $Teammate with write access"
gh api -X PUT "repos/$Full/collaborators/$Teammate" -f permission=push *> $null
if ($LASTEXITCODE -eq 0) { Ok "Invitation sent. $Teammate must accept it at https://github.com/$Full/invitations" }
else { Warn "Could not invite $Teammate. Check the username." }

# ---------------------------------------------------------------- 8. protect main
Step "Protecting main"
$rulesetNames = @(gh api "repos/$Full/rulesets" --jq '.[].name' 2> $null)
if ($rulesetNames -contains "Protect main") {
  Ok "Ruleset already exists"
} else {
  $ruleset = @'
{
  "name": "Protect main",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "bypass_actions": [],
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "required_linear_history" },
    { "type": "pull_request", "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true,
        "allowed_merge_methods": ["squash"] } },
    { "type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [ { "context": "ci" } ] } }
  ]
}
'@
  $tmp = Join-Path $env:TEMP "thespis-ruleset.json"
  Write-Utf8 $tmp $ruleset
  gh api -X POST "repos/$Full/rulesets" --input $tmp *> $null
  if ($LASTEXITCODE -eq 0) { Ok "main is protected: PRs only, CI must pass, branch must be up to date, no force-push" }
  else { Warn "Could not create the ruleset. Private repos on a free plan cannot enforce it; make the repo public or upgrade." }
  Remove-Item $tmp -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------- 9. issues
Step "Creating the issue series"
$count = [int](gh issue list --repo $Full --state all --limit 500 --json number --jq 'length')
if ($count -gt 0 -and -not $ForceIssues) {
  Ok "Repo already has $count issues; skipping (use -ForceIssues to create them anyway)"
} else {
  $issues = Get-Content (Join-Path $PSScriptRoot "issues.json") -Raw -Encoding UTF8 | ConvertFrom-Json
  $pending = 0
  $tmp = Join-Path $env:TEMP "thespis-issue-body.md"
  foreach ($i in $issues) {
    Write-Utf8 $tmp $i.body
    $ghArgs = @("issue", "create", "--repo", $Full, "--title", $i.title, "--body-file", $tmp,
              "--label", ($i.labels -join ","), "--milestone", $i.milestone)
    if ($i.assignees -contains $Owner) { $ghArgs += @("--assignee", $Owner) }
    $url = (& gh @ghArgs)
    if ($LASTEXITCODE -ne 0 -or -not $url) { Warn "Failed to create: $($i.title)"; continue }
    $n = ($url.Trim() -split "/")[-1]
    if ([string]$n -ne [string]$i.number) { Warn "Issue '$($i.title)' got #$n, expected #$($i.number); 'Depends on' links may be off" }
    if ($i.assignees -contains $Teammate) {
      gh issue edit $n --repo $Full --add-assignee $Teammate *> $null
      if ($LASTEXITCODE -ne 0) { $pending++ }
    }
    Write-Host "    #$n $($i.title)"
  }
  Remove-Item $tmp -ErrorAction SilentlyContinue
  Ok "$($issues.Count) issues created"
  if ($pending -gt 0) {
    Warn "$pending issues could not be assigned to $Teammate yet (invitation not accepted)."
    Write-Host "    Once Ahmed accepts the invite, run:  powershell -ExecutionPolicy Bypass -File scripts\assign-teammate.ps1" -ForegroundColor Yellow
  }
}

# ---------------------------------------------------------------- done
Step "Done"
Write-Host "    Repo:       https://github.com/$Full"
Write-Host "    Issues:     https://github.com/$Full/issues"
Write-Host "    Milestones: https://github.com/$Full/milestones"
Write-Host "    Ahmed must accept the invitation at https://github.com/$Full/invitations"
