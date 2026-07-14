"""NetSuite adapter -- interface defined, live sync pending client demand.

Per the connector-priority rule: build the live implementation when a
specific client needs it, not speculatively. When that happens, the
natural path is NetSuite's SuiteQL/REST API
(https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1540391670.html)
using Token-Based Authentication (TBA/OAuth 1.0a). SuiteQL can express the
bank/GL/trial-balance queries directly in SQL, so mapping is comparable to
the QuickBooks JournalEntry query in quickbooks.py.
"""
from __future__ import annotations

from app.ingestion.base import NotYetImplementedAdapter


class NetSuiteAdapter(NotYetImplementedAdapter):
    name = "netsuite"

    def __init__(self, account_id: str, token_id: str, token_secret: str, consumer_key: str, consumer_secret: str):
        self.account_id = account_id
        self.token_id = token_id
        self.token_secret = token_secret
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
