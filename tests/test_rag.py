from app.rag.store import RAGStore


def test_search_empty_entity_returns_nothing():
    store = RAGStore()
    assert store.search("entity-1", "revenue recognition") == []


def test_search_ranks_relevant_document_first():
    store = RAGStore()
    store.add_document(
        "entity-1",
        title="Revenue Recognition Policy",
        text="Revenue is recognized when control of goods transfers to the customer, per ASC 606.",
    )
    store.add_document(
        "entity-1",
        title="Expense Reimbursement Policy",
        text="Employees submit expense reports monthly for reimbursement of travel costs.",
    )

    results = store.search("entity-1", "revenue recognition control transfer")

    assert len(results) >= 1
    top_doc, top_score = results[0]
    assert top_doc.title == "Revenue Recognition Policy"
    assert top_score > 0


def test_search_scoped_to_entity():
    store = RAGStore()
    store.add_document("entity-1", title="Entity 1 policy", text="Intercompany transactions require approval")
    store.add_document("entity-2", title="Entity 2 policy", text="Intercompany transactions require approval")

    results = store.search("entity-1", "intercompany approval")

    assert len(results) == 1
    assert results[0][0].entity_id == "entity-1"


def test_search_no_matching_terms_returns_empty():
    store = RAGStore()
    store.add_document("entity-1", title="Doc", text="Revenue recognition policy")

    assert store.search("entity-1", "zzz nonexistent qqq") == []
