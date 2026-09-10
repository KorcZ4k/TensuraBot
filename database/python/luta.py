from database.python.mongodb import db
import json
import random


# ==========================================
# CARREGAR CONFIGURAÇÕES
# ==========================================

def _carregar_golpes():
    try:
        with open("database/json/golpes.json", "r", encoding="utf-8") as arquivo:
            return json.load(arquivo).get("golpes", {})
    except Exception as erro:
        print(f"Erro ao carregar golpes.json: {erro}")
        return {}


def _carregar_monstros():
    try:
        with open("database/json/monstros.json", "r", encoding="utf-8") as arquivo:
            return json.load(arquivo).get("monstros", {})
    except Exception as erro:
        print(f"Erro ao carregar monstros.json: {erro}")
        return {}


GOLPES = _carregar_golpes()
MONSTROS = _carregar_monstros()


def obter_jogador(user_id: str, guild_id: str):
    return db["Jogadores"].find_one({"ID": str(user_id), "guild_id": str(guild_id)})


def criar_participante_jogador(user_id: str, guild_id: str):
    jogador = obter_jogador(user_id, guild_id)
    if not jogador:
        return None
    forca = jogador.get("Força", 10)
    defesa = jogador.get("Defesa", 10)
    return {
        "id": str(user_id),
        "nome": jogador.get("Nome", f"Jogador_{user_id}"),
        "tipo": "jogador",
        "vida": jogador.get("Vida", 100),
        "vida_maxima": jogador.get("Vida_Maxima", jogador.get("Vida", 100)),
        "mana": jogador.get("Mana", 50),
        "mana_maxima": jogador.get("Mana_Maxima", jogador.get("Mana", 50)),
        "velocidade": jogador.get("Velocidade", 50),
        "Velocidade": jogador.get("Velocidade", 50),
        "Força": forca,
        "Defesa": defesa,
        "Destreza": jogador.get("Destreza", 10),
        "Magia": jogador.get("Magia", 0),
        "Inteligencia": jogador.get("Inteligencia", jogador.get("Inteligência", 0)),
        "defesa": forca + defesa,
        "defesa_ativa": False,
        "esquiva_ativa": False,
        "defesa_magica_ativa": False,
        "defesa_magica_valor": 0,
    }


def criar_monstro(tipo: str, nivel: int = 1):
    dados = MONSTROS.get(tipo)
    if not dados:
        return None
    nivel_minimo = dados.get("nivel_minimo", 1)
    nivel_maximo = dados.get("nivel_maximo", 99)
    nivel = max(nivel_minimo, min(nivel, nivel_maximo))
    fator_escala = 1 + ((nivel - 1) * 0.75)
    atributos_base = dados.get("atributos_base", {})
    forca = int(atributos_base.get("Força", 10) * fator_escala)
    defesa_base = int(atributos_base.get("Defesa", 10) * fator_escala)
    velocidade = int(atributos_base.get("Velocidade", 20) * fator_escala)
    destreza = int(atributos_base.get("Destreza", 10) * fator_escala)
    defesa_total = forca + defesa_base
    vida_base = dados.get("vida_base", 50)
    vida = int(vida_base * fator_escala)
    dano_base = int(dados.get("dano_base", 10) * fator_escala)
    xp_recompensa = int(dados.get("xp_recompensa", 20) * fator_escala)
    hunos_recompensa = int(dados.get("hunos_recompensa", 10) * fator_escala)
    return {
        "id": str(tipo), "nome": dados.get("nome", tipo), "emoji": dados.get("emoji", "👹"),
        "tipo": "monstro", "nivel": nivel, "nivel_minimo": nivel_minimo, "nivel_maximo": nivel_maximo,
        "vida": vida, "vida_maxima": vida, "mana": 0, "Força": forca, "Defesa": defesa_base,
        "Destreza": destreza, "defesa": defesa_total, "velocidade": velocidade, "Velocidade": velocidade,
        "dano_base": dano_base, "xp_recompensa": xp_recompensa, "hunos_recompensa": hunos_recompensa,
        "defesa_ativa": False, "esquiva_ativa": False, "defesa_magica_ativa": False, "defesa_magica_valor": 0,
    }


def ativar_defesa(participante):
    participante["defesa_ativa"] = True
    participante["esquiva_ativa"] = False


def ativar_esquiva(participante):
    participante["esquiva_ativa"] = True
    participante["defesa_ativa"] = False


def limpar_defesa(participante):
    participante["defesa_ativa"] = False
    participante["esquiva_ativa"] = False


def calcular_dano(atacante, defensor=None):
    if defensor and defensor.get("esquiva_ativa", False):
        chance_esquiva = 0.40
        defensor["esquiva_ativa"] = False
        if random.random() < chance_esquiva:
            return 0, "esquivou"
    reducao = 0.50 if defensor and defensor.get("defesa_ativa", False) else 0
    if atacante.get("tipo") == "jogador":
        forca = atacante.get("Força", 10)
        destreza = atacante.get("Destreza", 10)
        dano = int((forca + destreza) / 2) + random.randint(1, 10)
    else:
        dano = atacante.get("dano_base", 10) + random.randint(1, 15)
    if defensor:
        defesa = defensor.get("defesa", 0)
        dano = max(1, dano - int(defesa * 0.1))
    if reducao > 0:
        dano = int(dano * (1 - reducao))
    return max(1, dano), "normal"


def aplicar_dano(defensor, dano):
    defensor["vida"] = max(0, defensor.get("vida", 0) - dano)
    return defensor["vida"]


def esta_vivo(participante):
    return participante.get("vida", 0) > 0


def pode_lutar(user_id: str, guild_id: str):
    jogador = obter_jogador(user_id, guild_id)
    if not jogador:
        return {"pode": False, "mensagem": "Jogador não encontrado."}
    situacao = str(jogador.get("Situação", "")).strip().casefold()
    if situacao == "morto":
        return {"pode": False, "mensagem": "❌ Você está morto."}
    if jogador.get("Vida", 0) <= 0:
        return {"pode": False, "mensagem": "❌ Você está sem vida."}
    # Combates são mantidos apenas em memória. Um estado ativo persistido
    # sem combate correspondente é necessariamente órfão (ex.: reinício).
    # O bot limpará esses estados no startup; aqui não os tratamos como morte.
    if situacao == "ativo_combate":
        return {"pode": False, "mensagem": "❌ Você já está em combate."}
    return {"pode": True, "mensagem": "Pode lutar."}


def obter_vencedores(combate):
    participantes = combate.get("participantes", [])
    derrotados = [p for p in participantes if p.get("vida", 0) <= 0]
    if not derrotados:
        return None
    if combate.get("pvp", False):
        for participante in participantes:
            if participante.get("vida", 0) > 0:
                return {"tipo": "vitoria", "vencedor": participante}
        return {"tipo": "empate", "vencedor": None}
    jogadores_vivos = any(p.get("tipo") == "jogador" and p.get("vida", 0) > 0 for p in participantes)
    monstros_vivos = any(p.get("tipo") == "monstro" and p.get("vida", 0) > 0 for p in participantes)
    if jogadores_vivos and not monstros_vivos:
        return {"tipo": "vitoria", "lado": "jogadores"}
    if monstros_vivos and not jogadores_vivos:
        return {"tipo": "vitoria", "lado": "monstros"}
    return {"tipo": "empate"}


def finalizar_combate(combate):
    guild_id = combate.get("guild_id")
    resultado = obter_vencedores(combate)
    participantes = combate.get("participantes", [])
    if not guild_id:
        return resultado
    for participante in participantes:
        if participante.get("tipo") != "jogador":
            continue
        vida = max(0, int(participante.get("vida", 0) or 0))
        situacao = "morto" if vida <= 0 else "ativo"
        db["Jogadores"].update_one(
            {"ID": str(participante.get("id")), "guild_id": str(guild_id)},
            {"$set": {"Vida": vida, "Mana": int(participante.get("mana", 0) or 0), "Situação": situacao}},
        )
    return resultado
