import re

from conftest import ROOT

SQL_STATEMENT = re.compile(
    r"\b(SELECT\s+.+?\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b",
    re.IGNORECASE | re.DOTALL,
)

# Cogs are controllers and must not talk SQL. These counts are the debt that
# exists today; the ratchet lets them fall and blocks any new statement.
SQL_IN_COGS_BUDGET = {
    "admin.py": 9,
    "gac.py": 9,
    "gac_counter.py": 1,
    "gac_global_meta.py": 1,
    "gac_scout.py": 8,
    "meta_scanner.py": 2,
    "review_portraits.py": 9,
}


def sql_statements_per_cog():
    counts = {}
    for path in sorted((ROOT / "cogs").glob("*.py")):
        found = len(SQL_STATEMENT.findall(path.read_text(encoding="utf-8")))
        if found:
            counts[path.name] = found
    return counts


def test_no_cog_gains_raw_sql():
    regressions = {
        name: (SQL_IN_COGS_BUDGET.get(name, 0), found)
        for name, found in sql_statements_per_cog().items()
        if found > SQL_IN_COGS_BUDGET.get(name, 0)
    }
    assert regressions == {}, (
        "Data access belongs in services/, not cogs/. (budget, found) per file: "
        f"{regressions}"
    )


def test_budget_is_not_stale():
    counts = sql_statements_per_cog()
    overstated = {
        name: (budget, counts.get(name, 0))
        for name, budget in SQL_IN_COGS_BUDGET.items()
        if counts.get(name, 0) < budget
    }
    assert overstated == {}, (
        "Debt was paid down; lower the budget so the ratchet keeps holding. "
        f"(budget, found): {overstated}"
    )
