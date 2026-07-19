from app.coa import AccountType, ChartOfAccounts


def test_set_and_get_account():
    coa = ChartOfAccounts()
    coa.set_account("entity-1", "4000", "Revenue", AccountType.REVENUE)

    entry = coa.get("entity-1", "4000")
    assert entry is not None
    assert entry.account_name == "Revenue"
    assert entry.account_type == AccountType.REVENUE


def test_get_unknown_account_returns_none():
    coa = ChartOfAccounts()
    assert coa.get("entity-1", "9999") is None


def test_accounts_scoped_per_entity():
    coa = ChartOfAccounts()
    coa.set_account("entity-1", "4000", "Revenue", AccountType.REVENUE)
    coa.set_account("entity-2", "4000", "Consulting Revenue", AccountType.REVENUE)

    assert coa.get("entity-1", "4000").account_name == "Revenue"
    assert coa.get("entity-2", "4000").account_name == "Consulting Revenue"
    assert len(coa.accounts_for("entity-1")) == 1


def test_set_account_overwrites_existing():
    coa = ChartOfAccounts()
    coa.set_account("entity-1", "6100", "Facilities", AccountType.OPERATING_EXPENSE)
    coa.set_account("entity-1", "6100", "Facilities Expense", AccountType.OPERATING_EXPENSE)

    assert len(coa.accounts_for("entity-1")) == 1
    assert coa.get("entity-1", "6100").account_name == "Facilities Expense"
