<#
.SYNOPSIS
    One-shot Azure setup for LedgeOS/Sumly: creates the backend (Container
    Apps) and widget (Static Web Apps) infrastructure, and wires up the
    GitHub secrets/variables the two workflows in .github/workflows/ expect.

.DESCRIPTION
    This does NOT deploy the app itself -- that's what
    azure-container-apps-backend.yml and azure-static-web-apps-widget.yml do,
    on every push. This script does the one-time resource creation + secret
    wiring those workflows assume already exists (see AZURE_DEPLOYMENT.md).

    Run this from the repo root (it needs the Dockerfile alongside it for
    the initial image build). Requires the Azure CLI (`az`) and GitHub CLI
    (`gh`) to be installed and available on PATH; `gh` must already be
    authenticated (`gh auth login`) with a token that has repo + workflow
    scopes.

.PARAMETER SkipLogin
    Skip `az login` -- use this if you're already authenticated in this
    shell (`az account show` succeeds).

.PARAMETER SubscriptionId
    Azure subscription to use, if you have more than one. Omit to use
    whatever `az account show` currently defaults to.

.EXAMPLE
    .\azure-deploy.ps1 -SkipLogin
    .\azure-deploy.ps1 -SubscriptionId "00000000-0000-0000-0000-000000000000"
#>

[CmdletBinding()]
param(
    [switch]$SkipLogin,
    [string]$SubscriptionId,
    [string]$ResourceGroup = "rg-finance-close",
    [string]$Location = "eastus2",
    [string]$AcrName = "financeclosereg",
    [string]$ContainerAppEnv = "finance-close-env",
    [string]$ContainerAppName = "finance-close-api",
    [string]$StaticWebAppName = "finance-close-widget",
    [string]$GitHubRepo = "MCS-BG/Kubernetes-Webserver",
    [string]$Branch = "claude/finance-app-core-problem-983zcv"
)

$ErrorActionPreference = "Stop"

function Assert-LastExitCode($Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Step (exit code $LASTEXITCODE)"
    }
}

function Write-Step($Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

# --- Prerequisites -----------------------------------------------------

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

# --- Auth ----------------------------------------------------------------

if (-not $SkipLogin) {
    Write-Step "az login"
    az login
    Assert-LastExitCode "az login"
}

if ($SubscriptionId) {
    Write-Step "Setting subscription to $SubscriptionId"
    az account set --subscription $SubscriptionId
    Assert-LastExitCode "az account set"
}

$SubId = az account show --query id -o tsv
Assert-LastExitCode "az account show"
Write-Host "Using subscription: $SubId"

# --- Resource group --------------------------------------------------------

Write-Step "Resource group: $ResourceGroup ($Location)"
az group create --name $ResourceGroup --location $Location | Out-Null
Assert-LastExitCode "az group create"

# --- Backend: ACR + Container Apps environment + initial image -----------

Write-Step "Container Registry: $AcrName"
az acr create --name $AcrName --resource-group $ResourceGroup --sku Basic --admin-enabled true | Out-Null
Assert-LastExitCode "az acr create"

Write-Step "Container Apps environment: $ContainerAppEnv"
az containerapp env create --name $ContainerAppEnv --resource-group $ResourceGroup --location $Location | Out-Null
Assert-LastExitCode "az containerapp env create"

Write-Step "Building initial image via ACR Tasks (from .\Dockerfile)"
az acr build --registry $AcrName --image finance-close-platform:init . | Out-Null
Assert-LastExitCode "az acr build"

# --- Backend: the Container App -------------------------------------------
# ANTHROPIC_API_KEY is deliberately NOT set here -- the CD workflow
# (azure-container-apps-backend.yml) syncs it from the repo secret on every
# deploy, so it's populated the first time that workflow runs.

Write-Step "ACR admin credentials"
$AcrUser = az acr credential show --name $AcrName --query username -o tsv
Assert-LastExitCode "az acr credential show (username)"
$AcrPass = az acr credential show --name $AcrName --query "passwords[0].value" -o tsv
Assert-LastExitCode "az acr credential show (password)"

Write-Step "Container App: $ContainerAppName"
az containerapp create `
    --name $ContainerAppName `
    --resource-group $ResourceGroup `
    --environment $ContainerAppEnv `
    --image "$AcrName.azurecr.io/finance-close-platform:init" `
    --registry-server "$AcrName.azurecr.io" `
    --registry-username $AcrUser `
    --registry-password $AcrPass `
    --target-port 8000 `
    --ingress external | Out-Null
Assert-LastExitCode "az containerapp create"

$BackendFqdn = az containerapp show --name $ContainerAppName --resource-group $ResourceGroup `
    --query properties.configuration.ingress.fqdn -o tsv
Assert-LastExitCode "az containerapp show"
Write-Host "Backend FQDN: https://$BackendFqdn"

# --- GitHub: secret + variables the backend workflow reads ----------------

Write-Step "Service principal for AZURE_CREDENTIALS"
$SpJsonLines = az ad sp create-for-rbac --name "$ContainerAppName-cd" --role contributor `
    --scopes "/subscriptions/$SubId/resourceGroups/$ResourceGroup" --sdk-auth
Assert-LastExitCode "az ad sp create-for-rbac"
$SpJson = ($SpJsonLines -join "`n")
$SpJson | gh secret set AZURE_CREDENTIALS --repo $GitHubRepo
Assert-LastExitCode "gh secret set AZURE_CREDENTIALS"
Remove-Variable SpJson, SpJsonLines

gh variable set ACR_NAME --repo $GitHubRepo --body $AcrName
Assert-LastExitCode "gh variable set ACR_NAME"
gh variable set AZURE_RESOURCE_GROUP --repo $GitHubRepo --body $ResourceGroup
Assert-LastExitCode "gh variable set AZURE_RESOURCE_GROUP"
gh variable set CONTAINER_APP_NAME --repo $GitHubRepo --body $ContainerAppName
Assert-LastExitCode "gh variable set CONTAINER_APP_NAME"

# --- Widget: Static Web App + the secret its workflow reads ---------------

Write-Step "Static Web App: $StaticWebAppName"
az staticwebapp create --name $StaticWebAppName --resource-group $ResourceGroup `
    --location $Location --sku Free | Out-Null
Assert-LastExitCode "az staticwebapp create"

$SwaHostname = az staticwebapp show --name $StaticWebAppName --resource-group $ResourceGroup `
    --query defaultHostname -o tsv
Assert-LastExitCode "az staticwebapp show"

$SwaToken = az staticwebapp secrets list --name $StaticWebAppName --resource-group $ResourceGroup `
    --query properties.apiKey -o tsv
Assert-LastExitCode "az staticwebapp secrets list"

$SwaToken | gh secret set AZURE_STATIC_WEB_APPS_API_TOKEN_FINANCE_WIDGET --repo $GitHubRepo
Assert-LastExitCode "gh secret set AZURE_STATIC_WEB_APPS_API_TOKEN_FINANCE_WIDGET"
Remove-Variable SwaToken

Write-Host "Widget hostname: https://$SwaHostname"

# --- Wire the two together, commit the config change ----------------------

Write-Step "Setting ALLOWED_ORIGINS on the backend"
az containerapp update --name $ContainerAppName --resource-group $ResourceGroup `
    --set-env-vars "ALLOWED_ORIGINS=https://$SwaHostname" | Out-Null
Assert-LastExitCode "az containerapp update (ALLOWED_ORIGINS)"

Write-Step "Pointing web/config.js at the backend"
(Get-Content web/config.js) -replace 'window\.API_BASE_URL = "";', "window.API_BASE_URL = `"https://$BackendFqdn`";" |
    Set-Content web/config.js

git add web/config.js
git commit -m "Point widget at deployed backend ($BackendFqdn)"
Assert-LastExitCode "git commit"
git push origin $Branch
Assert-LastExitCode "git push"

# --- Trigger both workflows against this branch ---------------------------

Write-Step "Triggering both workflows on $Branch"
gh workflow run azure-container-apps-backend.yml --repo $GitHubRepo --ref $Branch
Assert-LastExitCode "gh workflow run (backend)"
gh workflow run azure-static-web-apps-widget.yml --repo $GitHubRepo --ref $Branch
Assert-LastExitCode "gh workflow run (widget)"

Write-Step "Done"
Write-Host "Watch the runs with:  gh run watch --repo $GitHubRepo"
Write-Host "Backend health check: curl https://$BackendFqdn/health"
Write-Host "Demo dashboard:       https://$SwaHostname/app/demo.html"
