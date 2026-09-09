from database.python.mongodb import db
import json
import random
import datetime

jogadores = db["Jogadores"]


def _carregar_mensagens_morte():
    try:
        with open('data/death_messages.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Erro ao carregar mensagens de morte: {e}")
        return {"humanas": ["{nome} caiu em batalha! Sua alma partiu para sempre."], "monstros": ["O monstro {nome} foi derrotado! Sua essência se dissipou."], "animados": ["{nome} foi destruído! Sua energia se desfez."]}

DEATH_MESSAGES = _carregar_mensagens_morte()


def obter_status(user_id: int, guild_id: int):
    return jogadores.find_one({"ID": str(user_id), "guild_id": str(guild_id)})


def obter_atributo(user_id: int, guild_id: int, atributo: str):
    jogador = jogadores.find_one({"ID": str(user_id), "guild_id": str(guild_id)}, {atributo: 1, "_id": 0})
    return None if jogador is None else jogador.get(atributo, 0)


def alterar_atributo(user_id: int, guild_id: int, atributo: str, valor: int):
    if atributo not in ["Força", "Defesa", "Velocidade", "Destreza", "Magia", "Sorte"]:
        raise ValueError("Atributo inválido.")
    if valor < 0:
        raise ValueError("O valor não pode ser negativo.")
    resultado = jogadores.update_one({"ID": str(user_id), "guild_id": str(guild_id)}, {"$set": {atributo: valor}})
    if resultado.matched_count == 0:
        raise ValueError("Jogador não encontrado.")
    return valor


def aumentar_atributo(user_id: int, guild_id: int, atributo: str, quantidade: int):
    if atributo not in ["Força", "Defesa", "Velocidade", "Destreza", "Magia", "Sorte"]:
        raise ValueError("Atributo inválido.")
    if quantidade <= 0:
        raise ValueError("A quantidade deve ser maior que zero.")
    resultado = jogadores.find_one_and_update({"ID": str(user_id), "guild_id": str(guild_id)}, {"$inc": {atributo: quantidade}}, return_document=True)
    if resultado is None:
        raise ValueError("Jogador não encontrado.")
    return resultado.get(atributo, 0)


def reduzir_atributo(user_id: int, guild_id: int, atributo: str, quantidade: int):
    if atributo not in ["Força", "Defesa", "Velocidade", "Destreza", "Magia", "Sorte"]:
        raise ValueError("Atributo inválido.")
    if quantidade <= 0:
        raise ValueError("A quantidade deve ser maior que zero.")
    resultado = jogadores.find_one_and_update({"ID": str(user_id), "guild_id": str(guild_id), atributo: {"$gte": quantidade}}, {"$inc": {atributo: -quantidade}}, return_document=True)
    if resultado is None:
        raise ValueError("Não foi possível reduzir o atributo.")
    return resultado.get(atributo, 0)


def obter_xp(user_id: int, guild_id: int):
    jogador = jogadores.find_one({"ID": str(user_id), "guild_id": str(guild_id)}, {"XP": 1, "_id": 0})
    return None if jogador is None else jogador.get("XP", 0)


def adicionar_xp(user_id: int, guild_id: int, quantidade: int):
    if quantidade <= 0:
        raise ValueError("A quantidade de XP deve ser maior que zero.")
    resultado = jogadores.find_one_and_update({"ID": str(user_id), "guild_id": str(guild_id)}, {"$inc": {"XP": quantidade}}, return_document=True)
    if resultado is None:
        raise ValueError("Jogador não encontrado.")
    xp_atual = resultado.get("XP", 0)
    nivel_atual = resultado.get("Nivel", 1)
    xp_maximo = 100 * nivel_atual
    while xp_atual >= xp_maximo:
        xp_atual -= xp_maximo
        nivel_atual += 1
        xp_maximo = 100 * nivel_atual
        jogadores.update_one({"ID": str(user_id), "guild_id": str(guild_id)}, {"$set": {"Nivel": nivel_atual, "XP": xp_atual, "XP_maximo": xp_maximo}})
    return xp_atual


def remover_xp(user_id: int, guild_id: int, quantidade: int):
    if quantidade <= 0:
        raise ValueError("A quantidade de XP deve ser maior que zero.")
    resultado = jogadores.find_one_and_update({"ID": str(user_id), "guild_id": str(guild_id), "XP": {"$gte": quantidade}}, {"$inc": {"XP": -quantidade}}, return_document=True)
    if resultado is None:
        raise ValueError("XP insuficiente ou jogador não encontrado.")
    return resultado.get("XP", 0)


def alterar_nivel(user_id: int, guild_id: int, nivel: int):
    if nivel < 0:
        raise ValueError("O nível não pode ser negativo.")
    resultado = jogadores.update_one({"ID": str(user_id), "guild_id": str(guild_id)}, {"$set": {"Nivel": nivel}})
    if resultado.matched_count == 0:
        raise ValueError("Jogador não encontrado.")
    return nivel


def alterar_nome(user_id: int, guild_id: int, nome: str):
    if not nome or not nome.strip():
        raise ValueError("O nome não pode estar vazio.")
    resultado = jogadores.update_one({"ID": str(user_id), "guild_id": str(guild_id)}, {"$set": {"Nome": nome.strip()}})
    if resultado.matched_count == 0:
        raise ValueError("Jogador não encontrado.")
    return nome.strip()


def alterar_raca(user_id: int, guild_id: int, raca: str):
    if not raca or not raca.strip():
        raise ValueError("A raça não pode estar vazia.")
    resultado = jogadores.update_one({"ID": str(user_id), "guild_id": str(guild_id)}, {"$set": {"Raça": raca.strip()}})
    if resultado.matched_count == 0:
        raise ValueError("Jogador não encontrado.")
    return raca.strip()


def verificar_morte(user_id: int, guild_id: int):
    jogador = jogadores.find_one({"ID": str(user_id), "guild_id": str(guild_id)})
    if not jogador:
        return None
    if jogador.get("Situação") == "morto":
        return {"morreu": True, "ja_estava_morto": True, "mensagem": f"{jogador.get('Nome', 'Alguém')} já está morto."}
    if jogador.get("Vida", 0) <= 0:
        return _aplicar_morte_permanente(jogador, user_id, guild_id, "humano")
    return None


def _aplicar_morte_permanente(jogador, user_id, guild_id, tipo):
    mensagens = DEATH_MESSAGES.get("monstros" if tipo.startswith("monstro") else "animados" if tipo == "animado" else "humanas", ["{nome} morreu permanentemente!"])
    mensagem = random.choice(mensagens).format(nome=jogador.get("Nome", jogador.get("ID", "Alguém")))
    resultado = jogadores.update_one({"ID": str(user_id), "guild_id": str(guild_id)}, {"$set": {"Situação": "morto", "Vida": 0, "data_morte": datetime.datetime.utcnow().isoformat(), "mensagem_morte": mensagem, "tipo_morte": tipo}})
    if resultado.modified_count > 0:
        return {"morreu": True, "ja_estava_morto": False, "mensagem": mensagem, "tipo": tipo}
    return {"morreu": False, "mensagem": "Erro ao processar a morte."}


def reviver(user_id: int, guild_id: int):
    jogador = jogadores.find_one({"ID": str(user_id), "guild_id": str(guild_id)})
    if not jogador:
        return {"sucesso": False, "mensagem": "Jogador não encontrado."}
    if jogador.get("Situação") != "morto":
        return {"sucesso": False, "mensagem": "Este jogador não está morto."}
    vida_maxima = jogador.get("Vida_Maxima", 100)
    mana_maxima = jogador.get("Mana Total", 100)
    resultado = jogadores.update_one({"ID": str(user_id), "guild_id": str(guild_id)}, {"$set": {"Situação": "ativo", "Vida": vida_maxima, "Mana": mana_maxima, "data_morte": None, "mensagem_morte": None, "tipo_morte": None}})
    return {"sucesso": resultado.modified_count > 0, "mensagem": f"{jogador.get('Nome', 'Alguém')} foi revivido!" if resultado.modified_count > 0 else "Erro ao reviver."}


def aplicar_dano(user_id: int, guild_id: int, dano: int, tipo_dano: str = "fisico"):
    jogador = jogadores.find_one({"ID": str(user_id), "guild_id": str(guild_id)})
    if not jogador:
        return {"sucesso": False, "mensagem": "Jogador não encontrado."}
    if jogador.get("Situação") == "morto":
        return {"sucesso": False, "mensagem": f"{jogador.get('Nome', 'Alguém')} já está morto.", "ja_morto": True}
    vida = jogador.get("Vida", 0)
    reducao = int(jogador.get("Defesa", 0) * 0.2) if tipo_dano == "fisico" else 0
    dano_reduzido = max(1, int(dano) - reducao)
    nova_vida = max(0, vida - dano_reduzido)
    jogadores.update_one({"ID": str(user_id), "guild_id": str(guild_id)}, {"$set": {"Vida": nova_vida}})
    morte = verificar_morte(user_id, guild_id)
    return {"sucesso": True, "dano_aplicado": dano_reduzido, "vida_restante": 0 if morte else nova_vida, "morreu": bool(morte and morte.get("morreu")), "mensagem_morte": morte.get("mensagem", "") if morte else "", "ja_morto": False}


def aplicar_cura(user_id: int, guild_id: int, cura: int):
    jogador = jogadores.find_one({"ID": str(user_id), "guild_id": str(guild_id)})
    if not jogador:
        return {"sucesso": False, "mensagem": "Jogador não encontrado."}
    vida_maxima = jogador.get("Vida_Maxima", 100)
    nova_vida = min(vida_maxima, jogador.get("Vida", 0) + max(0, int(cura)))
    jogadores.update_one({"ID": str(user_id), "guild_id": str(guild_id)}, {"$set": {"Vida": nova_vida}})
    return {"sucesso": True, "cura_aplicada": nova_vida - jogador.get("Vida", 0), "vida_atual": nova_vida, "vida_maxima": vida_maxima}


def recuperar_mana(user_id: int, guild_id: int, tipo: str):
    jogador = jogadores.find_one({"ID": str(user_id), "guild_id": str(guild_id)})
    if not jogador:
        return {"sucesso": False, "mensagem": "Jogador não encontrado."}
    if jogador.get("Situação") == "morto":
        return {"sucesso": False, "mensagem": "❌ Você está morto."}
    if tipo not in {"descanso", "meditacao"}:
        return {"sucesso": False, "mensagem": "Tipo de recuperação inválido."}
    ultimo = jogador.get("ultima_recuperacao", {}).get(tipo)
    cooldown = 1800
    if ultimo:
        if isinstance(ultimo, str):
            ultimo = datetime.datetime.fromisoformat(ultimo)
        restante = cooldown - (datetime.datetime.utcnow() - ultimo).total_seconds()
        if restante > 0:
            return {"sucesso": False, "mensagem": f"⏰ Aguarde {int(restante // 60)}min para usar {tipo} novamente."}
    mana_maxima = int(jogador.get("Mana Total", 0) or 0)
    mana_atual = int(jogador.get("Mana", 0) or 0)
    recuperacao = max(1, mana_maxima // 2) if mana_atual < mana_maxima else 0
    nova_mana = min(mana_maxima, mana_atual + recuperacao)
    recuperacoes = jogador.get("ultima_recuperacao", {}).copy()
    recuperacoes[tipo] = datetime.datetime.utcnow().isoformat()
    jogadores.update_one({"_id": jogador["_id"]}, {"$set": {"Mana": nova_mana, "ultima_recuperacao": recuperacoes}})
    return {"sucesso": True, "mensagem": f"✅ {tipo.capitalize()} concluído.", "mana_recuperada": nova_mana - mana_atual, "mana_atual": nova_mana, "mana_maxima": mana_maxima, "percentual": (recuperacao / mana_maxima * 100) if mana_maxima else 0, "cooldown_horas": 0.5}


def get_cooldown_recuperacao(user_id: str, guild_id: str, tipo: str):
    jogador = jogadores.find_one({"ID": str(user_id), "guild_id": str(guild_id)})
    if not jogador:
        return 0
    ultimo = jogador.get("ultima_recuperacao", {}).get(tipo)
    if not ultimo:
        return 0
    if isinstance(ultimo, str):
        ultimo = datetime.datetime.fromisoformat(ultimo)
    return max(0, 0.5 - (datetime.datetime.utcnow() - ultimo).total_seconds() / 3600)


def esta_morto(user_id: int, guild_id: int):
    jogador = jogadores.find_one({"ID": str(user_id), "guild_id": str(guild_id)})
    return bool(jogador and jogador.get("Situação") == "morto")
