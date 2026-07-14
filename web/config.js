// Where the FastAPI backend lives, when the widget is hosted separately
// from it (e.g. widget on Azure Static Web Apps, API on Azure Container
// Apps). Leave empty for same-origin deployments -- the widget already
// works that way at /app/ when served directly by the FastAPI app.
//
// Set this to the backend's public URL after deploying it, e.g.:
//   window.API_BASE_URL = "https://finance-close-api.<region>.azurecontainerapps.io";
window.API_BASE_URL = "";
