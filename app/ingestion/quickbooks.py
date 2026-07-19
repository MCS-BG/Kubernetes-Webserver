"""QuickBooks Online adapter: OAuth 2.0 + Accounting API v3.

This is a real integration against Intuit's documented API shape (query
API + Reports API), wired to the common SourceAdapter interface. To go
live you need:
  1. An app registered at developer.intuit.com (gives client_id/secret)
  2. A completed OAuth authorization for the target company (gives
     access_token, refresh_token, realm_id)
  3. A token store that persists + refreshes those tokens (out of scope
     for this MVP -- pass a fresh access_token in for now, or wire
     QuickBooksOAuth.refresh() into your own token storage).

Docs: https://developer.intuit.com/app/developer/qbo/docs/api/accounting
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import requests

from app.ingestion.base import SourceAdapter
from app.models import BankTransaction, GLEntry, TrialBalanceLine

SANDBOX_BASE_URL = "https://sandbox-quickbooks.api.intuit.com"
PRODUCTION_BASE_URL = "https://quickbooks.api.intuit.com"
OAUTH_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
OAUTH_AUTHORIZE_URL = "https://appcenter.intuit.com/connect/oauth2"


class QuickBooksOAuth:
    """Minimal OAuth 2.0 authorization-code helper for QuickBooks Online.

    Token persistence/refresh scheduling is the caller's responsibility --
    this class only performs the HTTP exchange.
    """

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def authorization_url(self, state: str, scope: str = "com.intuit.quickbooks.accounting") -> str:
        return (
            f"{OAUTH_AUTHORIZE_URL}?client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}&response_type=code"
            f"&scope={scope}&state={state}"
        )

    def exchange_code_for_tokens(self, code: str) -> dict:
        resp = requests.post(
            OAUTH_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()

    def refresh(self, refresh_token: str) -> dict:
        resp = requests.post(
            OAUTH_TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


class QuickBooksOnlineAdapter(SourceAdapter):
    name = "quickbooks_online"

    def __init__(
        self,
        access_token: str,
        realm_id: str,
        environment: str = "production",
        default_currency: str = "USD",
    ):
        self._access_token = access_token
        self._realm_id = realm_id
        self._base_url = PRODUCTION_BASE_URL if environment == "production" else SANDBOX_BASE_URL
        self._default_currency = default_currency

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }

    def _query(self, sql: str) -> dict:
        resp = requests.get(
            f"{self._base_url}/v3/company/{self._realm_id}/query",
            params={"query": sql},
            headers=self._headers(),
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()

    def fetch_bank_transactions(self) -> list[BankTransaction]:
        """Approximates the bank feed with recorded money-movement entities
        (Deposit + Purchase). QBO's true bank-feed transactions require a
        connected bank account and are exposed differently per financial
        institution, so this covers what's queryable via the public API.
        """
        out: list[BankTransaction] = []
        for entity, sign in (("Deposit", 1), ("Purchase", -1)):
            payload = self._query(f"SELECT * FROM {entity} MAXRESULTS 1000")
            for row in payload.get("QueryResponse", {}).get(entity, []):
                out.append(
                    BankTransaction(
                        date=datetime.fromisoformat(row["TxnDate"]).date(),
                        amount=sign * Decimal(str(row.get("TotalAmt", 0))),
                        currency=row.get("CurrencyRef", {}).get("value", self._default_currency),
                        description=row.get("PrivateNote", "") or "",
                        reference=str(row.get("DocNumber", "") or row.get("Id", "")),
                        account=row.get("DepositToAccountRef", {}).get("name", "")
                        or row.get("AccountRef", {}).get("name", ""),
                        source_system=self.name,
                    )
                )
        return out

    def fetch_gl_entries(self) -> list[GLEntry]:
        out: list[GLEntry] = []
        payload = self._query("SELECT * FROM JournalEntry MAXRESULTS 1000")
        for je in payload.get("QueryResponse", {}).get("JournalEntry", []):
            txn_date = datetime.fromisoformat(je["TxnDate"]).date()
            currency = je.get("CurrencyRef", {}).get("value", self._default_currency)
            for line in je.get("Line", []):
                detail = line.get("JournalEntryLineDetail", {})
                posting_type = detail.get("PostingType", "Debit")
                signed_amount = Decimal(str(line.get("Amount", 0)))
                if posting_type == "Credit":
                    signed_amount = -signed_amount
                account_ref = detail.get("AccountRef", {})
                out.append(
                    GLEntry(
                        date=txn_date,
                        amount=signed_amount,
                        currency=currency,
                        account_code=account_ref.get("value", ""),
                        account_name=account_ref.get("name", ""),
                        description=line.get("Description", "") or "",
                        reference=str(je.get("DocNumber", "") or je.get("Id", "")),
                        source_system=self.name,
                    )
                )
        return out

    def fetch_trial_balance(self) -> list[TrialBalanceLine]:
        resp = requests.get(
            f"{self._base_url}/v3/company/{self._realm_id}/reports/TrialBalance",
            headers=self._headers(),
            timeout=15.0,
        )
        resp.raise_for_status()
        report = resp.json()
        out: list[TrialBalanceLine] = []
        rows = report.get("Rows", {}).get("Row", [])
        for row in rows:
            col_data = row.get("ColData")
            if not col_data or len(col_data) < 3:
                continue
            account_name = col_data[0].get("value", "")
            account_id = col_data[0].get("id", account_name)
            debit = _parse_amount(col_data[1].get("value"))
            credit = _parse_amount(col_data[2].get("value"))
            out.append(
                TrialBalanceLine(
                    account_code=account_id,
                    account_name=account_name,
                    reported_debit=debit,
                    reported_credit=credit,
                )
            )
        return out


def _parse_amount(value) -> Decimal:
    if not value:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")
