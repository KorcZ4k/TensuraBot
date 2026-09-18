import asyncio

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
        "mana": 50, "efeitos": [], "defesa_ativa": False,
        "esquiva_ativa": False, "defesa_magica_ativa": False,
        "defesa_magica_valor": 0,
    }


def _combat():
    a, d = _p(1), _p("slime", "monstro")
    return {
        "participantes": [a, d], "turno": 0, "numero_turno": 1,
        "fase": "ataque", "ativo": True, "ataque_pendente": None,
        "historico": [], "ui_stage": "turn", "ui_waiting_advance": False,
        "guild_id": "g", "pvp": False,
    }


def test_turno_preserva_identidade_mesmo_com_lista_reordenada():
    cog = _cog()
    c = _combat()
    cog._normalizar_estado(c)
    assert c["_turno_participante_id"] == "1"
    c["participantes"].reverse()
    cog._normalizar_estado(c)
    assert c["_turno_participante_id"] == "1"
    assert cog._obter_atacante(c)["id"] == "1"


def test_ataque_pendente_nao_pode_ser_substituido():
    cog = _cog()
    c = _combat()
    a, d = c["participantes"]
    primeiro = cog._criar_ataque(c, "soco", a, d, dano_base=10)
    segundo = cog._criar_ataque(c, "soco", a, d, dano_base=99)
    assert segundo is primeiro
    assert c["ataque_pendente"]["dano_base"] == 10


def test_ataque_pendente_com_outro_alvo_falha():
    cog = _cog()
    c = _combat()
    a, d = c["participantes"]
    outro = _p("outro", "monstro")
    c["participantes"].append(outro)
    cog._criar_ataque(c, "soco", a, d, dano_base=10)
    try:
        cog._criar_ataque(c, "soco", a, outro, dano_base=10)
    except RuntimeError:
        pass
    else:
        raise AssertionError("ataque pendente foi redirecionado")


def test_ataque_invalido_nao_e_criado():
    cog = _cog()
    c = _combat()
    a, d = c["participantes"]
    try:
        cog._criar_ataque(c, "invalido", a, d)
    except ValueError:
        pass
    else:
        raise AssertionError("tipo inválido aceito")


def test_defesas_sao_limpa_em_um_unico_ponto():
    cog = _cog()
    c = _combat()
    for p in c["participantes"]:
        p["defesa_ativa"] = True
        p["esquiva_ativa"] = True
        p["defesa_magica_ativa"] = True
        p["defesa_magica_valor"] = 20
    cog._limpar_defesas(c)
    assert all(not p["defesa_ativa"] and not p["esquiva_ativa"] for p in c["participantes"])
    assert all(not p["defesa_magica_ativa"] and p["defesa_magica_valor"] == 0 for p in c["participantes"])


def test_pendente_com_alvo_morto_mantem_alvo_original():
    cog = _cog()
    c = _combat()
    a, d = c["participantes"]
    cog._criar_ataque(c, "soco", a, d, dano_base=10)
    d["vida"] = 0
    assert cog._obter_defensor(c) is d


def test_pendente_com_atacante_morto_mantem_atacante_original():
    cog = _cog()
    c = _combat()
    a, d = c["participantes"]
    cog._criar_ataque(c, "soco", a, d, dano_base=10)
    a["vida"] = 0
    assert cog._por_id(c, c["ataque_pendente"]["atacante_id"]) is a


def test_criador_balanceado_usa_o_mesmo_criador_de_dados():
    tipo = next(iter(bosses.luta_db.MONSTROS))
    base = bosses.luta_db.criar_monstro(tipo, 1)
    balanceado = bosses.criar_monstro_balanceado(tipo, 1)
    assert base is not None and balanceado is not None
    assert balanceado["vida"] == base["vida"]
    assert balanceado["dano_base"] == base["dano_base"]
    assert balanceado["xp_recompensa"] == base["xp_recompensa"]
    assert balanceado["tp_recompensa"] == base["tp_recompensa"]


def test_contrato_recompensa_tem_tp():
    tipo = next(iter(bosses.luta_db.MONSTROS))
    monstro = bosses.luta_db.criar_monstro(tipo, 1)
    if monstro is not None:
        assert "xp_recompensa" in monstro
        assert "tp_recompensa" in monstro
        assert "hunos_recompensa" in monstro


def test_resistencia_de_efeito_nao_aplica_stun_resistido(monkeypatch):
    defensor = _p("d", "monstro")
    defensor["boss_id"] = "dragao-adulto"
    monkeypatch.setattr(bosses.random, "random", lambda: 0.1)
    resultado = bosses.efeito_especial(defensor, {"nome": "stun", "turnos": 1})
    assert resultado is False
    assert defensor["efeitos"] == []


def test_efeito_corrosao_e_normalizado():
    defensor = _p("d", "monstro")
    efeito = bosses.efeito_especial(defensor, {"nome": "corrosao", "valor": 10, "turnos": 3})
    assert efeito["nome"] == "corrosao"
    assert defensor["efeitos"][0]["turnos"] == 3


def test_reward_without_database_is_safe():
    cog = _cog()
    c = _combat()
    c["participantes"][1].update({"xp_recompensa": 10, "tp_recompensa": 20, "hunos_recompensa": 30, "vida": 0})
    if bosses.luta_db.db is not None:
        return
    assert asyncio.run(cog._recompensar(c)) == (0, 0, 0)
