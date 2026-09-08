from pathlib import Path

import main


async def test_init_db_accepts_a_bare_filename(tmp_path, monkeypatch):
    import database.db as db_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(db_module, "DATABASE_PATH", "swgoh.db")

    await db_module.init_db()

    assert (tmp_path / "swgoh.db").exists()


def test_log_handler_creates_a_missing_directory(tmp_path):
    cible = tmp_path / "logs" / "bot.log"

    handler = main.build_file_handler(str(cible))
    try:
        assert cible.exists()
    finally:
        handler.close()


def test_log_handler_falls_back_instead_of_blocking_startup(tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    handler = main.build_file_handler(str(blocker / "sous-dossier" / "bot.log"))
    try:
        assert Path(handler.baseFilename) == tmp_path / "bot.log"
    finally:
        handler.close()
