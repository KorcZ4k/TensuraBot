import ast
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from database.python.json_cache import clear_json_cache, load_json


ROOT = Path(__file__).resolve().parents[1]


class PerformanceSafetyTests(unittest.TestCase):
    def tearDown(self):
        clear_json_cache()

    def test_json_catalog_is_cached_but_returned_as_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalogo.json"
            path.write_text(json.dumps({"items": ["a"]}), encoding="utf-8")

            first = load_json(str(path))
            first["items"].append("mutacao")

            path.write_text(json.dumps({"items": ["arquivo-alterado"]}), encoding="utf-8")
            second = load_json(str(path))

            self.assertEqual(second, {"items": ["a"]})
            self.assertIsNot(first, second)

    def test_concurrent_offloads_do_not_serialize(self):
        async def run():
            async def operation(value):
                return await asyncio.to_thread(lambda: value)

            results = await asyncio.gather(*(operation(i) for i in range(32)))
            return results

        self.assertEqual(asyncio.run(run()), list(range(32)))

    def test_cache_clear_forces_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalogo.json"
            path.write_text(json.dumps({"version": 1}), encoding="utf-8")

            self.assertEqual(load_json(str(path))["version"], 1)
            path.write_text(json.dumps({"version": 2}), encoding="utf-8")
            clear_json_cache()

            self.assertEqual(load_json(str(path))["version"], 2)

    def test_optimized_wrappers_keep_extension_setup(self):
        for relative in (
            "comandos/RPG/luta.py",
            "comandos/RPG/magias.py",
            "comandos/RPG/status.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative)
            functions = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
            self.assertIn("setup", functions, relative)

    def test_legacy_engines_are_preserved(self):
        for relative in (
            "comandos/RPG/luta_sync.py",
            "comandos/RPG/magias_sync.py",
            "comandos/RPG/status_sync.py",
        ):
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertGreater(path.stat().st_size, 1000, relative)

    def test_startup_uses_async_registration(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("from database.python.users import cadastro_async", source)
        self.assertNotIn("await asyncio.to_thread(cadastro", source)


if __name__ == "__main__":
    unittest.main()
