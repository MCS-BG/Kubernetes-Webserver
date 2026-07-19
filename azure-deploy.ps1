<#
.SYNOPSIS
    One-shot Azure setup + deploy trigger for LedgeOS (with its Sumly P&L
    feature) -- a single FastAPI backend + a static chat/demo widget.

.DESCRIPTION
    This does NOT deploy the app itself on every code change -- that's what
    azure-container-apps-backend.yml and azure-static-web-apps-widget.yml do,
    on every push to `main`. This script does one-time-per-environment
    resource creation + secret/variable wiring those workflows assume
    already exists, using an environment ladder so the same script covers
    every stage: demo (internal showcase) -> stg (pre-customer UAT) ->
    <client-short-code> (a live customer environment).

    LedgeOS is one Python/FastAPI monolith -- Ledge (reconciliation) and
    Sumly (P&L) are routers inside the same app, not separate services.
    There is no worker process and no Azure Blob Storage usage anywhere in
    this codebase, so this script creates exactly one Container App and
    one Static Web App per environment, nothing more.

    Run this from the repo root (it needs the Dockerfile alongside it for
    the initial image build). Requires the Azure CLI (`az`) and GitHub CLI
    (`gh`) on PATH; `gh` must already be authenticated (`gh auth login`)
    with a token that has repo + workflow scopes.

    Every resource-creation step checks whether the resource already exists
    first and skips it if so -- safe to re-run. `-WhatIf` prints every `az`/
    `gh` command it would run (including read-only lookups needed to decide
    skip-vs-create) without executing any of them.

.PARAMETER Environment
    demo | stg | <client-short-code>. Drives every resource name via
    $EnvLabel/$EnvCode -- never hardcode an environment name into a
    resource string elsewhere in this script.

.PARAMETER Stage
    all | infra | apps. `infra` provisions the resource group, Log
    Analytics workspace, Container Apps environment, and ACR. `apps`
    provisions/updates the Container App, Static Web App, and GitHub
    secrets/variables/workflow triggers (requires infra to already exist).

.PARAMETER SkipLogin
    Skip `az login` -- use this if you're already authenticated in this
    shell (`az account show` succeeds).

.PARAMETER SubscriptionId
    Azure subscription name or GUID. Defaults to "atxclouddev".

.PARAMETER TenantId
    Azure AD tenant GUID, passed to `az login --tenant`. Defaults to the
    "Blackbeard Technologies" tenant that owns the atxclouddev
    subscription. Pass an empty string (-TenantId "") to fall back to
    `az login`'s normal default-tenant behavior instead.

.EXAMPLE
    .\azure-deploy.ps1 -WhatIf                    # dry-run, demo environment
    .\azure-deploy.ps1 -SkipLogin                 # real run, already logged in
    .\azure-deploy.ps1 -Environment stg            # promote to staging
    .\azure-deploy.ps1 -Environment acme           # customer "acme" environment
    .\azure-deploy.ps1 -Stage infra                # infra pass only
    .\azure-deploy.ps1 -Stage apps                 # apps pass only (infra must already exist)
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$Environment    = "demo",
    [ValidateSet("all", "infra", "apps")]
    [string]$Stage          = "all",
    [switch]$SkipLogin,
    [string]$SubscriptionId = "atxclouddev",
    [string]$TenantId       = "4c12a2f7-4bd5-4073-9cb9-3576e959c063",
    [string]$Location       = "centralus",
    [string]$AppName        = "ledgeos",
    [string]$ImageName      = "finance-close-platform",
    [string]$GitHubRepo     = "MCS-BG/Kubernetes-Webserver",
    [string]$Branch         = "claude/finance-app-core-problem-983zcv"
)

$ErrorActionPreference = "Stop"

# --- Naming (computed once; never hardcode an environment name elsewhere) --

$EnvLabel   = $Environment.ToLower()
$EnvCodeRaw = ($EnvLabel -replace '[^a-z0-9]', '')
$EnvCode    = $EnvCodeRaw.Substring(0, [Math]::Min($EnvCodeRaw.Length, 8))

$ResourceGroup    = "rg-$AppName-$EnvLabel"
$AcrName          = "acr$AppName$EnvCode"
$ContainerAppEnv  = "cae-$AppName-$EnvLabel"
$LogAnalytics     = "law-$AppName-$EnvLabel"
$ContainerAppName = "ca-$AppName-api"
$StaticWebAppName = "swa-$AppName-$EnvLabel"
$CommonTags       = @("environment=$EnvLabel", "app=$AppName", "project=ledgeos")

# --- Helpers -----------------------------------------------------------

function Assert-LastExitCode {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Step (exit code $LASTEXITCODE)"
    }
}

function Write-Step { param([string]$Msg) Write-Host "`n==> $Msg" -ForegroundColor Cyan }
function Write-OK   { param([string]$Msg) Write-Host "  OK: $Msg" -ForegroundColor Green }
function Write-Skip { param([string]$Msg) Write-Host "  -- $Msg (already exists)" -ForegroundColor DarkGray }
function Write-Warn { param([string]$Msg) Write-Host "  ** $Msg" -ForegroundColor Yellow }
function Write-Err  { param([string]$Msg) Write-Host "  !! $Msg" -ForegroundColor Red }

# WhatIf-aware az/gh wrappers. Args are always passed as an array through the
# call operator (&), never built as a concatenated string through
# Invoke-Expression -- among other things, that guarantees a [WhatIf] log
# line never accidentally echoes a secret piped in via -StdinValue.
function Invoke-Az {
    param([Parameter(Mandatory)][string[]]$CmdArgs)
    if ($WhatIfPreference) {
        Write-Host "  [WhatIf] az $($CmdArgs -join ' ')" -ForegroundColor DarkYellow
        return
    }
    & az @CmdArgs
    Assert-LastExitCode "az $($CmdArgs[0]) $($CmdArgs[1])"
}

# Existence-check wrapper for `az ... show`-style lookups. Plain `2>$null`
# on a native command isn't reliably silent on Windows PowerShell 5.1 --
# combined with $ErrorActionPreference = "Stop", an expected "doesn't exist
# yet" error (e.g. ResourceGroupNotFound) can still surface as a
# script-terminating NativeCommandError even though it's redirected. Scoping
# $ErrorActionPreference to SilentlyContinue for just this call, plus a
# try/catch as a second layer, makes "doesn't exist" reliably resolve to
# $null instead of crashing the script, on both Windows PowerShell and
# PowerShell 7.
function Test-AzShow {
    param([Parameter(Mandatory)][string[]]$CmdArgs)
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        $result = & az @CmdArgs 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        return $result
    } catch {
        return $null
    } finally {
        $ErrorActionPreference = $previousEap
    }
}

function Invoke-Gh {
    param(
        [Parameter(Mandatory)][string[]]$CmdArgs,
        [string]$StdinValue
    )
    if ($WhatIfPreference) {
        $suffix = if ($StdinValue) { "  (stdin value redacted)" } else { "" }
        Write-Host "  [WhatIf] gh $($CmdArgs -join ' ')$suffix" -ForegroundColor DarkYellow
        return
    }
    if ($StdinValue) {
        $StdinValue | & gh @CmdArgs
    } else {
        & gh @CmdArgs
    }
    Assert-LastExitCode "gh $($CmdArgs[0]) $($CmdArgs[1])"
}

Write-Host "Environment : $EnvLabel  (code: $EnvCode)" -ForegroundColor Yellow
Write-Host "Location    : $Location" -ForegroundColor Yellow
Write-Host "Stage       : $Stage$(if ($WhatIfPreference) { '  [WHATIF -- no changes will be made]' })" -ForegroundColor Yellow

# --- Preflight (always runs) ------------------------------------------------

Write-Step "Pre-flight checks"

foreach ($cmd in @("az", "gh")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "'$cmd' is not on PATH. Install it before running this script."
    }
}

if (-not (Test-Path -Path ".\Dockerfile")) {
    throw "Dockerfile not found in the current directory -- run this script from the repo root."
}

gh auth status *> $null
if ($LASTEXITCODE -ne 0) {
    throw "'gh' is not authenticated. Run 'gh auth login' first."
}
Write-OK "gh authenticated"

if (-not $SkipLogin) {
    Write-Step "az login"
    if ($TenantId) {
        az login --tenant $TenantId
    } else {
        az login
    }
    Assert-LastExitCode "az login"
}

az account set --subscription $SubscriptionId
Assert-LastExitCode "az account set"
$SubId = az account show --query id -o tsv
Assert-LastExitCode "az account show"
Write-OK "Subscription: $SubId"

$caExt = az extension list --query "[?name=='containerapp'].name" -o tsv
if ($caExt) {
    Write-Skip "containerapp extension"
} else {
    az extension add --name containerapp --upgrade --only-show-errors
    Assert-LastExitCode "az extension add containerapp"
    Write-OK "containerapp extension installed"
}

# Only Microsoft.App / Web / ContainerRegistry / OperationalInsights --
# deliberately NOT Microsoft.Storage, this app has no blob storage usage.
foreach ($provider in @("Microsoft.App", "Microsoft.Web", "Microsoft.ContainerRegistry", "Microsoft.OperationalInsights")) {
    $state = az provider show --namespace $provider --query registrationState -o tsv
    if ($state -eq "Registered") {
        Write-Skip "$provider"
    } else {
        Write-Warn "$provider is '$state' -- registering (can take a few minutes)"
        if (-not $WhatIfPreference) {
            az provider register --namespace $provider --wait
            Assert-LastExitCode "az provider register $provider"
        }
        Write-OK "$provider registered"
    }
}

# --- Stage: infra ------------------------------------------------------

if ($Stage -in @("all", "infra")) {

    Write-Step "[infra] Resource group -> $ResourceGroup"
    $existingRg = Test-AzShow @("group", "show", "--name", $ResourceGroup, "--query", "name", "-o", "tsv")
    if ($existingRg) {
        Write-Skip $ResourceGroup
    } else {
        Invoke-Az (@("group", "create", "--name", $ResourceGroup, "--location", $Location, "--tags") + $CommonTags)
        Write-OK "Created: $ResourceGroup"
    }

    Write-Step "[infra] Log Analytics workspace -> $LogAnalytics"
    $existingLaw = Test-AzShow @("monitor", "log-analytics", "workspace", "show", "--workspace-name", $LogAnalytics, "--resource-group", $ResourceGroup, "--query", "name", "-o", "tsv")
    if ($existingLaw) {
        Write-Skip $LogAnalytics
    } else {
        Invoke-Az (@("monitor", "log-analytics", "workspace", "create",
                "--workspace-name", $LogAnalytics, "--resource-group", $ResourceGroup,
                "--location", $Location, "--sku", "PerGB2018", "--retention-time", "30",
                "--tags") + $CommonTags)
        Write-OK "Created: $LogAnalytics"
    }

    Write-Step "[infra] Container Apps environment -> $ContainerAppEnv"
    $existingCae = Test-AzShow @("containerapp", "env", "show", "--name", $ContainerAppEnv, "--resource-group", $ResourceGroup, "--query", "name", "-o", "tsv")
    if ($existingCae) {
        Write-Skip $ContainerAppEnv
    } else {
        $LawId  = az monitor log-analytics workspace show --workspace-name $LogAnalytics --resource-group $ResourceGroup --query customerId -o tsv
        $LawKey = az monitor log-analytics workspace get-shared-keys --workspace-name $LogAnalytics --resource-group $ResourceGroup --query primarySharedKey -o tsv
        Invoke-Az (@("containerapp", "env", "create",
                "--name", $ContainerAppEnv, "--resource-group", $ResourceGroup, "--location", $Location,
                "--logs-workspace-id", $LawId, "--logs-workspace-key", $LawKey,
                "--tags") + $CommonTags)
        Write-OK "Created: $ContainerAppEnv"
    }

    Write-Step "[infra] Container Registry -> $AcrName"
    $existingAcr = Test-AzShow @("acr", "show", "--name", $AcrName, "--resource-group", $ResourceGroup, "--query", "name", "-o", "tsv")
    if ($existingAcr) {
        Write-Skip $AcrName
    } else {
        # --admin-enabled true: simplest working option for registry auth on
        # the Container App below. Consider switching to managed identity +
        # AcrPull role assignment before promoting past `demo`.
        Invoke-Az (@("acr", "create", "--name", $AcrName, "--resource-group", $ResourceGroup,
                "--sku", "Basic", "--admin-enabled", "true", "--location", $Location,
                "--tags") + $CommonTags)
        Write-OK "Created: $AcrName"
    }
}

# --- Stage: apps ---------------------------------------------------------

if ($Stage -in @("all", "apps")) {

    Write-Step "[apps] Confirming infra exists"
    $acrCheck = Test-AzShow @("acr", "show", "--name", $AcrName, "--resource-group", $ResourceGroup, "--query", "name", "-o", "tsv")
    $caeCheck = Test-AzShow @("containerapp", "env", "show", "--name", $ContainerAppEnv, "--resource-group", $ResourceGroup, "--query", "name", "-o", "tsv")
    if ((-not $acrCheck -or -not $caeCheck) -and -not $WhatIfPreference) {
        throw "ACR or Container Apps environment not found for '$EnvLabel' -- run with -Stage infra (or -Stage all) first."
    }

    $AcrLoginServer = az acr show --name $AcrName --resource-group $ResourceGroup --query loginServer -o tsv
    $AcrUsername    = az acr credential show --name $AcrName --resource-group $ResourceGroup --query username -o tsv
    $AcrPassword    = az acr credential show --name $AcrName --resource-group $ResourceGroup --query "passwords[0].value" -o tsv

    Write-Step "[apps] Container App -> $ContainerAppName"
    $existingCa = Test-AzShow @("containerapp", "show", "--name", $ContainerAppName, "--resource-group", $ResourceGroup, "--query", "name", "-o", "tsv")
    if ($existingCa) {
        Write-Skip "$ContainerAppName (image/config updates from here are owned by the CD workflow, not this script)"
    } else {
        Write-Host "  Bootstrapping initial image (first-ever create only)..."
        Invoke-Az @("acr", "build", "--registry", $AcrName, "--image", "$($ImageName):init", ".")

        # ANTHROPIC_API_KEY is deliberately NOT set here -- the backend CD
        # workflow (azure-container-apps-backend.yml) syncs it from the repo
        # secret on every deploy, so it's populated the first time that
        # workflow runs (triggered at the end of this script).
        Invoke-Az (@("containerapp", "create",
                "--name", $ContainerAppName, "--resource-group", $ResourceGroup,
                "--environment", $ContainerAppEnv,
                "--image", "$AcrLoginServer/$($ImageName):init",
                "--registry-server", $AcrLoginServer,
                "--registry-username", $AcrUsername,
                "--registry-password", $AcrPassword,
                "--target-port", "8000", "--ingress", "external",
                "--tags") + $CommonTags)
        Write-OK "Created: $ContainerAppName"
    }

    $BackendFqdn = az containerapp show --name $ContainerAppName --resource-group $ResourceGroup --query properties.configuration.ingress.fqdn -o tsv
    if ($BackendFqdn) { Write-Host "  Backend FQDN: https://$BackendFqdn" }

    Write-Step "[apps] Service principal for AZURE_CREDENTIALS"
    $SpName     = "$ContainerAppName-cd"
    $existingSp = Test-AzShow @("ad", "sp", "list", "--display-name", $SpName, "--query", "[0].appId", "-o", "tsv")
    if ($existingSp) {
        Write-Skip $SpName
        Write-Warn "An existing service principal's secret can't be re-retrieved -- run 'az ad sp delete --id $existingSp' and re-run this script if AZURE_CREDENTIALS needs refreshing."
    } else {
        if ($WhatIfPreference) {
            Write-Host "  [WhatIf] az ad sp create-for-rbac --name $SpName --role contributor --scopes /subscriptions/$SubId/resourceGroups/$ResourceGroup --sdk-auth | gh secret set AZURE_CREDENTIALS" -ForegroundColor DarkYellow
        } else {
            $SpJsonLines = az ad sp create-for-rbac --name $SpName --role contributor `
                --scopes "/subscriptions/$SubId/resourceGroups/$ResourceGroup" --sdk-auth
            Assert-LastExitCode "az ad sp create-for-rbac"
            $SpJson = ($SpJsonLines -join "`n")
            Invoke-Gh -CmdArgs @("secret", "set", "AZURE_CREDENTIALS", "--repo", $GitHubRepo) -StdinValue $SpJson
            Remove-Variable SpJson, SpJsonLines
            Write-OK "AZURE_CREDENTIALS set"
        }
    }

    Write-Step "[apps] Repo variables"
    Invoke-Gh @("variable", "set", "ACR_NAME", "--repo", $GitHubRepo, "--body", $AcrName)
    Invoke-Gh @("variable", "set", "AZURE_RESOURCE_GROUP", "--repo", $GitHubRepo, "--body", $ResourceGroup)
    Invoke-Gh @("variable", "set", "CONTAINER_APP_NAME", "--repo", $GitHubRepo, "--body", $ContainerAppName)

    # centralus is a verified-supported Azure Static Web Apps region (unlike
    # southcentralus, which the environment/region wasn't confirmed for) --
    # everything in this script, including the SWA, now deploys to the same
    # $Location.
    Write-Step "[apps] Static Web App -> $StaticWebAppName ($Location)"
    $existingSwa = Test-AzShow @("staticwebapp", "show", "--name", $StaticWebAppName, "--resource-group", $ResourceGroup, "--query", "name", "-o", "tsv")
    if ($existingSwa) {
        Write-Skip $StaticWebAppName
    } else {
        Invoke-Az (@("staticwebapp", "create", "--name", $StaticWebAppName, "--resource-group", $ResourceGroup,
                "--location", $Location, "--sku", "Free", "--tags") + $CommonTags)
        Write-OK "Created: $StaticWebAppName"
    }

    $SwaHostname = az staticwebapp show --name $StaticWebAppName --resource-group $ResourceGroup --query defaultHostname -o tsv
    if ($SwaHostname) {
        $SwaToken = az staticwebapp secrets list --name $StaticWebAppName --resource-group $ResourceGroup --query properties.apiKey -o tsv
        Invoke-Gh -CmdArgs @("secret", "set", "AZURE_STATIC_WEB_APPS_API_TOKEN_FINANCE_WIDGET", "--repo", $GitHubRepo) -StdinValue $SwaToken
        Remove-Variable SwaToken
        Write-Host "  Widget hostname: https://$SwaHostname"
    }

    if ($BackendFqdn -and $SwaHostname) {
        Write-Step "[apps] Setting ALLOWED_ORIGINS on the backend"
        Invoke-Az @("containerapp", "update", "--name", $ContainerAppName, "--resource-group", $ResourceGroup,
            "--set-env-vars", "ALLOWED_ORIGINS=https://$SwaHostname")

        Write-Step "[apps] Pointing web/config.js at the backend"
        $targetLine     = "window.API_BASE_URL = `"https://$BackendFqdn`";"
        $currentContent = Get-Content web/config.js -Raw
        if ($currentContent -match [regex]::Escape($targetLine)) {
            Write-Skip "config.js already points at $BackendFqdn"
        } elseif ($WhatIfPreference) {
            Write-Host "  [WhatIf] would update web/config.js and git commit + push to $Branch" -ForegroundColor DarkYellow
        } else {
            (Get-Content web/config.js) -replace 'window\.API_BASE_URL = ".*";', $targetLine | Set-Content web/config.js
            git add web/config.js
            git commit -m "Point widget at deployed backend ($BackendFqdn)"
            Assert-LastExitCode "git commit"
            git push origin $Branch
            Assert-LastExitCode "git push"
            Write-OK "config.js updated and pushed"
        }
    }

    Write-Step "[apps] Triggering workflows on $Branch"
    Invoke-Gh @("workflow", "run", "azure-container-apps-backend.yml", "--repo", $GitHubRepo, "--ref", $Branch)
    Invoke-Gh @("workflow", "run", "azure-static-web-apps-widget.yml", "--repo", $GitHubRepo, "--ref", $Branch)
}

# --- Summary -------------------------------------------------------------

Write-Host "`n=== Summary [$EnvLabel] ===" -ForegroundColor Green
Write-Host "Resource Group      : $ResourceGroup"
Write-Host "Log Analytics       : $LogAnalytics"
Write-Host "Container Apps Env  : $ContainerAppEnv"
Write-Host "ACR                 : $AcrName.azurecr.io"
Write-Host "Container App       : $ContainerAppName"
if ($BackendFqdn) {
    Write-Host "Backend             : https://$BackendFqdn"
} else {
    Write-Host "Backend             : not created this run -- run with -Stage apps (or -Stage all)"
}
Write-Host "Static Web App      : $StaticWebAppName"
if ($SwaHostname) {
    Write-Host "Widget              : https://$SwaHostname"
} else {
    Write-Host "Widget              : not created this run -- run with -Stage apps (or -Stage all)"
}

Write-Host "`nPromote to next stage:" -ForegroundColor Yellow
Write-Host "  demo -> stg      : .\azure-deploy.ps1 -Environment stg"
Write-Host "  stg  -> customer : .\azure-deploy.ps1 -Environment <client-code>"

if ($BackendFqdn -and $SwaHostname) {
    Write-Host "`nWatch the workflow runs: gh run watch --repo $GitHubRepo"
    Write-Host "Backend health check   : curl https://$BackendFqdn/health"
    Write-Host "Demo dashboard         : https://$SwaHostname/app/demo.html"
}
