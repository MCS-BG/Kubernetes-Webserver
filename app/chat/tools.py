"""Tools the chat agent can call. Each one wraps existing engine/store code
-- the chat layer adds no new business logic of its own, it just exposes
what already works (reconciliation, trial balance, RAG, feedback) through
natural language.
"""
from __future__ import annotations

import requests
from anthropic import beta_tool

from app.entities import registry as entity_registry
from app.fx import get_fx_provider
from app.rag import rag_store
from app.reconciliation import check_fx_rates, match_transactions, tie_out
from app.skills import skill_store
from app.store import store


@beta_tool
def list_entities() -> str:
    """List the legal entities available to report against, with their base currency.

    Call this first whenever it's ambiguous which legal entity the user means.
    """
    entities = entity_registry.list()
    if not entities:
        return "No entities are configured yet."
    return "\n".join(
        f"- {e.name} (base currency {e.base_currency}): {e.description}".rstrip(": ")
        for e in entities
    )


@beta_tool
def run_reconciliation(entity_name: str, cash_account_codes: str = "") -> str:
    """Run bank-to-GL reconciliation and trial-balance tie-out for a legal entity.

    Uses the entity's most recently uploaded source data (bank feed, GL, trial
    balance). Args:
        entity_name: The legal entity to report against, e.g. "Acme Ops LLC". Call
            list_entities first if you aren't sure of the exact name.
        cash_account_codes: Comma-separated GL account code(s) that represent this
            entity's bank/cash account(s), e.g. "1000". Strongly recommended --
            without it, matching runs against every GL account and can produce
            false matches. Leave blank only if genuinely unknown.
    """
    entity = entity_registry.find_by_name(entity_name)
    if not entity:
        return f"No entity named '{entity_name}' is configured. Call list_entities to see available entities."

    sources = store.sources_for_entity(entity.id)
    if not sources:
        return f"No uploaded source data found for {entity.name} yet."
    source = sources[-1]

    account_codes = [c.strip() for c in cash_account_codes.split(",") if c.strip()] or None

    result = match_transactions(
        source.bank_transactions, source.gl_entries, gl_account_codes=account_codes
    )
    tie_out_lines, tb_flags = tie_out(source.gl_entries, source.trial_balance)
    result.flags.extend(tb_flags)

    try:
        fx_provider = get_fx_provider()
        result.flags.extend(
            check_fx_rates(source.gl_entries, fx_provider, base_currency=entity.base_currency)
        )
    except (requests.RequestException, KeyError, ValueError):
        # FX reference source is an external network call -- don't block the
        # close on it being unreachable, just skip the currency check.
        pass

    result.flags, suppressed = skill_store.apply_suppression(result.flags, entity.id)

    store.results[result.id] = result
    store.tie_outs[result.id] = tie_out_lines
    store.result_entity[result.id] = entity.id

    summary = result.summary()
    return (
        f"Reconciliation for {entity.name} complete (reconciliation_id: {result.id}).\n"
        f"Matched: {summary['matched']}. Unmatched bank: {summary['unmatched_bank']}. "
        f"Unmatched GL: {summary['unmatched_gl']}. Total flags: {summary['flags_total']} "
        f"(by severity: {summary['flags_by_severity']}). "
        f"Suppressed by previously-learned patterns: {suppressed}."
    )


@beta_tool
def get_exceptions(reconciliation_id: str) -> str:
    """List the reconciliation exceptions (flags) for a completed run, with reasons and their index.

    Args:
        reconciliation_id: The reconciliation_id returned by run_reconciliation.
    """
    result = store.results.get(reconciliation_id)
    if not result:
        return f"No reconciliation found with id {reconciliation_id}."
    if not result.flags:
        return "No exceptions -- everything reconciled cleanly."
    return "\n".join(
        f"[{i}] ({flag.severity.value}/{flag.type.value}) {flag.message}"
        for i, flag in enumerate(result.flags)
    )


@beta_tool
def get_trial_balance_report(reconciliation_id: str) -> str:
    """Get the trial-balance tie-out report (per account, computed vs. reported) for a completed run.

    Args:
        reconciliation_id: The reconciliation_id returned by run_reconciliation.
    """
    lines_data = store.tie_outs.get(reconciliation_id)
    if lines_data is None:
        return f"No reconciliation found with id {reconciliation_id}."
    return "\n".join(
        f"{line.account_code} {line.account_name}: computed "
        f"{line.computed_debit}/{line.computed_credit}, reported "
        f"{line.reported_debit}/{line.reported_credit} "
        f"[{'OK' if line.tied_out else 'MISMATCH'}]"
        for line in lines_data
    )


@beta_tool
def search_knowledge_base(entity_name: str, query: str) -> str:
    """Search this entity's reference documents (accounting policies, chart-of-accounts
    notes, prior close notes) for context relevant to the query.

    Args:
        entity_name: The legal entity whose documents to search.
        query: What to look for, e.g. "revenue recognition policy".
    """
    entity = entity_registry.find_by_name(entity_name)
    if not entity:
        return f"No entity named '{entity_name}' is configured."
    results = rag_store.search(entity.id, query)
    if not results:
        return "No relevant documents found."
    return "\n\n".join(f"### {doc.title}\n{doc.text}" for doc, _score in results)


@beta_tool
def record_exception_feedback(
    reconciliation_id: str, flag_index: int, match_text: str, note: str
) -> str:
    """Record that a specific exception is a known, reviewed false positive, so future
    reconciliations for this entity stop flagging the same recognized pattern. This is
    how the platform's exception-handling improves over time -- only ever from an
    explicit human review, never invented automatically.

    Args:
        reconciliation_id: The reconciliation run the flag came from.
        flag_index: The index of the flag as shown by get_exceptions.
        match_text: A distinctive substring (e.g. a vendor/customer name) identifying
            this recurring pattern in future flags.
        note: Why this is not a real issue -- recorded in the entity's skill file.
    """
    result = store.results.get(reconciliation_id)
    if not result:
        return f"No reconciliation found with id {reconciliation_id}."
    if flag_index < 0 or flag_index >= len(result.flags):
        return f"flag_index {flag_index} is out of range (0-{len(result.flags) - 1})."
    entity_id = store.result_entity.get(reconciliation_id)
    if not entity_id:
        return "This reconciliation run has no associated entity -- cannot record entity-scoped feedback."

    flag = result.flags[flag_index]
    pattern = skill_store.record_feedback(
        entity_id=entity_id, flag_type=flag.type, match_text=match_text, note=note
    )
    return (
        f"Recorded. Future '{flag.type.value}' flags matching '{match_text}' will be "
        f"suppressed for this entity (pattern {pattern.id})."
    )


ALL_TOOLS = [
    list_entities,
    run_reconciliation,
    get_exceptions,
    get_trial_balance_report,
    search_knowledge_base,
    record_exception_feedback,
]
