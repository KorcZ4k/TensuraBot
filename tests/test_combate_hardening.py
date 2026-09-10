import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CombatHardeningTests(unittest.TestCase):
    def _source(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_async_combat_facade_uses_real_mongo_collection(self):
        source = self._source("database/python/luta_async.py")
        self.assertNotIn("luta_db.jogadores", source)
        self.assertIn('luta_db.db["Jogadores"].update_one', source)

    def test_party_invites_have_expiration_and_are_not_consumed_during_combat(self):
        source = self._source("comandos/RPG/party.py")
        self.assertIn("CONVITE_EXPIRA_EM", source)
        self.assertIn("_limpar_convites_expirados", source)
        self.assertIn("Tente novamente quando o combate terminar", source)

    def test_defense_calculations_accept_upper_and_lowercase_attributes(self):
        source = self._source("comandos/RPG/correcoes_luta.py")
        self.assertIn('participante.get(maiusculo, participante.get(minusculo, padrao))', source)
        self.assertIn('"Defesa", "defesa"', source)
        self.assertIn('"Magia", "magia"', source)

    def test_global_command_error_handler_does_not_reraise(self):
        source = self._source("main.py")
        self.assertNotIn("raise error", source)
        self.assertIn("[COMANDO][ERRO]", source)

    def test_empty_legacy_rpg_module_is_removed(self):
        self.assertFalse((ROOT / "database/python/rpg.py").exists())

    def test_hardening_modules_remain_valid_python(self):
        for relative in (
            "database/python/luta_async.py",
            "comandos/RPG/party.py",
            "comandos/RPG/correcoes_luta.py",
            "comandos/RPG/correcoes_concorrencia.py",
            "comandos/RPG/correcoes_party.py",
            "main.py",
        ):
            ast.parse(self._source(relative), filename=relative)


if __name__ == "__main__":
    unittest.main()
