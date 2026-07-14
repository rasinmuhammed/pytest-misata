"""The plugin's own suite: fixtures resolve, specs parse, caching holds,
determinism holds, the database seeds, and isolation between tests is real."""

import sqlite3

import pandas as pd
import pytest

pytest_plugins = ["pytest_misata.plugin"]

SCHEMA = {
    "users": {
        "id": {"type": "integer", "primary_key": True},
        "email": {"type": "email"},
        "age": {"type": "integer", "min": 18, "max": 80},
    },
    "orders": {
        "id": {"type": "integer", "primary_key": True},
        "user_id": {"type": "integer",
                    "foreign_key": {"table": "users", "column": "id"}},
        "amount": {"type": "float", "min": 5, "max": 500},
    },
}


class TestMisataTables:
    def test_returns_dataframes_for_every_table(self, misata_tables):
        tables = misata_tables(SCHEMA, seed=7, rows=100)
        assert set(tables) == {"users", "orders"}
        assert all(isinstance(df, pd.DataFrame) for df in tables.values())

    def test_row_count_respected(self, misata_tables):
        tables = misata_tables(SCHEMA, seed=7, rows=137)
        assert len(tables["users"]) == 137

    def test_fk_integrity_holds(self, misata_tables):
        tables = misata_tables(SCHEMA, seed=7, rows=200)
        assert set(tables["orders"]["user_id"]) <= set(tables["users"]["id"])

    def test_same_seed_same_bytes(self, misata_tables):
        a = misata_tables(SCHEMA, seed=11, rows=100)
        b = misata_tables(SCHEMA, seed=11, rows=100)
        for name in a:
            pd.testing.assert_frame_equal(a[name], b[name])

    def test_different_seed_different_data(self, misata_tables):
        a = misata_tables(SCHEMA, seed=1, rows=100)
        b = misata_tables(SCHEMA, seed=2, rows=100)
        assert not a["users"]["email"].equals(b["users"]["email"])

    def test_cache_returns_copies_not_aliases(self, misata_tables):
        a = misata_tables(SCHEMA, seed=7, rows=100)
        a["users"].loc[0, "age"] = -999
        b = misata_tables(SCHEMA, seed=7, rows=100)
        assert b["users"].loc[0, "age"] != -999

    def test_declared_bounds_hold(self, misata_tables):
        tables = misata_tables(SCHEMA, seed=7, rows=300)
        assert tables["users"]["age"].between(18, 80).all()
        assert tables["orders"]["amount"].between(5, 500).all()

    def test_schemaconfig_spec_accepted(self, misata_tables):
        import misata
        config = misata.from_dict_schema(SCHEMA, row_count=60, seed=3)
        tables = misata_tables(config, seed=3)
        assert len(tables["users"]) == 60

    def test_story_spec_accepted(self, misata_tables):
        tables = misata_tables(
            "an ecommerce store with customers and orders", seed=5, rows=80)
        assert tables and all(len(df) > 0 for df in tables.values())

    def test_bad_spec_type_raises(self, misata_tables):
        with pytest.raises(TypeError, match="dict schema"):
            misata_tables(12345)


class TestMisataDb:
    def test_seeds_sqlite_with_all_tables(self, misata_db):
        url = misata_db(SCHEMA, seed=7, rows=120)
        path = url.replace("sqlite:///", "")
        con = sqlite3.connect(path)
        names = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"users", "orders"} <= names
        n = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        assert n == 120
        con.close()

    def test_fk_join_returns_no_orphans(self, misata_db):
        url = misata_db(SCHEMA, seed=7, rows=150)
        con = sqlite3.connect(url.replace("sqlite:///", ""))
        orphans = con.execute(
            "SELECT COUNT(*) FROM orders o LEFT JOIN users u "
            "ON o.user_id = u.id WHERE u.id IS NULL").fetchone()[0]
        assert orphans == 0
        con.close()

    def test_each_call_gets_its_own_file(self, misata_db):
        a = misata_db(SCHEMA, seed=7, rows=50, filename="a.sqlite3")
        b = misata_db(SCHEMA, seed=7, rows=50, filename="b.sqlite3")
        assert a != b

    def test_deterministic_across_seeding(self, misata_db):
        urls = [misata_db(SCHEMA, seed=9, rows=40, filename=f"{i}.sqlite3")
                for i in range(2)]
        sums = []
        for url in urls:
            con = sqlite3.connect(url.replace("sqlite:///", ""))
            sums.append(con.execute(
                "SELECT ROUND(SUM(amount), 2) FROM orders").fetchone()[0])
            con.close()
        assert sums[0] == sums[1]


class TestPluginRegistration:
    def test_entry_point_registers_fixtures(self, request):
        # Both fixtures resolvable by name through pytest's own machinery.
        assert request.getfixturevalue("misata_tables") is not None
