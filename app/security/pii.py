"""PII masking utilities. Used before anything free-text (descriptions,
references, names) is written to the audit log, so the immutable audit
trail itself never becomes a second place PII leaks from.
"""
from __future__ import annotations

import re

_DIGITS_RE = re.compile(r"\d{4,}")


def mask_account_number(text: str) -> str:
    """Masks digit runs of 4+ digits, keeping only the last 4 visible.

    "Account 123456789" -> "Account *****6789"
    """

    def _mask(match: re.Match) -> str:
        digits = match.group(0)
        return "*" * (len(digits) - 4) + digits[-4:]

    return _DIGITS_RE.sub(_mask, text)


def mask_name(name: str) -> str:
    """Masks a person/company name to its first letter per word plus asterisks.

    "Jane Doe" -> "J*** D**"
    """
    if not name:
        return name
    return " ".join((w[0] + "*" * (len(w) - 1)) if w else w for w in name.split(" "))
