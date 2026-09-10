import ast
import asyncio
import importlib
import unittest
from pathlib import Path

from discord.ext import commands

ROOT = Path(__file__).resolve().parents[1]


def _extensions_from_main():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "extensoes" for t in node.targets):
            return [item.value for item in node.value.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)]
    raise AssertionError("A lista extensoes nao foi encontrada em main.py")


async def _load_all_extensions():
    bot = commands.Bot(command_prefix="!", intents=__import__("discord").Intents.none())
    loaded = []
    failures = []
    for extension in _extensions_from_main():
        try:
            await bot.load_extension(extension)
            loaded.append(extension)
        except Exception as exc:
            failures.append(f"{extension}: {type(exc).__name__}: {exc}")
    return bot, loaded, failures


class CommandRegistryTests(unittest.TestCase):
    def test_every_loaded_extension_registers_cleanly(self):
        bot, loaded, failures = asyncio.run(_load_all_extensions())
        self.assertFalse(failures, "Falhas ao carregar extensoes:\n" + "\n".join(failures))
        self.assertEqual(len(loaded), len(_extensions_from_main()))

    def test_registered_command_names_and_aliases_are_unique(self):
        bot, loaded, failures = asyncio.run(_load_all_extensions())
        self.assertFalse(failures, "Falhas ao carregar extensoes:\n" + "\n".join(failures))
        seen = {}

        def walk(command, prefix=""):
            full_name = f"{prefix} {command.name}".strip()
            for name in [command.name, *getattr(command, "aliases", [])]:
                key = f"{prefix} {name}".strip()
                owner = seen.get(key)
                if owner and owner != full_name:
                    raise AssertionError(f"Conflito de comando/alias '{key}': {owner} vs {full_name}")
                seen[key] = full_name
            for child in getattr(command, "commands", []):
                walk(child, full_name)

        for command in bot.commands:
            walk(command)

        self.assertGreater(len(seen), 0)


if __name__ == "__main__":
    unittest.main()
