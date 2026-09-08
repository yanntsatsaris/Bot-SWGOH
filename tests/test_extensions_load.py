import importlib

import main


def test_every_declared_extension_is_importable():
    for extension in main.INITIAL_EXTENSIONS:
        importlib.import_module(extension)


def test_every_extension_exposes_a_setup_hook():
    missing = [
        extension
        for extension in main.INITIAL_EXTENSIONS
        if not hasattr(importlib.import_module(extension), "setup")
    ]
    assert missing == [], f"discord.py cannot load an extension without setup(): {missing}"
