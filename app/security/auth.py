"""Minimal role-based access control -- enough to demonstrate segregation
of duties (the person who approves/reviews a close item can't be the same
person who prepared it), not a full identity system. Real deployments
should sit this behind proper SSO/OIDC; this is the smallest thing that
makes "who did this" and "who's allowed to approve it" real questions the
API can answer.

Configuration: set AUTH_TOKENS as a comma-separated list of
"token:actor_name:role" triples, e.g.:
    AUTH_TOKENS="tok_alice:alice:preparer,tok_bob:bob:reviewer,tok_admin:admin:admin"

If AUTH_TOKENS is unset (the default, e.g. local dev and this repo's test
suite), authentication is a no-op that returns a fixed admin identity --
segregation of duties only has teeth once real tokens are configured.
"""
from __future__ import annotations

import os

from fastapi import Depends, Header, HTTPException

ROLE_RANK = {"preparer": 1, "reviewer": 2, "admin": 3}


def _load_tokens() -> dict[str, tuple[str, str]]:
    raw = os.environ.get("AUTH_TOKENS", "")
    tokens: dict[str, tuple[str, str]] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) != 3:
            continue
        token, actor, role = parts
        tokens[token] = (actor, role)
    return tokens


def authenticate(authorization: str | None = Header(None)) -> tuple[str, str]:
    """Returns (actor, role).

    Tokens are re-read from AUTH_TOKENS on every call (not cached at import
    time) -- deliberately, so tests and ops can change the token set without
    restarting the process.
    """
    tokens = _load_tokens()
    if not tokens:
        return ("unauthenticated", "admin")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if token not in tokens:
        raise HTTPException(401, "Invalid token")
    return tokens[token]


def require_role(minimum_role: str):
    def dependency(identity: tuple[str, str] = Depends(authenticate)) -> tuple[str, str]:
        _actor, role = identity
        if ROLE_RANK.get(role, 0) < ROLE_RANK.get(minimum_role, 999):
            raise HTTPException(403, f"Requires {minimum_role} role or higher")
        return identity

    return dependency
