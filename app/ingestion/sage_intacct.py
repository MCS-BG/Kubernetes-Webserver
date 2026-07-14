"""Sage Intacct adapter -- interface defined, live sync pending client demand.

Sage Intacct's XML Gateway (or newer REST API) requires a sender ID/password
plus per-company user credentials or an OAuth 2.0 web services connection.
Once a client on Intacct signs on, implement fetch_gl_entries via the
GENERAL_LEDGER/GLENTRY object and fetch_trial_balance via the
TRIALBALANCE report object, following the same shape as
quickbooks.QuickBooksOnlineAdapter.
"""
from __future__ import annotations

from app.ingestion.base import NotYetImplementedAdapter


class SageIntacctAdapter(NotYetImplementedAdapter):
    name = "sage_intacct"

    def __init__(self, sender_id: str, sender_password: str, company_id: str, user_id: str, user_password: str):
        self.sender_id = sender_id
        self.sender_password = sender_password
        self.company_id = company_id
        self.user_id = user_id
        self.user_password = user_password
