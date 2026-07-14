"""Bank-to-GL reconciliation matching engine.

Runs a series of increasingly permissive passes -- exact match, then
date-window match, then fuzzy-description match, then amount-mismatch
detection for otherwise-clear pairs -- so that whatever's left over at the
end is a genuine exception worth a human's attention, not just noise.
"""
from __future__ import annotations

from decimal import Decimal
from difflib import SequenceMatcher

from app.config import settings as default_settings
from app.models import (
    BankTransaction,
    Flag,
    FlagSeverity,
    FlagType,
    GLEntry,
    MatchedPair,
    ReconciliationResult,
)


def _amounts_close(a: Decimal, b: Decimal, tolerance: Decimal) -> bool:
    return abs(a - b) <= tolerance


def _description_similarity(a: str, b: str) -> float:
    a = (a or "").strip().lower()
    b = (b or "").strip().lower()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def match_transactions(
    bank_txns: list[BankTransaction],
    gl_entries: list[GLEntry],
    date_window_days: int | None = None,
    amount_tolerance: Decimal | None = None,
    fuzzy_threshold: float | None = None,
    gl_account_codes: list[str] | None = None,
) -> ReconciliationResult:
    """Matches a bank feed against GL activity.

    `gl_account_codes`, when given, restricts matching to GL lines posted to
    those account code(s) -- i.e. the cash/bank GL account(s) that this bank
    feed actually corresponds to. This matters because in a balanced
    double-entry ledger both legs of a journal entry share the same
    absolute amount, so matching against the whole GL (every account) can
    produce a coincidental match against an unrelated expense or revenue
    leg instead of the real cash-side entry. Leave unset only when you
    genuinely want to check whether bank activity appears anywhere in the
    ledger, not a bank account in particular.
    """
    if gl_account_codes is not None:
        allowed = set(gl_account_codes)
        gl_entries = [g for g in gl_entries if g.account_code in allowed]

    date_window_days = (
        date_window_days if date_window_days is not None else default_settings.match_date_window_days
    )
    amount_tolerance = (
        amount_tolerance
        if amount_tolerance is not None
        else Decimal(default_settings.match_amount_tolerance)
    )
    fuzzy_threshold = (
        fuzzy_threshold if fuzzy_threshold is not None else default_settings.fuzzy_description_threshold
    )

    unmatched_bank: dict[str, BankTransaction] = {b.id: b for b in bank_txns}
    unmatched_gl: dict[str, GLEntry] = {g.id: g for g in gl_entries}
    matched_pairs: list[MatchedPair] = []
    flags: list[Flag] = []

    # Pass 1: exact amount, exact date, same currency.
    for b_id, b in list(unmatched_bank.items()):
        for g_id, g in list(unmatched_gl.items()):
            if g.currency != b.currency or b.date != g.date:
                continue
            if _amounts_close(abs(b.amount), abs(g.amount), amount_tolerance):
                matched_pairs.append(MatchedPair(b_id, g_id, confidence=1.0, method="exact"))
                del unmatched_bank[b_id]
                del unmatched_gl[g_id]
                break

    # Pass 2: exact amount within a date window (handles clearing delay).
    for b_id, b in list(unmatched_bank.items()):
        for g_id, g in list(unmatched_gl.items()):
            if g.currency != b.currency:
                continue
            if abs((b.date - g.date).days) <= date_window_days and _amounts_close(
                abs(b.amount), abs(g.amount), amount_tolerance
            ):
                matched_pairs.append(MatchedPair(b_id, g_id, confidence=0.85, method="date_window"))
                del unmatched_bank[b_id]
                del unmatched_gl[g_id]
                break

    # Pass 3: same amount, fuzzy description/reference match (handles
    # transactions posted well outside the date window but clearly the
    # same economic event).
    for b_id, b in list(unmatched_bank.items()):
        best_match: tuple[str, GLEntry, float] | None = None
        for g_id, g in list(unmatched_gl.items()):
            if g.currency != b.currency or not _amounts_close(abs(b.amount), abs(g.amount), amount_tolerance):
                continue
            score = max(
                _description_similarity(b.description, g.description),
                _description_similarity(b.reference, g.reference),
            )
            if score >= fuzzy_threshold and (best_match is None or score > best_match[2]):
                best_match = (g_id, g, score)
        if best_match:
            g_id, g, score = best_match
            matched_pairs.append(
                MatchedPair(b_id, g_id, confidence=round(score, 2), method="fuzzy_description")
            )
            del unmatched_bank[b_id]
            del unmatched_gl[g_id]

    # Pass 4: amount-mismatch detection. Same day + clearly the same
    # transaction by description, but the amount itself is off -- this is
    # a more useful, specific flag than leaving both sides in the generic
    # unmatched pile.
    for b_id, b in list(unmatched_bank.items()):
        best_match: tuple[str, GLEntry, float] | None = None
        for g_id, g in list(unmatched_gl.items()):
            if g.currency != b.currency or abs((b.date - g.date).days) > date_window_days:
                continue
            score = max(
                _description_similarity(b.description, g.description),
                _description_similarity(b.reference, g.reference),
            )
            if score >= fuzzy_threshold and (best_match is None or score > best_match[2]):
                best_match = (g_id, g, score)
        if best_match:
            g_id, g, score = best_match
            diff = abs(b.amount) - abs(g.amount)
            flags.append(
                Flag(
                    type=FlagType.AMOUNT_MISMATCH,
                    severity=FlagSeverity.CRITICAL,
                    message=(
                        f"Bank txn {b.reference or b_id} ({b.amount} {b.currency}) and GL entry "
                        f"{g.reference or g_id} ({g.amount} {g.currency}) look like the same transaction "
                        f"but differ by {diff} {b.currency}"
                    ),
                    entry_ids=[b_id, g_id],
                    details={"difference": str(diff), "description_similarity": round(score, 2)},
                )
            )
            del unmatched_bank[b_id]
            del unmatched_gl[g_id]

    # Whatever's left has no plausible counterpart at all.
    for b_id, b in unmatched_bank.items():
        flags.append(
            Flag(
                type=FlagType.UNMATCHED_BANK,
                severity=FlagSeverity.WARNING,
                message=(
                    f"Bank transaction {b.reference or b_id} for {b.amount} {b.currency} on "
                    f"{b.date} has no matching GL entry"
                ),
                entry_ids=[b_id],
                details={"amount": str(b.amount), "currency": b.currency, "date": b.date.isoformat()},
            )
        )
    for g_id, g in unmatched_gl.items():
        flags.append(
            Flag(
                type=FlagType.UNMATCHED_GL,
                severity=FlagSeverity.WARNING,
                message=(
                    f"GL entry {g.reference or g_id} in {g.account_name or g.account_code} for "
                    f"{g.amount} {g.currency} on {g.date} has no matching bank transaction"
                ),
                entry_ids=[g_id],
                details={
                    "amount": str(g.amount),
                    "currency": g.currency,
                    "date": g.date.isoformat(),
                    "account_code": g.account_code,
                },
            )
        )

    flags.extend(_find_duplicates(bank_txns, "bank"))
    flags.extend(_find_duplicates(gl_entries, "gl"))

    return ReconciliationResult(
        matched_pairs=matched_pairs,
        unmatched_bank_ids=list(unmatched_bank.keys()),
        unmatched_gl_ids=list(unmatched_gl.keys()),
        flags=flags,
    )


def _find_duplicates(entries, kind: str) -> list[Flag]:
    seen: dict[tuple, str] = {}
    flags: list[Flag] = []
    for e in entries:
        key = (e.date, e.amount, e.currency, (e.description or "").strip().lower())
        if key in seen:
            flags.append(
                Flag(
                    type=FlagType.DUPLICATE_TRANSACTION,
                    severity=FlagSeverity.CRITICAL,
                    message=(
                        f"Possible duplicate {kind} entry: {e.amount} {e.currency} on "
                        f"{e.date} ({e.description})"
                    ),
                    entry_ids=[seen[key], e.id],
                    details={"kind": kind},
                )
            )
        else:
            seen[key] = e.id
    return flags
