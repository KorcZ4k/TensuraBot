import asyncio
import unittest
from types import SimpleNamespace


class CombatRegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_pending_target_is_not_retargeted_when_dead(self):
        from comandos.RPG.Luta.sistemas_luta import Luta

        luta = Luta.__new__(Luta)
        jogador = {"id": "jogador", "tipo": "jogador", "vida": 100, "equipe": "jogadores"}
        alvo = {"id": "alvo", "tipo": "monstro", "vida": 0, "equipe": "inimigos"}
        outro = {"id": "outro", "tipo": "monstro", "vida": 100, "equipe": "inimigos"}
        combate = {
            "participantes": [jogador, alvo, outro],
            "turno": 0,
            "ataque_pendente": {"atacante_id": "jogador", "defensor_id": "alvo"},
        }
        self.assertIs(luta._obter_defensor(combate), alvo)

    def test_next_turn_skips_dead_participant(self):
        from comandos.RPG.Luta.sistemas_luta import Luta

        luta = Luta.__new__(Luta)
        participantes = [
            {"id": "A", "vida": 100},
            {"id": "B", "vida": 0},
            {"id": "C", "vida": 100},
        ]
        combate = {"participantes": participantes, "turno": 0}
        self.assertEqual(luta._proximo_indice(combate, 0), 2)

    async def test_monster_attack_does_not_duplicate_existing_pending_attack(self):
        import comandos.RPG.Luta.ataque_resiliente as resiliente

        pending = {"atacante_id": "monstro", "defensor_id": "jogador"}
        combate = {"ativo": True, "fase": "ataque", "ataque_pendente": pending}
        chamadas = []

        class FakeLuta:
            def _obter_combate(self, _):
                return combate

            def _criar_ataque(self, *args, **kwargs):
                chamadas.append("criar")
                raise AssertionError("ataque duplicado")

        class FakeCtx:
            channel = SimpleNamespace(id=1)

        original = resiliente._original_ataque_monstro
        resiliente._original_ataque_monstro = lambda *_args, **_kwargs: None
        try:
            await resiliente._ataque_monstro_resiliente(FakeLuta(), FakeCtx())
        finally:
            resiliente._original_ataque_monstro = original

        self.assertEqual(chamadas, [])
        self.assertIs(combate["ataque_pendente"], pending)
        self.assertEqual(combate["fase"], "defesa")

    async def test_monster_attack_fallback_creates_pending_attack(self):
        import comandos.RPG.Luta.ataque_resiliente as resiliente

        combate = {
            "ativo": True,
            "fase": "ataque",
            "ataque_pendente": None,
        }
        atacante = {
            "id": "monstro",
            "tipo": "monstro",
            "vida": 100,
            "golpes": ["golpe_inexistente"],
            "dano_base": 10,
        }
        defensor = {"id": "jogador", "tipo": "jogador", "vida": 100}
        anuncios = []

        class FakeLuta:
            def _obter_combate(self, _):
                return combate

            def _obter_atacante(self, _):
                return atacante

            def _obter_defensor(self, _):
                return defensor

            def _criar_ataque(self, combate, *_args, **kwargs):
                ataque = {
                    "atacante_id": "monstro",
                    "defensor_id": "jogador",
                    "dano_base": kwargs["dano_base"],
                }
                combate["ataque_pendente"] = ataque
                return ataque

            async def _anunciar_ataque(self, _):
                anuncios.append(True)

        class FakeCtx:
            channel = SimpleNamespace(id=2)

        original = resiliente._original_ataque_monstro

        async def falha(*_args, **_kwargs):
            raise RuntimeError("falha simulada")

        resiliente._original_ataque_monstro = falha
        try:
            await resiliente._ataque_monstro_resiliente(FakeLuta(), FakeCtx())
        finally:
            resiliente._original_ataque_monstro = original

        self.assertIsNotNone(combate["ataque_pendente"])
        self.assertEqual(combate["fase"], "defesa")
        self.assertEqual(len(anuncios), 1)

    async def test_defense_exception_releases_resolving_state(self):
        from comandos.RPG.Luta import integridade_estado

        atacante = {"id": "monstro", "tipo": "monstro", "vida": 100}
        defensor = {"id": "jogador", "tipo": "jogador", "vida": 100}
        ataque = {"atacante_id": "monstro", "defensor_id": "jogador"}
        combate = {
            "ativo": True,
            "fase": "defesa",
            "ataque_pendente": ataque,
            "ui_stage": "defense_action",
            "ui_waiting_advance": False,
            "participantes": [atacante, defensor],
        }
        mensagens = []

        class FakeUI:
            async def send(self, *args, **kwargs):
                mensagens.append((args, kwargs))

        class FakeLuta:
            def _obter_combate(self, _):
                return combate

            def _ui_context(self, *_args):
                return FakeUI()

            def _obter_defensor(self, _):
                return defensor

            def _participante(self, _combate, participante_id):
                return next(p for p in _combate["participantes"] if str(p["id"]) == str(participante_id))

            async def _resolver_ataque(self, _ui):
                ataque["_resolvendo"] = True
                raise RuntimeError("falha simulada")

        class FakeCtx:
            channel = SimpleNamespace(id=3)
            author = SimpleNamespace(id="jogador")

        await integridade_estado._executar_defesa_unificado(FakeLuta(), FakeCtx(), "defesa")

        self.assertNotIn("_resolvendo", ataque)
        self.assertEqual(combate["ui_stage"], "defense_action")
        self.assertFalse(combate["ui_waiting_advance"])
        self.assertTrue(mensagens)

    def test_monster_contract_contains_tp_reward(self):
        from comandos.RPG.Luta.contrato_monstro import _normalizar_recompensa

        monstro = {"xp_recompensa": 75, "hunos_recompensa": 60}
        resultado = _normalizar_recompensa(monstro)
        self.assertEqual(resultado["tp_recompensa"], 75)
        self.assertEqual(resultado["hunos_recompensa"], 60)

    def test_prefix_and_public_commands_remain_exclamation_based(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        main = (root / "main.py").read_text(encoding="utf-8")
        commands = (root / "comandos/RPG/Luta/comandos_luta.py").read_text(encoding="utf-8")
        self.assertIn('command_prefix="!"', main)
        self.assertIn('name="luta"', commands)
        self.assertIn('name="pve"', commands)
        self.assertIn('name="soco"', commands)
        self.assertIn('name="defesa"', commands)
        self.assertIn('name="esquiva"', commands)


if __name__ == "__main__":
    unittest.main()
