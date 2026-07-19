# Deploying to Azure

LedgeOS is one Python/FastAPI application -- Ledge (reconciliation) and
Sumly (P&L) are routers inside the same backend, not separate services.
It's still two independent *deployables*, because Azure Static Web Apps
hosts static content (plus, optionally, an Azure Functions API) and can't
run this backend's FastAPI/uvicorn process directly:

| Piece | What | Where | Workflow |
|---|---|---|---|
| Widget | `web/index.html` + `demo.html` (+ `config.js`) | Azure Static Web Apps | `.github/workflows/azure-static-web-apps-widget.yml` |
| Backend | The FastAPI app (`Dockerfile`) | Azure Container Apps | `.github/workflows/azure-container-apps-backend.yml` |

**Prefer running `azure-deploy.ps1`** (repo root) over the manual commands
below -- it does the same one-time setup, idempotently (safe to re-run),
across an environment ladder (see next section), and wires the resulting
secrets/variables into this repo automatically via `gh`. The commands in
this doc are the manual-recovery equivalent, for when you need to inspect
or fix one specific step by hand.

```powershell
.\azure-deploy.ps1 -WhatIf          # dry-run first -- prints every az/gh command, changes nothing
.\azure-deploy.ps1 -SkipLogin       # real run, if already `az login`'d in this shell
```

## Environment ladder

One script, one `-Environment` value, every stage:

```
[local]  ->  demo  ->  stg  ->  <client-code>
                                (e.g. acme, northstar)
```

| Stage | `-Environment` | Purpose | Example resource group |
|---|---|---|---|
| Demo / MVP | `demo` (default) | Internal showcase, customer preview | `rg-ledgeos-demo` |
| Staging / UAT | `stg` | Pre-customer validation | `rg-ledgeos-stg` |
| Customer | `<client-code>` | Live customer environment | `rg-ledgeos-acme` |

Naming rules the script enforces:

- **Resource group / Container Apps environment / Log Analytics / Static
  Web App**: kebab suffix -- `rg-ledgeos-demo`, `cae-ledgeos-stg`.
- **ACR**: alphanumeric only, no suffix separator -- `acrledgeosdemo`,
  `acrledgeosacme` (name must also be globally unique across all of
  Azure, not just this subscription).
- **Container App**: no environment suffix -- `ca-ledgeos-api` -- since it
  already lives inside its environment's own resource group.
- **Tags**: every resource gets `environment=<label>`, `app=ledgeos`,
  `project=ledgeos`.

Never hardcode an environment name into a resource string -- always derive
it from `-Environment` (the script does this via `$EnvLabel`/`$EnvCode`).

Promote to the next stage:

```powershell
.\azure-deploy.ps1 -Environment stg            # demo -> stg
.\azure-deploy.ps1 -Environment <client-code>   # stg -> customer
```

## Prerequisites

```bash
# 1. Verify login + pick the right subscription
az account show --query "{name:name, sub:id, tenant:tenantId}" -o table
az account set --subscription atxclouddev

# 2. Register required resource providers (one-time per subscription;
#    the script checks and only registers what isn't already registered)
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.Web --wait
az provider register --namespace Microsoft.ContainerRegistry --wait
az provider register --namespace Microsoft.OperationalInsights --wait
# NOT Microsoft.Storage -- this app has no blob storage usage anywhere.

# 3. Ensure the containerapp CLI extension
az extension add --name containerapp --upgrade
```

## One-time setup (manual equivalent of `azure-deploy.ps1 -Stage infra`)

### 1. Resource group

```bash
az group create --name rg-ledgeos-demo --location centralus
```

### 2. Log Analytics workspace + Container Apps environment

```bash
az monitor log-analytics workspace create \
  --workspace-name law-ledgeos-demo --resource-group rg-ledgeos-demo \
  --location centralus --sku PerGB2018 --retention-time 30

LAW_ID=$(az monitor log-analytics workspace show --workspace-name law-ledgeos-demo \
  --resource-group rg-ledgeos-demo --query customerId -o tsv)
LAW_KEY=$(az monitor log-analytics workspace get-shared-keys --workspace-name law-ledgeos-demo \
  --resource-group rg-ledgeos-demo --query primarySharedKey -o tsv)

az containerapp env create --name cae-ledgeos-demo \
  --resource-group rg-ledgeos-demo --location centralus \
  --logs-workspace-id "$LAW_ID" --logs-workspace-key "$LAW_KEY"
```

### 3. Container Registry

```bash
# --admin-enabled true: the Container App below authenticates to the
# registry with admin username/password rather than a managed identity --
# simplest option that works without extra role-assignment steps. Consider
# switching to managed identity + an AcrPull role assignment before
# promoting past `demo`.
az acr create --name acrledgeosdemo --resource-group rg-ledgeos-demo \
  --sku Basic --admin-enabled true
```

## Backend: Container App (manual equivalent of `-Stage apps`, backend half)

```bash
# Build+push an initial image so the app has something to start from
az acr build --registry acrledgeosdemo --image finance-close-platform:init .

ACR_USER=$(az acr credential show --name acrledgeosdemo --query username -o tsv)
ACR_PASS=$(az acr credential show --name acrledgeosdemo --query "passwords[0].value" -o tsv)

# ANTHROPIC_API_KEY is deliberately NOT set here -- the backend CD workflow
# syncs it from the repo secret ANTHROPIC_API_KEY on every deploy instead
# (az containerapp secret set + --set-env-vars ANTHROPIC_API_KEY=secretref:...).
# ALLOWED_ORIGINS is set below, once the widget's URL is known (step 4).
az containerapp create \
  --name ca-ledgeos-api \
  --resource-group rg-ledgeos-demo \
  --environment cae-ledgeos-demo \
  --image acrledgeosdemo.azurecr.io/finance-close-platform:init \
  --registry-server acrledgeosdemo.azurecr.io \
  --registry-username "$ACR_USER" \
  --registry-password "$ACR_PASS" \
  --target-port 8000 \
  --ingress external

# Note the FQDN this prints (or fetch it any time with the line below) --
# that's the backend URL the widget's config.js needs.
az containerapp show --name ca-ledgeos-api --resource-group rg-ledgeos-demo \
  --query properties.configuration.ingress.fqdn -o tsv
```

Grant a service principal push/deploy rights, then add it as a GitHub
secret:

```bash
az ad sp create-for-rbac --name ca-ledgeos-api-cd \
  --role contributor \
  --scopes /subscriptions/<sub-id>/resourceGroups/rg-ledgeos-demo \
  --sdk-auth
# Paste the resulting JSON into the GitHub repo secret: AZURE_CREDENTIALS
```

Then set these repo **variables** (Settings -> Secrets and variables ->
Actions -> Variables), matching what you created above:

- `ACR_NAME` = `acrledgeosdemo`
- `AZURE_RESOURCE_GROUP` = `rg-ledgeos-demo`
- `CONTAINER_APP_NAME` = `ca-ledgeos-api`

## Widget: Azure Static Web Apps

`centralus` is a verified-supported Azure Static Web Apps region, so
everything -- resource group, ACR, Container Apps environment, and the
SWA -- deploys to the same region now.

```bash
az staticwebapp create \
  --name swa-ledgeos-demo \
  --resource-group rg-ledgeos-demo \
  --location centralus \
  --sku Free
```

Get its deployment token and add it as the GitHub repo secret
`AZURE_STATIC_WEB_APPS_API_TOKEN_FINANCE_WIDGET` (the exact name the
workflow expects):

```bash
az staticwebapp secrets list --name swa-ledgeos-demo \
  --resource-group rg-ledgeos-demo --query properties.apiKey -o tsv
```

Edit `web/config.js` and set `API_BASE_URL` to the Container App FQDN from
the backend step above, then commit:

```js
window.API_BASE_URL = "https://ca-ledgeos-api.<region>.azurecontainerapps.io";
```

## Push to `main` (or trigger manually)

Both workflows trigger on push to `main` (or run manually via **Actions ->
workflow -> Run workflow**, or `gh workflow run <file> --ref <branch>` for
a feature branch). After both succeed, the widget's URL
(`https://swa-ledgeos-demo.azurestaticapps.net`) is the one you'd
actually give to a user.

## Keeping CORS correct

`ALLOWED_ORIGINS` on the backend and `API_BASE_URL` in the widget have to
agree, or the browser will block the widget's requests. If you rename or
recreate either resource, update both sides:

- Backend: `az containerapp update --name ca-ledgeos-api --resource-group rg-ledgeos-demo --set-env-vars ALLOWED_ORIGINS=https://<new-widget-url>`
- Widget: edit `web/config.js`, commit, let the widget workflow redeploy.

## Current limitation: one environment wired at a time

Both GitHub Actions workflows trigger only on push to `main` and read
single, repo-global secrets/variables (`AZURE_CREDENTIALS`, `ACR_NAME`,
`AZURE_RESOURCE_GROUP`, `CONTAINER_APP_NAME`,
`AZURE_STATIC_WEB_APPS_API_TOKEN_FINANCE_WIDGET`). Only one environment's
resources can be "live" in CI at a time -- running `azure-deploy.ps1` for
a different `-Environment` repoints all of these at the new environment,
including overwriting `web/config.js` with that environment's backend
URL. Promoting `demo -> stg -> <client-code>` today means each promotion
takes over the CD pipeline; it doesn't run in parallel with the previous
stage. True parallel, independent CD per environment would need [GitHub
Environments](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment)
(repo Settings -> Environments, each with its own secrets/variables) --
a real future improvement, not built today.

## What not to do

- **Never** hardcode an environment name into a resource name string --
  always derive it from `-Environment`.
- **Never** commit an ACR password, service-principal JSON, or SWA
  deployment token to source control.
- **Never** remove `azure-deploy.ps1`'s idempotency guards (the
  `if ($existing...) { Write-Skip }` checks) -- they're what makes
  re-running the script safe.
- **Never** run `-Stage infra` against an existing customer environment
  without a `-WhatIf` pass first.
- **Never** skip `-WhatIf` before the first real run against a new
  subscription.

## Local sanity check before you deploy

Both pieces already work together same-origin (no CORS needed) via
`uvicorn app.main:app` + `http://localhost:8000/app/` -- see the README.
Confirming that still works is the cheapest way to catch a regression
before spending time on the Azure-specific wiring above.
