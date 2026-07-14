# Step 10: Deployment

This step deliberately doesn't duplicate the detailed runbooks that
already exist -- it's the map to them.

## Option A: Generic Kubernetes

```bash
docker build -t finance-close-platform:latest .
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.example.yaml   # copy it, fill in real values first
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

`k8s/configmap.yaml` holds the non-secret env vars from
[Step 1](01-setup.md)'s table; `k8s/secret.example.yaml` is a template for
`ANTHROPIC_API_KEY` and friends -- never commit a filled-in copy of it.

## Option B: Azure

Static Web Apps hosts static content only -- it can't run this app's
FastAPI/uvicorn process. So the widget and the backend deploy as two
separate pieces:

- Widget (`web/`) -> Azure Static Web Apps, via
  `.github/workflows/azure-static-web-apps-widget.yml`
- Backend (everything else) -> Azure Container Apps, via
  `.github/workflows/azure-container-apps-backend.yml`

Full one-time setup (resource creation, GitHub secrets/variables, wiring
`ALLOWED_ORIGINS` and `web/config.js` to match each other) is in
**[../AZURE_DEPLOYMENT.md](../AZURE_DEPLOYMENT.md)**. Read the caveat at
the top of that doc before running the `az` commands in it -- they were
written without a live Azure CLI session to verify against.

## Before deploying to either: read the roadmap gaps

`../README.md` -> **Roadmap / not yet built** lists what's still MVP-only
and should be addressed before real client data flows through a
production deployment -- most importantly, **persistent storage**: this
platform's store (`app/store.py`) is in-memory. A pod/container restart
or redeploy silently loses every entity, source, reconciliation run, and
chart-of-accounts entry. Fine for a demo or a single working session;
not fine for production until it's backed by Postgres.

## After deploying: re-check Step 9

Whatever you deploy to, set `AUTH_TOKENS` before real users touch it --
the unauthenticated-admin default that makes local dev friction-free is
not an appropriate production posture.
