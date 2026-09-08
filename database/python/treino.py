from database.python.mongodb import db
import datetime
import json
import random

jogadores = db["Jogadores"]


def _carregar_config_treino():
    try:
        with open('database/json/treino.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Erro ao carregar configuração de treino: {e}")
        return {"treinos": {
            "leve": {"nome": "Treino Leve", "emoji": "🏃", "nivel_minimo": 1, "cooldown_horas": 12, "tp_minimo": 100, "tp_maximo": 200},
            "medio": {"nome": "Treino Médio", "emoji": "💪", "nivel_minimo": 10, "cooldown_horas": 15, "tp_minimo": 200, "tp_maximo": 500},
            "pesado": {"nome": "Treino Pesado", "emoji": "🏋️", "nivel_minimo": 20, "cooldown_horas": 20, "tp_minimo": 500, "tp_maximo": 1000},
            "supremo": {"nome": "Treino Supremo", "emoji": "🔥", "nivel_minimo": 50, "cooldown_horas": 24, "tp_minimo": 2000, "tp_maximo": 2000}},
            "atributos": ["Força", "Defesa", "Vitalidade", "Velocidade", "Destreza", "Magia", "Sorte", "Inteligencia"]}


CONFIG_TREINO = _carregar_config_treino()


def obter_jogador(user_id: int, guild_id: int):
    return jogadores.find_one({"ID": str(user_id), "guild_id": str(guild_id)})


def _verificar_cooldown_jogador(jogador, tipo_treino: str):
    if not jogador:
        return {"pode": False, "mensagem": "Jogador não encontrado."}
    if jogador.get("Situação") == "morto":
        return {"pode": False, "mensagem": "❌ Você está morto. Não pode treinar."}
    treino_config = CONFIG_TREINO["treinos"].get(tipo_treino)
    if not treino_config:
        return {"pode": False, "mensagem": "Tipo de treino inválido."}
    nivel = jogador.get("Nivel", 1)
    if nivel < treino_config["nivel_minimo"]:
        return {"pode": False, "mensagem": f"❌ Você precisa ser nível **{treino_config['nivel_minimo']}** para fazer {treino_config['nome']}. (Seu nível: {nivel})"}
    ultimo_treino_tipo = jogador.get("ultimo_treino", {}).get(tipo_treino)
    if ultimo_treino_tipo:
        data_ultimo = datetime.datetime.fromisoformat(ultimo_treino_tipo)
        horas_passadas = (datetime.datetime.utcnow() - data_ultimo).total_seconds() / 3600
        if horas_passadas < treino_config["cooldown_horas"]:
            horas_restantes = treino_config["cooldown_horas"] - horas_passadas
            return {"pode": False, "mensagem": f"⏰ Você já fez {treino_config['nome']} recentemente. Aguarde {int(horas_restantes)} horas."}
    return {"pode": True}


def verificar_cooldown(user_id: int, guild_id: int, tipo_treino: str):
    return _verificar_cooldown_jogador(obter_jogador(user_id, guild_id), tipo_treino)


def realizar_treino(user_id: int, guild_id: int, tipo_treino: str):
    """Treino concede TP em centenas; o Supremo concede exatamente 2000 TP."""
    jogador = obter_jogador(user_id, guild_id)
    verificacao = _verificar_cooldown_jogador(jogador, tipo_treino)
    if not verificacao["pode"]:
        return {"sucesso": False, "mensagem": verificacao["mensagem"]}

    config = CONFIG_TREINO["treinos"][tipo_treino]
    minimo = int(config.get("tp_minimo", 100))
    maximo = int(config.get("tp_maximo", minimo))
    tp_ganho = minimo if minimo == maximo else random.randrange(minimo, maximo + 1, 100)

    ultimo_treino = jogador.get("ultimo_treino", {}).copy()
    ultimo_treino[tipo_treino] = datetime.datetime.utcnow().isoformat()
    resultado = jogadores.update_one(
        {"_id": jogador["_id"]},
        {"$set": {"ultimo_treino": ultimo_treino}, "$inc": {"TP": tp_ganho}},
    )
    if resultado.modified_count <= 0:
        return {"sucesso": False, "mensagem": "Erro ao realizar treino."}
    tp_atual = int(jogador.get("TP", 0) or 0) + tp_ganho
    return {"sucesso": True, "mensagem": f"✅ {config['emoji']} **{config['nome']}** realizado com sucesso!", "tp_ganho": tp_ganho, "tp_atual": tp_atual, "cooldown_horas": config["cooldown_horas"]}


def listar_treinos_disponiveis(user_id: int, guild_id: int):
    jogador = obter_jogador(user_id, guild_id)
    if not jogador:
        return []
    nivel = jogador.get("Nivel", 1)
    return [{"tipo": tipo, "nome": config["nome"], "emoji": config["emoji"], "nivel_minimo": config["nivel_minimo"], "cooldown_horas": config["cooldown_horas"], "descricao": config.get("descricao", ""), "tp_minimo": config.get("tp_minimo", 100), "tp_maximo": config.get("tp_maximo", 100)} for tipo, config in CONFIG_TREINO["treinos"].items() if nivel >= config["nivel_minimo"]]


def get_cooldown_restante(user_id: int, guild_id: int, tipo_treino: str):
    jogador = obter_jogador(user_id, guild_id)
    if not jogador:
        return None
    config = CONFIG_TREINO["treinos"].get(tipo_treino)
    if not config:
        return None
    ultimo = jogador.get("ultimo_treino", {}).get(tipo_treino)
    if not ultimo:
        return 0
    horas_passadas = (datetime.datetime.utcnow() - datetime.datetime.fromisoformat(ultimo)).total_seconds() / 3600
    return max(0, config["cooldown_horas"] - horas_passadas)
