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

    def test_combat_has_one_canonical_resolver(self):
        source = self._source("comandos/RPG/luta.py")
        self.assertIn("class Luta(commands.Cog)", source)
        self.assertIn("async def _resolver_ataque", source)
        self.assertIn("ataque.get(\"defensor_id\")", source)
        self.assertNotIn("monkeypatch", source.lower())

    def test_legacy_patch_modules_do_not_override_canonical_resolver(self):
        for relative in (
            "comandos/RPG/correcoes_luta.py",
            "comandos/RPG/correcoes_concorrencia.py",
            "comandos/RPG/correcoes_party.py",
            "comandos/RPG/habilidades_combate.py",
        ):
            source = self._source(relative)
            self.assertNotIn("_resolver_ataque =", source)
            self.assertNotIn("_proximo_turno =", source)

    def test_global_command_error_handler_does_not_reraise(self):
        source = self._source("main.py")
        self.assertNotIn("raise error", source)
        self.assertIn("[COMANDO][ERRO]", source)

    def test_hardening_modules_remain_valid_python(self):
        for relative in (
            "database/python/luta.py",
            "database/python/luta_async.py",
            "comandos/RPG/luta.py",
            "comandos/RPG/luta_sync.py",
            "comandos/RPG/party.py",
            "comandos/RPG/correcoes_luta.py",
            "comandos/RPG/correcoes_concorrencia.py",
            "comandos/RPG/correcoes_party.py",
            "comandos/RPG/habilidades_combate.py",
            "main.py",
        ):
            ast.parse(self._source(relative), filename=relative)


class TurnOrderTests(unittest.TestCase):
    @staticmethod
    def next_living(participants, current):
        for step in range(1, len(participants) + 1):
            index = (current + step) % len(participants)
            if participants[index]["vida"] > 0:
                return index
        return None

    def test_two_players_alternate_by_speed(self):
        ps = [
            {"id": "fast", "velocidade": 100, "vida": 100},
            {"id": "slow", "velocidade": 50, "vida": 100},
        ]
        ps.sort(key=lambda p: p["velocidade"], reverse=True)
        self.assertEqual([p["id"] for p in ps], ["fast", "slow"])
        self.assertEqual(ps[self.next_living(ps, 0)]["id"], "slow")
        self.assertEqual(ps[self.next_living(ps, 1)]["id"], "fast")

    def test_party_cycles_speed_order_and_skips_dead(self):
        ps = [
            {"id": "A", "velocidade": 100, "vida": 100},
            {"id": "B", "velocidade": 80, "vida": 0},
            {"id": "C", "velocidade": 60, "vida": 100},
            {"id": "D", "velocidade": 40, "vida": 100},
        ]
        ps.sort(key=lambda p: p["velocidade"], reverse=True)
        ordem = []
        atual = -1
        for _ in range(3):
            atual = self.next_living(ps, atual)
            ordem.append(ps[atual]["id"])
        self.assertEqual(ordem, ["A", "C", "D"])

    def test_pending_defender_is_the_one_who_must_defend(self):
        source = self._source("comandos/RPG/luta.py")
        self.assertIn('"defensor_id": defensor.get("id")', source)
        self.assertIn('str(defensor.get("id")) != str(ctx.author.id)', source)


if __name__ == "__main__":
    unittest.main()
