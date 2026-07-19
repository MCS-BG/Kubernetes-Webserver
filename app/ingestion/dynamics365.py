"""Microsoft Dynamics 365 Finance adapter -- interface defined, live sync
pending client demand.

D365 Finance exposes its data model (GeneralJournalAccountEntry,
BankAccountTable, TrialBalance-equivalent inquiries) via OData v4 endpoints
secured with Azure AD (Entra ID) app registrations. Auth is
client-credentials OAuth 2.0 against
https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token, then calls
against https://{env}.operations.dynamics.com/data/{Entity}.
"""
from __future__ import annotations

from app.ingestion.base import NotYetImplementedAdapter


class Dynamics365FinanceAdapter(NotYetImplementedAdapter):
    name = "dynamics365_finance"

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, environment_url: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.environment_url = environment_url
