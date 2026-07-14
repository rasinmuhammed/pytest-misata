# pytest-misata

pytest fixtures for [Misata](https://github.com/rasinmuhammed/misata): deterministic, referentially-intact, multi-table test data in one line. No factories to maintain, no fixtures.json to hand-edit, no flaky random rows.

```bash
pip install pytest-misata
```

## Five lines to seeded tests

```python
def test_every_order_has_a_user(misata_tables):
    tables = misata_tables({
        "users":  {"id": {"type": "integer", "primary_key": True},
                   "email": {"type": "email"}},
        "orders": {"id": {"type": "integer", "primary_key": True},
                   "user_id": {"type": "integer",
                               "foreign_key": {"table": "users", "column": "id"}},
                   "amount": {"type": "float", "min": 5, "max": 500}},
    }, seed=7, rows=200)
    assert set(tables["orders"]["user_id"]) <= set(tables["users"]["id"])
```

The FK containment assertion above is not a hope: Misata guarantees it at generation time, for every relationship, every run.

## The fixtures

### `misata_tables(spec, seed=42, rows=None)`

Returns `{table_name: DataFrame}`. Accepts three spec forms:

- a **dict schema** (shown above),
- a **`SchemaConfig`** you built or loaded from YAML,
- a **plain-English story**: `misata_tables("a SaaS with users and subscriptions", rows=500)`.

Session-scoped cache: fifty tests sharing one schema pay for one generation. Each call returns copies, so a test that mutates its frames cannot poison the next test.

### `misata_db(spec, seed=42, rows=None)`

Same specs, but the tables land in a temporary SQLite database and you get the URL back:

```python
from sqlalchemy import create_engine, text

def test_app_against_real_rows(misata_db):
    db_url = misata_db(SCHEMA, seed=7, rows=500)
    with create_engine(db_url).connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
    assert n == 500
```

Function-scoped: every test gets its own database file under pytest's `tmp_path`, so writes never leak between tests.

## Why not factory_boy or hand-rolled fixtures?

Factories build one row at a time and know nothing about the rows around them, so the classic seed-data defects creep in: orders that ship before they are placed, totals that fail their own arithmetic, foreign keys pointing nowhere. Misata generates the whole relational story at once with those invariants enforced, then audits its own output before returning it. Run `misata audit` on your current seed directory if you want to see the difference measured.

## Determinism contract

Same spec plus same seed produces the same bytes on every machine, every run, with no network and no API keys. Change the seed to rotate the whole dataset without touching a single assertion about declared properties.

## License

MIT. The engine is [misata](https://pypi.org/project/misata/), also MIT.
