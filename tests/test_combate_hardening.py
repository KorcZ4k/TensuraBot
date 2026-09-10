import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


class CombatHardeningTests(unittest.TestCase):
    def test_async_combat_facade_uses_real_mongo_collection(self):
        text = source("database/python/luta_async.py")
        self.assertNotIn("luta_db.jogadores", text)
        self.assertIn('luta_db.db["Jogadores"].update_one', text)

    def test_party_invites_have_expiration_and_are_not_consumed_during_combat(self):
        text = source("comandos/RPG/party.py")
        self.assertIn("CONVITE_EXPIRA_EM", text)
        self.assertIn("_limpar_convites_expirados", text)
        self.assertIn("Tente novamente quando o combate terminar", text)

    def test_combat_has_one_canonical_resolver(self):
        text = source("comandos/RPG/luta.py")
        self.assertIn("class Luta(commands.Cog)", text)
        self.assertIn("async def _resolver_ataque", text)
        self.assertIn("ataque.get(\"defensor_id\")", text)
        self.assertNotIn("monkeypatch", text.lower())

    def test_legacy_patch_modules_do_not_override_canonical_resolver(self):
        for relative in (
            "comandos/RPG/correcoes_luta.py",
            "comandos/RPG/correcoes_concorrencia.py",
            "comandos/RPG/correcoes_party.py",
            "comandos/RPG/habilidades_combate.py",
        ):
            text = source(relative)
            self.assertNotIn("_resolver_ataque =", text)
            self.assertNotIn("_proximo_turno =", text)

    def test_global_command_error_handler_does_not_reraise(self):
        text = source("main.py")
        self.assertNotIn("raise error", text)
        self.assertIn("[COMANDO][ERRO]", text)

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
            ast.parse(source(relative), filename=relative)


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
        text = source("comandos/RPG/luta.py")
        self.assertIn('"defensor_id": defensor.get("id")', text)
        self.assertIn('str(defensor.get("id")) != str(ctx.author.id)', text)


if __name__ == "__main__":
    unittest.main()
