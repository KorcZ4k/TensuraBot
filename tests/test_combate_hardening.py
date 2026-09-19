import ast
import json
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

    def test_party_combat_uses_the_canonical_lock_and_nonblocking_monster_creation(self):
        text = source("comandos/RPG/party.py")
        self.assertIn("async with luta_cog._lock(ctx.channel.id):", text)
        self.assertIn("await run_db(luta_db.criar_monstro", text)

    def test_combat_has_one_canonical_resolver(self):
        text = source("comandos/RPG/luta.py")
        self.assertIn("class Luta(commands.Cog)", text)
        self.assertNotIn("class LutaBase", text)
        self.assertIn("async def _resolver_ataque", text)
        self.assertIn('ataque.get("defensor_id")', text)
        self.assertEqual(text.count("async def _resolver_ataque"), 1)

    def test_luta_is_the_only_public_fight_command_owner(self):
        main = source("main.py")
        comandos = source("comandos/RPG/luta.py")
        self.assertIn('"comandos.RPG.luta"', main)
        self.assertNotIn('"comandos.RPG.Luta.comandos_luta"', main)
        self.assertNotIn('"comandos.RPG.correcoes_luta"', main)
        self.assertNotIn('"comandos.RPG.correcoes_monstros"', main)
        self.assertNotIn('"comandos.RPG.correcoes_luta_segura"', main)
        self.assertIn("async def luta(ctx)", comandos)
        self.assertIn("async def monstros(ctx)", comandos)
        self.assertIn("async def pve(ctx", comandos)
        self.assertIn("luta_db.iniciar_cooldown_monstro", comandos)
        self.assertIn("luta_db.cancelar_cooldown_monstro", comandos)

    def test_no_duplicate_combat_cogs_remain(self):
        self.assertFalse((ROOT / "comandos/RPG/correcoes_monstros.py").exists())
        self.assertFalse((ROOT / "comandos/RPG/correcoes_luta_segura.py").exists())
        self.assertIn("class Luta(commands.Cog)", source("comandos/RPG/luta.py"))
        self.assertNotIn("class LutaBase", source("comandos/RPG/luta.py"))

    def test_public_commands_are_module_callbacks_without_self_binding(self):
        text = source("comandos/RPG/luta.py")
        for signature in (
            "async def luta(ctx)",
            "async def monstros(ctx)",
            "async def pve(ctx, *, monstro_tipo: str = \"\")",
            "async def pvp(ctx, membro: Optional[discord.Member] = None)",
            "async def soco(ctx)",
            "async def chute(ctx)",
            "async def defesa(ctx)",
            "async def esquiva(ctx)",
            "async def fugir(ctx)",
            "async def matar(ctx)",
            "async def desmaiar(ctx)",
        ):
            self.assertIn(signature, text)

    def test_legacy_patch_modules_do_not_override_canonical_resolver(self):
        for relative in (
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

    def test_restart_recovers_orphaned_combat_status(self):
        text = source("main.py")
        self.assertIn("async def _recuperar_combates_orfaos", text)
        self.assertIn('{"Situação": "ativo_combate"}', text)
        self.assertIn('{"$set": {"Situação": "ativo"}}', text)
        self.assertIn("await _recuperar_combates_orfaos()", text)

    def test_slime_has_no_stun_or_control_effects(self):
        data = json.loads(source("database/json/golpes.json"))
        golpes = data["golpes"]
        for nome in ("pancada", "investida"):
            efeito = golpes[nome].get("efeito")
            self.assertIsNone(efeito, f"{nome} não pode aplicar efeito de controle")

    def test_monster_definition_only_references_existing_attacks(self):
        monstros = json.loads(source("database/json/monstros.json"))["monstros"]
        golpes = json.loads(source("database/json/golpes.json"))["golpes"]
        for nome, monstro in monstros.items():
            for golpe in monstro.get("golpes", []):
                self.assertIn(golpe, golpes, f"Monstro {nome} referencia golpe inexistente: {golpe}")

    def test_every_monster_has_twelve_hour_cooldown(self):
        monstros = json.loads(source("database/json/monstros.json"))["monstros"]
        self.assertTrue(monstros)
        for nome, monstro in monstros.items():
            self.assertEqual(monstro.get("cooldown_horas"), 12, f"Monstro {nome} deve ter cooldown de 12h")

    def test_monster_cooldown_is_persistent_and_per_monster(self):
        text = source("database/python/luta.py")
        self.assertIn("MONSTRO_COOLDOWN_HORAS = 12", text)
        self.assertIn("Cooldowns_Monstros", text)
        self.assertIn("iniciar_cooldown_monstro", text)
        self.assertIn("cancelar_cooldown_monstro", text)
        self.assertIn("timedelta(hours=horas)", text)

    def test_pve_reserves_cooldown_only_after_validation(self):
        text = source("comandos/RPG/luta.py")
        self.assertLess(text.index("monstro_id = cog._encontrar_monstro"), text.index("luta_db.pode_lutar"))
        self.assertLess(text.index("luta_db.pode_lutar"), text.index("luta_db.iniciar_cooldown_monstro"))
        self.assertLess(text.index("luta_db.iniciar_cooldown_monstro"), text.index("luta_db.criar_monstro"))
        self.assertIn("cancelar_cooldown_monstro", text)
        self.assertIn("cog.combates.pop(ctx.channel.id, None)", text)

    def test_rest_and_meditation_always_restore_life(self):
        text = source("database/python/status_async.py")
        self.assertIn('0.50,', text)
        self.assertIn('"Vida": nova_vida', text)
        self.assertIn('"vida_recuperada"', text)

    def test_combat_image_mapping_is_monster_only(self):
        text = source("comandos/RPG/luta.py")
        imagens = json.loads(source("database/json/Imagens.json"))["Imagens"]
        for monstro in ("slime", "goblin", "lobo", "orc", "esqueleto", "dragao", "titan", "fenix", "demonio"):
            self.assertIn(f'"{monstro}-luta-url"', text)
            self.assertIn(f"{monstro}-luta-url", imagens)
        self.assertIn("def imagem_ataque(nome):", text)
        self.assertIn("return None", text)
        self.assertIn("imagem_ataque é propositalmente ignorada", text)

    def test_combat_image_can_be_attached_to_embed(self):
        text = source("comandos/RPG/luta.py")
        self.assertIn("async def _baixar_imagem_monstro(url):", text)
        self.assertIn('panel.set_image(url=f"attachment://{filename}")', text)
        self.assertIn('kwargs["file"] = arquivo', text)
        self.assertNotIn("imagem_ataque=imagem_ataque", text)

    def test_single_message_combat_ui_requires_manual_advance(self):
        text = source("comandos/RPG/luta.py")
        self.assertIn("class _AvancarView(discord.ui.View):", text)
        self.assertIn('custom_id="luta:avancar"', text)
        self.assertIn('label="Avançar"', text)
        self.assertIn('combate["ui_stage"] = "attributes"', text)
        self.assertIn('combate["ui_stage"] = "velocity"', text)
        self.assertIn('combate["ui_stage"] = "attack"', text)
        self.assertIn('combate["ui_stage"] = "result"', text)
        self.assertIn('await self._proximo_turno(interaction)', text)
        self.assertIn('await self._resolver_ataque(self._ui_context(interaction, combate))', text)

    def test_single_message_ui_adapts_engine_sends_and_finalization(self):
        text = source("comandos/RPG/luta.py")
        self.assertIn('async def send(self, content=None, **kwargs):', text)
        self.assertIn("class _UIContext:", text)
        self.assertIn('self._message.edit(embed=padrao, attachments=[], view=view)', text)
        self.assertIn('attachments=[]', text)
        self.assertIn('ui_waiting_advance', text)
        self.assertIn('await self._finalizar(self._ui_context(ctx, combate), motivo="vida")', text)
        self.assertIn('await self._aplicar_efeitos_inicio(ui_ctx, atacante)', text)

    def test_monster_turn_is_not_auto_resolved_in_single_message_ui(self):
        text = source("comandos/RPG/luta.py")
        self.assertIn('if atacante and atacante.get("tipo") == "monstro":', text)
        self.assertIn('await self._criar_ataque_monstro_ui(combate)', text)
        self.assertIn('elif stage == "attack":', text)
        self.assertIn('await self._resolver_ataque(self._ui_context(interaction, combate))', text)

    def test_hardening_modules_remain_valid_python(self):
        for relative in (
            "database/python/luta.py",
            "database/python/luta_async.py",
            "database/python/status_async.py",
            "comandos/RPG/luta.py",
            "comandos/RPG/luta_sync.py",
            "comandos/RPG/party.py",
            "comandos/RPG/correcoes_concorrencia.py",
            "comandos/RPG/correcoes_party.py",
            "comandos/RPG/habilidades_combate.py",
            "comandos/RPG/Luta/Infos_Luta.py",
            "comandos/RPG/monstros_balanceamento.py",
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
