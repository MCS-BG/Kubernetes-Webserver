# Deploying to Azure

This app is two independent deployables, because Azure Static Web Apps
hosts static content (plus, optionally, an Azure Functions API) and can't
run this backend's FastAPI/uvicorn process directly:

| Piece | What | Where | Workflow |
|---|---|---|---|
| Widget | `web/index.html` (+ `config.js`) | Azure Static Web Apps | `.github/workflows/azure-static-web-apps-widget.yml` |
| Backend | The FastAPI app (`Dockerfile`) | Azure Container Apps | `.github/workflows/azure-container-apps-backend.yml` |

Both workflows are already committed and will no-op until you complete the
one-time setup below and add the resulting secrets/variables to this repo.
I could not execute any of this myself -- no Azure CLI or credentials are
available in the environment this was built in, and I could not reach
Microsoft's live documentation to double-check the exact current CLI flags
at the time of writing. **Treat the `az` commands below as a strong
starting point, not gospel — verify against `az containerapp --help` /
current Azure docs before running in a real subscription,** especially if
any command errors on a flag that's been renamed or moved since.

## One-time setup

### 1. Resource group

```bash
az group create --name rg-finance-close --location eastus
```

### 2. Backend: Azure Container Registry + Container App

```bash
# Registry the CD workflow pushes images to
az acr create --name financeclosereg --resource-group rg-finance-close \
  --sku Basic --admin-enabled false

# Container Apps environment (the shared runtime the app lives in)
az containerapp env create --name finance-close-env \
  --resource-group rg-finance-close --location eastus

# Build+push an initial image so the app has something to start from
az acr build --registry financeclosereg --image finance-close-platform:init .

# The app itself -- fill in a real ANTHROPIC_API_KEY, and ALLOWED_ORIGINS
# once you know the widget's Static Web Apps URL (step 3)
az containerapp create \
  --name finance-close-api \
  --resource-group rg-finance-close \
  --environment finance-close-env \
  --image financeclosereg.azurecr.io/finance-close-platform:init \
  --registry-server financeclosereg.azurecr.io \
  --target-port 8000 \
  --ingress external \
  --env-vars ANTHROPIC_API_KEY=secretref:anthropic-api-key ALLOWED_ORIGINS=https://<your-widget>.azurestaticapps.net \
  --secrets anthropic-api-key=<your-real-key>

# Note the FQDN this prints (or fetch it any time with the line below) --
# that's the backend URL the widget's config.js needs.
az containerapp show --name finance-close-api --resource-group rg-finance-close \
  --query properties.configuration.ingress.fqdn -o tsv
```

Grant the workflow's service principal push/deploy rights, then add it as
a GitHub secret:

```bash
az ad sp create-for-rbac --name finance-close-cd \
  --role contributor \
  --scopes /subscriptions/<sub-id>/resourceGroups/rg-finance-close \
  --sdk-auth
# Paste the resulting JSON into the GitHub repo secret: AZURE_CREDENTIALS
```

Then set these repo **variables** (Settings → Secrets and variables →
Actions → Variables), matching what you created above:

- `ACR_NAME` = `financeclosereg`
- `AZURE_RESOURCE_GROUP` = `rg-finance-close`
- `CONTAINER_APP_NAME` = `finance-close-api`

### 3. Widget: Azure Static Web Apps

```bash
az staticwebapp create \
  --name finance-close-widget \
  --resource-group rg-finance-close \
  --location eastus2 \
  --sku Free
```

In the Azure Portal, open the new Static Web App → **Manage deployment
token** → copy it → add it as the GitHub repo secret
`AZURE_STATIC_WEB_APPS_API_TOKEN_FINANCE_WIDGET` (the exact name the
workflow expects).

Edit `web/config.js` and set `API_BASE_URL` to the Container App FQDN from
step 2, then commit:

```js
window.API_BASE_URL = "https://finance-close-api.<region>.azurecontainerapps.io";
```

### 4. Push to `main`

Both workflows trigger on push to `main` (or run manually via
**Actions → workflow → Run workflow**). After both succeed, the widget's
URL (`https://finance-close-widget.azurestaticapps.net`) is the one you'd
actually give to a user.

## Keeping CORS correct

`ALLOWED_ORIGINS` on the backend and `API_BASE_URL` in the widget have to
agree, or the browser will block the widget's requests. If you rename or
recreate either resource, update both sides:

- Backend: `az containerapp update --name finance-close-api --resource-group rg-finance-close --set-env-vars ALLOWED_ORIGINS=https://<new-widget-url>`
- Widget: edit `web/config.js`, commit, let the widget workflow redeploy.

## Local sanity check before you deploy

Both pieces already work together same-origin (no CORS needed) via
`uvicorn app.main:app` + `http://localhost:8000/app/` -- see the README.
Confirming that still works is the cheapest way to catch a regression
before spending time on the Azure-specific wiring above.
