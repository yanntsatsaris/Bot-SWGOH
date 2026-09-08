import ast

from conftest import ROOT, project_python_files


def duplicate_top_level_definitions(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    return sorted({name for name in names if names.count(name) > 1})


def test_no_shadowed_top_level_definitions():
    offenders = {
        str(path.relative_to(ROOT)): duplicates
        for path in project_python_files()
        if (duplicates := duplicate_top_level_definitions(path))
    }
    assert offenders == {}, (
        "A second definition silently replaces the first at import time, so the "
        f"earlier one is unreachable: {offenders}"
    )


def test_every_module_parses():
    for path in project_python_files():
        ast.parse(path.read_text(encoding="utf-8"))


def test_archive_is_not_reachable_from_live_code():
    importers = [
        str(path.relative_to(ROOT))
        for path in project_python_files()
        if "_archive" in path.read_text(encoding="utf-8")
    ]
    assert importers == [], f"_archive/ is dead code and must stay unreferenced: {importers}"
