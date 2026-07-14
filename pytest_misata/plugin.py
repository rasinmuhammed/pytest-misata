"""pytest fixtures for Misata: seeded, coherent test data in one line.

The two fixtures this plugin exposes:

``misata_tables``
    A factory that turns a schema (dict, SchemaConfig, or plain-English
    story) into a dict of DataFrames. Results are cached per (spec, seed)
    for the whole session, so fifty tests sharing one schema pay for one
    generation.

``misata_db``
    The same factory, but the tables land in a temporary SQLite database
    and you get the path/URL back. Point your app's connection string at
    it and run integration tests against real referentially-intact rows.

Both are deterministic: same spec and seed, same bytes, every run, every
machine. No network, no API keys, no flaky tests.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pandas as pd
import pytest


def _spec_key(spec: Any, seed: int, rows: Optional[int]) -> str:
    """Stable cache key for a schema spec + seed."""
    if isinstance(spec, str):
        body = spec
    elif isinstance(spec, dict):
        body = json.dumps(spec, sort_keys=True, default=str)
    else:
        # SchemaConfig or anything pydantic-like
        dump = getattr(spec, "model_dump_json", None)
        body = dump() if callable(dump) else repr(spec)
    raw = f"{body}|seed={seed}|rows={rows}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _build_config(spec: Any, seed: int, rows: Optional[int]):
    """Normalise any accepted spec form into a SchemaConfig."""
    import misata
    from misata.schema import SchemaConfig

    if isinstance(spec, SchemaConfig):
        if seed is not None:
            spec.seed = seed
        return spec
    if isinstance(spec, dict):
        return misata.from_dict_schema(spec, row_count=rows or 1000, seed=seed)
    if isinstance(spec, str):
        config = misata.parse(spec, rows=rows or 1000)
        config.seed = seed
        return config
    raise TypeError(
        f"misata_tables accepts a dict schema, a SchemaConfig, or a story "
        f"string; got {type(spec).__name__}"
    )


@pytest.fixture(scope="session")
def misata_tables() -> Callable[..., Dict[str, pd.DataFrame]]:
    """Factory fixture: spec -> {table_name: DataFrame}, cached per session.

    Usage::

        def test_orders_have_users(misata_tables):
            tables = misata_tables({
                "users": {"id": {"type": "integer", "primary_key": True},
                           "email": {"type": "email"}},
                "orders": {"id": {"type": "integer", "primary_key": True},
                            "user_id": {"type": "integer",
                                        "foreign_key": {"table": "users",
                                                         "column": "id"}},
                            "amount": {"type": "float", "min": 5, "max": 500}},
            }, seed=7, rows=200)
            assert set(tables["orders"]["user_id"]) <= set(tables["users"]["id"])
    """
    cache: Dict[str, Dict[str, pd.DataFrame]] = {}

    def _generate(
        spec: Any,
        *,
        seed: int = 42,
        rows: Optional[int] = None,
    ) -> Dict[str, pd.DataFrame]:
        import misata

        key = _spec_key(spec, seed, rows)
        if key not in cache:
            config = _build_config(spec, seed, rows)
            cache[key] = misata.generate_from_schema(config)
        # Copies, so one test mutating a frame cannot poison the next.
        return {name: df.copy() for name, df in cache[key].items()}

    return _generate


@pytest.fixture()
def misata_db(tmp_path: Path) -> Callable[..., str]:
    """Factory fixture: spec -> sqlite URL seeded with generated tables.

    Usage::

        def test_app_reads_seeded_db(misata_db):
            db_url = misata_db(SCHEMA, seed=7, rows=500)
            engine = sqlalchemy.create_engine(db_url)
            with engine.connect() as conn:
                n = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
            assert n == 500

    Function-scoped on purpose: every test gets its own database file under
    pytest's tmp_path, so a test that writes rows cannot affect another.
    """

    def _seed(
        spec: Any,
        *,
        seed: int = 42,
        rows: Optional[int] = None,
        filename: str = "misata.sqlite3",
    ) -> str:
        from misata.db import seed_database

        config = _build_config(spec, seed, rows)
        db_path = tmp_path / filename
        db_url = f"sqlite:///{db_path}"
        seed_database(config, db_url, create=True, use_llm=False)
        return db_url

    return _seed
