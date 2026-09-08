import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("POSTGRES_URL", None)

import pytest

PROJECT_PACKAGES = ("cogs", "services", "database", "utils", "scripts")


def project_python_files():
    for package in PROJECT_PACKAGES:
        yield from sorted((ROOT / package).rglob("*.py"))
    yield ROOT / "main.py"
    yield ROOT / "config.py"


@pytest.fixture
async def db(tmp_path, monkeypatch):
    import database.db as db_module

    monkeypatch.setattr(db_module, "DATABASE_PATH", str(tmp_path / "test.db"))
    await db_module.init_db()
    return db_module
