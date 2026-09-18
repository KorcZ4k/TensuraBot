import asyncio
import unittest
from unittest.mock import patch

from comandos.RPG.Luta.hardening_final import Luta
from comandos.RPG import monstros_balanceamento as bosses


def _cog():
    cog = Luta.__new__(Luta)
    cog.combates = {}
    cog._embeds_acao = {}
    cog._ui_views = {}
    cog._ui_avancar_locks = {}
    return cog


def _p(pid, tipo="jogador", equipe=None, vida=100):
    return {
        "id": str(pid), "nome": str(pid), "tipo": tipo,
        "equipe": equipe or ("jogadores" if tipo == "jogador" else "inimigos"),
        "vida": vida, "vida_maxima": 100, "defesa": 10,
        "Força": 10, "Defesa": 10, "Velocidade": 10, "Destreza": 10,
        "Magia": 50, "Inteligencia": 10, "mana": 50,
        "efeitos": [], "defesa_ativa": False, "esquiva_ativa": False,
        "defesa_magica_ativa": False, "defesa_magica_valor": 0,
    }


def _combat():
    a, d = _p(1), _p("slime", "monstro")
    return {
        "participantes": [a, d], "turno": 0, "numero_turno": 1,
        "fase": "ataque", "ativo": True, "ataque_pendente": None,
        "historico": [], "ui_stage": "turn", "ui_waiting_advance": False,
        "guild_id": "g", "pvp": False,
    }


class LutaInvariantTests(unittest.TestCase):
    def test_turno_preserva_identidade_mesmo_com_lista_reordenada(self):
        cog, c = _cog(), _combat()
        cog._normalizar_estado(c)
        c["participantes"].reverse()
        cog._normalizar_estado(c)
        self.assertEqual(c["_turno_participante_id"], "1")
        self.assertEqual(cog._obter_atacante(c)["id"], "1")

    def test_ataque_pendente_nao_pode_ser_substituido(self):
        cog, c = _cog(), _combat()
        a, d = c["participantes"]
        primeiro = cog._criar_ataque(c, "soco", a, d, dano_base=10)
        segundo = cog._criar_ataque(c, "soco", a, d, dano_base=99)
        self.assertIs(segundo, primeiro)
        self.assertEqual(c["ataque_pendente"]["dano_base"], 10)

    def test_ataque_pendente_com_outro_alvo_falha(self):
        cog, c = _cog(), _combat()
        a, d = c["participantes"]
        outro = _p("outro", "monstro")
        c["participantes"].append(outro)
        cog._criar_ataque(c, "soco", a, d, dano_base=10)
        with self.assertRaises(RuntimeError):
            cog._criar_ataque(c, "soco", a, outro, dano_base=10)

    def test_ataque_invalido_nao_e_criado(self):
        cog, c = _cog(), _combat()
        a, d = c["participantes"]
        with self.assertRaises(ValueError):
            cog._criar_ataque(c, "invalido", a, d)

    def test_defesas_sao_limpa_em_um_unico_ponto(self):
        cog, c = _cog(), _combat()
        for p in c["participantes"]:
            p.update(defesa_ativa=True, esquiva_ativa=True, defesa_magica_ativa=True, defesa_magica_valor=20)
        cog._limpar_defesas(c)
        self.assertTrue(all(not p["defesa_ativa"] and not p["esquiva_ativa"] for p in c["participantes"]))
        self.assertTrue(all(not p["defesa_magica_ativa"] and p["defesa_magica_valor"] == 0 for p in c["participantes"]))

    def test_pendente_com_alvo_morto_mantem_alvo_original(self):
        cog, c = _cog(), _combat()
        a, d = c["participantes"]
        cog._criar_ataque(c, "soco", a, d, dano_base=10)
        d["vida"] = 0
        self.assertIs(cog._obter_defensor(c), d)

    def test_pendente_com_atacante_morto_mantem_atacante_original(self):
        cog, c = _cog(), _combat()
        a, d = c["participantes"]
        cog._criar_ataque(c, "soco", a, d, dano_base=10)
        a["vida"] = 0
        self.assertIs(cog._por_id(c, c["ataque_pendente"]["atacante_id"]), a)

    def test_criador_balanceado_usa_o_mesmo_criador_de_dados(self):
        tipo = next(iter(bosses.luta_db.MONSTROS))
        base = bosses.luta_db.criar_monstro(tipo, 1)
        balanceado = bosses.criar_monstro_balanceado(tipo, 1)
        self.assertIsNotNone(base)
        self.assertIsNotNone(balanceado)
        self.assertEqual(balanceado["vida"], base["vida"])
        self.assertEqual(balanceado["dano_base"], base["dano_base"])
        self.assertEqual(balanceado["xp_recompensa"], base["xp_recompensa"])
        self.assertEqual(balanceado["tp_recompensa"], base["tp_recompensa"])

    def test_contrato_recompensa_tem_tp(self):
        for tipo in bosses.luta_db.MONSTROS:
            monstro = bosses.luta_db.criar_monstro(tipo, 1)
            self.assertIn("xp_recompensa", monstro)
            self.assertIn("tp_recompensa", monstro)
            self.assertIn("hunos_recompensa", monstro)

    def test_resistencia_de_efeito_nao_aplica_stun_resistido(self):
        defensor = _p("d", "monstro")
        defensor["boss_id"] = "dragao-adulto"
        with patch.object(bosses.random, "random", return_value=0.1):
            resultado = bosses.efeito_especial(defensor, {"nome": "stun", "turnos": 1})
        self.assertFalse(resultado)
        self.assertEqual(defensor["efeitos"], [])

    def test_efeito_corrosao_e_normalizado(self):
        defensor = _p("d", "monstro")
        efeito = bosses.efeito_especial(defensor, {"nome": "corrosao", "valor": 10, "turnos": 3})
        self.assertEqual(efeito["nome"], "corrosao")
        self.assertEqual(defensor["efeitos"][0]["turnos"], 3)

    def test_reward_without_database_is_safe(self):
        if bosses.luta_db.db is not None:
            self.skipTest("Banco disponível")
        cog, c = _cog(), _combat()
        c["participantes"][1].update(xp_recompensa=10, tp_recompensa=20, hunos_recompensa=30, vida=0)
        self.assertEqual(asyncio.run(cog._recompensar(c)), (0, 0, 0))

    def test_regras_de_boss_nao_removem_participantes_no_meio_da_maquina(self):
        c = _combat()
        invocado = _p("inv", "monstro")
        invocado.update(invocado=True, expira_turno=1)
        c["participantes"].append(invocado)
        bosses.preparar_proximo_turno(c)
        self.assertIn(invocado, c["participantes"])
        self.assertIn("inv", c["_participantes_expirados"])

    def test_recompensa_usa_tp_explicitamente(self):
        cog, c = _cog(), _combat()
        c["participantes"][1].update(xp_recompensa=100, tp_recompensa=300, hunos_recompensa=50, vida=0)
        self.assertEqual(c["participantes"][1]["tp_recompensa"], 300)

    def test_ataque_pendente_tem_fase_defesa(self):
        cog, c = _cog(), _combat()
        a, d = c["participantes"]
        cog._criar_ataque(c, "fisico", a, d, dano_base=10)
        self.assertEqual(c["fase"], "defesa")
        self.assertEqual(c["ui_stage"], "attack")

    def test_resolucao_restaurada_se_edicao_da_ui_falhar(self):
        cog, c = _cog(), _combat()
        a, d = c["participantes"]
        cog._criar_ataque(c, "soco", a, d, dano_base=10)
        original_vida = d["vida"]
        cog.combates[1] = c

        async def falhar_ui(*_args, **_kwargs):
            raise RuntimeError("message.edit falhou")

        async def salvar(*_args, **_kwargs):
            return None

        async def proximo(*_args, **_kwargs):
            return None

        cog._ui_editar = falhar_ui
        cog._salvar = salvar
        cog._proximo_turno = proximo
        with self.assertRaises(RuntimeError):
            asyncio.run(cog._resolver_ataque(type("Ctx", (), {"channel": type("Ch", (), {"id": 1})()})()))
        self.assertIsNotNone(c["ataque_pendente"])
        self.assertEqual(c["fase"], "defesa")
        self.assertEqual(c["ui_stage"], "attack")
        self.assertEqual(d["vida"], original_vida)
        self.assertNotIn("_resolvendo", c["ataque_pendente"])

    def test_resolucao_de_pendente_com_atacante_morto_descarta_sem_redirecionar(self):
        cog, c = _cog(), _combat()
        a, d = c["participantes"]
        cog._criar_ataque(c, "soco", a, d, dano_base=10)
        a["vida"] = 0
        cog.combates[1] = c
        calls = []

        async def salvar(*_args, **_kwargs):
            return None

        async def proximo(*_args, **_kwargs):
            calls.append(True)

        cog._salvar = salvar
        cog._proximo_turno = proximo
        asyncio.run(cog._resolver_ataque(type("Ctx", (), {"channel": type("Ch", (), {"id": 1})()})()))
        self.assertIsNone(c["ataque_pendente"])
        self.assertEqual(calls, [True])
        self.assertIs(cog._por_id(c, "1"), a)

    def test_resolucao_de_pendente_com_defensor_morto_descarta_sem_redirecionar(self):
        cog, c = _cog(), _combat()
        a, d = c["participantes"]
        cog._criar_ataque(c, "soco", a, d, dano_base=10)
        d["vida"] = 0
        cog.combates[1] = c
        calls = []

        async def salvar(*_args, **_kwargs):
            return None

        async def proximo(*_args, **_kwargs):
            calls.append(True)

        cog._salvar = salvar
        cog._proximo_turno = proximo
        asyncio.run(cog._resolver_ataque(type("Ctx", (), {"channel": type("Ch", (), {"id": 1})()})()))
        self.assertIsNone(c["ataque_pendente"])
        self.assertEqual(calls, [True])
        self.assertIs(cog._por_id(c, "slime"), d)

    def test_ataque_de_area_atinge_todos_os_alvos_vivos(self):
        cog, c = _cog(), _combat()
        a, d = c["participantes"]
        extra = _p("extra", "jogador", equipe="jogadores", vida=100)
        c["participantes"].append(extra)
        a["tipo"] = "monstro"
        a["equipe"] = "inimigos"
        a["boss_id"] = "dragao-adulto"
        a["Força"] = 10
        a["Velocidade"] = 10
        cog.combates[1] = c
        cog._criar_ataque(c, "fisico", a, d, dano_base=10, area=True, area_targets=[d, extra])
        async def salvar(*_args, **_kwargs):
            return None
        async def ui(*_args, **_kwargs):
            return None
        cog._salvar = salvar
        cog._ui_editar = ui
        asyncio.run(cog._resolver_ataque(type("Ctx", (), {"channel": type("Ch", (), {"id": 1})()})()))
        self.assertLess(d["vida"], 100)
        self.assertLess(extra["vida"], 100)


    def test_recompensa_idempotente_retorna_cache(self):
        cog, c = _cog(), _combat()
        c.update(recompensa_aplicada=True, recompensa_xp=10, recompensa_hunos=20, recompensa_tp=30)
        self.assertEqual(asyncio.run(cog._recompensar(c)), (10, 20, 30))

    def test_lock_por_canal_e_unico(self):
        cog = _cog()
        self.assertIs(cog._lock(123), cog._lock(123))
        self.assertIsNot(cog._lock(123), cog._lock(456))

    def test_limpeza_de_recursos_para_view_registrada(self):
        cog, c = _cog(), _combat()
        class View:
            def __init__(self):
                self.parou = False
            def stop(self):
                self.parou = True
        class Msg:
            id = 55
        view = View()
        c["ui_message"] = Msg()
        cog._ui_views[55] = view
        asyncio.run(cog._limpar_recursos_combate(1, c))
        self.assertTrue(view.parou)
        self.assertNotIn(55, cog._ui_views)

    def test_ataque_pendente_e_fonte_de_verdade_mesmo_com_fase_incorreta(self):
        cog, c = _cog(), _combat()
        a, d = c["participantes"]
        a["tipo"], a["equipe"] = "monstro", "inimigos"
        d["tipo"], d["equipe"] = "jogador", "jogadores"
        primeiro = cog._criar_ataque(c, "ataque_monstro", a, d, dano_base=10)
        c["fase"] = "ataque"
        cog.combates[1] = c
        resultado = asyncio.run(cog._ataque_monstro(type("Ctx", (), {"channel": type("Ch", (), {"id": 1})()})()))
        self.assertIs(c["ataque_pendente"], primeiro)
        self.assertIs(resultado, primeiro)
        self.assertEqual(c["fase"], "defesa")


    def test_todos_os_golpes_dos_monstros_tem_tipo_aceitavel_ou_sao_defensivos(self):
        defensivos = {"defesa", "esquiva"}
        for monstro_id, dados in bosses.luta_db.MONSTROS.items():
            for golpe_id in dados.get("golpes", []):
                golpe = bosses.luta_db.GOLPES[golpe_id]
                tipo = str(golpe.get("tipo", "")).casefold()
                self.assertTrue(tipo in {"fisico", "magia", "magico", "mágico", "monstro"} or golpe_id in defensivos,
                                f"{monstro_id}/{golpe_id}: tipo={tipo}")

    def test_finalizar_combate_sem_db_nao_acessa_banco(self):
        import database.python.luta as luta_db
        resultado = {"participantes": [{"id": "1", "tipo": "jogador", "vida": 10}], "guild_id": "g"}
        if luta_db.db is not None:
            self.skipTest("Banco disponível")
        self.assertIsNotNone(luta_db.finalizar_combate(resultado))


if __name__ == "__main__":
    unittest.main()
