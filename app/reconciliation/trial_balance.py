"""Trial balance tie-out: does the GL activity we computed match what the
ERP reports as each account's ending balance, and does the ledger balance
(total debits == total credits) at all?
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.config import settings as default_settings
from app.models import Flag, FlagSeverity, FlagType, GLEntry, TrialBalanceLine, TrialBalanceTieOut


def compute_balances_from_gl(gl_entries: list[GLEntry]) -> dict[str, tuple[Decimal, Decimal, str]]:
    """Returns {account_code: (computed_debit, computed_credit, account_name)}."""
    totals: dict[str, list] = defaultdict(lambda: [Decimal("0"), Decimal("0"), ""])
    for e in gl_entries:
        bucket = totals[e.account_code]
        if e.amount >= 0:
            bucket[0] += e.amount
        else:
            bucket[1] += -e.amount
        if not bucket[2] and e.account_name:
            bucket[2] = e.account_name
    return {code: (v[0], v[1], v[2]) for code, v in totals.items()}


def tie_out(
    gl_entries: list[GLEntry],
    trial_balance_lines: list[TrialBalanceLine],
    tolerance: Decimal | None = None,
) -> tuple[list[TrialBalanceTieOut], list[Flag]]:
    tolerance = tolerance if tolerance is not None else Decimal(default_settings.tie_out_tolerance)
    computed = compute_balances_from_gl(gl_entries)
    reported_by_code = {line.account_code: line for line in trial_balance_lines}

    results: list[TrialBalanceTieOut] = []
    flags: list[Flag] = []

    for code in sorted(set(computed) | set(reported_by_code)):
        computed_debit, computed_credit, computed_name = computed.get(
            code, (Decimal("0"), Decimal("0"), "")
        )
        reported_line = reported_by_code.get(code)
        reported_debit = reported_line.reported_debit if reported_line else Decimal("0")
        reported_credit = reported_line.reported_credit if reported_line else Decimal("0")
        account_name = (reported_line.account_name if reported_line else "") or computed_name

        debit_variance = computed_debit - reported_debit
        credit_variance = computed_credit - reported_credit
        tied_out = abs(debit_variance) <= tolerance and abs(credit_variance) <= tolerance

        results.append(
            TrialBalanceTieOut(
                account_code=code,
                account_name=account_name,
                computed_debit=computed_debit,
                computed_credit=computed_credit,
                reported_debit=reported_debit,
                reported_credit=reported_credit,
                debit_variance=debit_variance,
                credit_variance=credit_variance,
                tied_out=tied_out,
            )
        )

        if not tied_out:
            flags.append(
                Flag(
                    type=FlagType.ACCOUNT_TIE_OUT_MISMATCH,
                    severity=FlagSeverity.CRITICAL,
                    message=(
                        f"Account {code} ({account_name}) doesn't tie out: computed "
                        f"debit/credit {computed_debit}/{computed_credit} vs reported "
                        f"{reported_debit}/{reported_credit}"
                    ),
                    entry_ids=[],
                    details={
                        "account_code": code,
                        "debit_variance": str(debit_variance),
                        "credit_variance": str(credit_variance),
                    },
                )
            )

    total_debit = sum((r.computed_debit for r in results), Decimal("0"))
    total_credit = sum((r.computed_credit for r in results), Decimal("0"))
    if abs(total_debit - total_credit) > tolerance:
        flags.append(
            Flag(
                type=FlagType.TRIAL_BALANCE_OUT_OF_BALANCE,
                severity=FlagSeverity.CRITICAL,
                message=(
                    f"Ledger is out of balance: total debits {total_debit} != total "
                    f"credits {total_credit} (diff {total_debit - total_credit})"
                ),
                entry_ids=[],
                details={"total_debit": str(total_debit), "total_credit": str(total_credit)},
            )
        )

    return results, flags
