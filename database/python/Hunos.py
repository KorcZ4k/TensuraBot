import random
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

from database.python.mongodb import db, client

hunos = db["Hunos"]
FUSO = timezone(timedelta(hours=-3))


def _filtro(user_id, guild_id):
    return {"ID": str(user_id), "guild_id": str(guild_id)}


def obter_hunos(user_id, guild_id):
    jogador = hunos.find_one(_filtro(user_id, guild_id))
    if jogador is None:
        return {"carteira": 0, "banco": 0}
    return {"carteira": int(jogador.get("carteira", 0) or 0), "banco": int(jogador.get("banco", 0) or 0)}


def _garantir_conta(user_id, guild_id):
    return hunos.find_one_and_update(
        _filtro(user_id, guild_id),
        {"$setOnInsert": {"ID": str(user_id), "guild_id": str(guild_id), "carteira": 0, "banco": 0}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )


def adicionar_hunos(user_id, guild_id, quantidade):
    quantidade = int(quantidade)
    if quantidade <= 0:
        raise ValueError("A quantidade deve ser maior que zero.")
    _garantir_conta(user_id, guild_id)
    resultado = hunos.find_one_and_update(
        _filtro(user_id, guild_id), {"$inc": {"carteira": quantidade}}, return_document=ReturnDocument.AFTER
    )
    return int(resultado.get("carteira", 0))


def remover_hunos(user_id, guild_id, quantidade):
    quantidade = int(quantidade)
    if quantidade <= 0:
        raise ValueError("A quantidade deve ser maior que zero.")
    resultado = hunos.find_one_and_update(
        {**_filtro(user_id, guild_id), "carteira": {"$gte": quantidade}},
        {"$inc": {"carteira": -quantidade}}, return_document=ReturnDocument.AFTER
    )
    if resultado is None:
        raise ValueError("Hunos insuficientes na carteira.")
    return int(resultado.get("carteira", 0))


def depositar_hunos(user_id, guild_id, quantidade=None):
    conta = _garantir_conta(user_id, guild_id)
    carteira = int(conta.get("carteira", 0) or 0)
    if quantidade is None:
        quantidade = carteira
    quantidade = int(quantidade)
    if quantidade <= 0:
        raise ValueError("Você não possui Hunos na carteira para depositar.")
    resultado = hunos.find_one_and_update(
        {**_filtro(user_id, guild_id), "carteira": {"$gte": quantidade}},
        {"$inc": {"carteira": -quantidade, "banco": quantidade}}, return_document=ReturnDocument.AFTER
    )
    if resultado is None:
        raise ValueError("Hunos insuficientes na carteira.")
    return {"carteira": int(resultado.get("carteira", 0)), "banco": int(resultado.get("banco", 0))}


def sacar_hunos(user_id, guild_id, quantidade=None):
    conta = _garantir_conta(user_id, guild_id)
    banco = int(conta.get("banco", 0) or 0)
    if quantidade is None:
        quantidade = banco
    quantidade = int(quantidade)
    if quantidade <= 0:
        raise ValueError("Você não possui Hunos no banco para sacar.")
    resultado = hunos.find_one_and_update(
        {**_filtro(user_id, guild_id), "banco": {"$gte": quantidade}},
        {"$inc": {"banco": -quantidade, "carteira": quantidade}}, return_document=ReturnDocument.AFTER
    )
    if resultado is None:
        raise ValueError("Hunos insuficientes no banco.")
    return {"carteira": int(resultado.get("carteira", 0)), "banco": int(resultado.get("banco", 0))}


def pagar_hunos(remetente_id, destinatario_id, guild_id, quantidade):
    quantidade = int(quantidade)
    if quantidade <= 0:
        raise ValueError("A quantidade deve ser maior que zero.")
    if str(remetente_id) == str(destinatario_id):
        raise ValueError("Você não pode pagar a si mesmo.")

    sender_query = {**_filtro(remetente_id, guild_id), "carteira": {"$gte": quantidade}}
    recipient_query = _filtro(destinatario_id, guild_id)
    try:
        with client.start_session() as session:
            with session.start_transaction():
                resultado = hunos.update_one(sender_query, {"$inc": {"carteira": -quantidade}}, session=session)
                if resultado.modified_count != 1:
                    raise ValueError("Hunos insuficientes na carteira.")
                hunos.update_one(
                    recipient_query,
                    {"$setOnInsert": {"ID": str(destinatario_id), "guild_id": str(guild_id), "banco": 0}, "$inc": {"carteira": quantidade}},
                    upsert=True,
                    session=session,
                )
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError("Não foi possível concluir o pagamento com segurança.") from exc
    return True


def _cooldown_pronto(conta, campo, horas):
    agora = datetime.now(FUSO)
    ultimo = conta.get(campo)
    if ultimo is None:
        return True, 0
    if isinstance(ultimo, datetime):
        if ultimo.tzinfo is None:
            ultimo = ultimo.replace(tzinfo=FUSO)
        proximo = ultimo + timedelta(hours=horas)
        restante = (proximo - agora).total_seconds()
        return restante <= 0, max(0, int(restante))
    return True, 0


def trabalhar_hunos(user_id, guild_id):
    conta = _garantir_conta(user_id, guild_id)
    pronto, restante = _cooldown_pronto(conta, "ultimo_trabalho", 1)
    if not pronto:
        raise ValueError(f"Você precisa esperar **{restante // 60 + 1} minutos** para trabalhar novamente.")
    ganho = random.randint(100, 500)
    resultado = hunos.find_one_and_update(
        _filtro(user_id, guild_id),
        {"$inc": {"carteira": ganho}, "$set": {"ultimo_trabalho": datetime.now(FUSO)}},
        return_document=ReturnDocument.AFTER,
    )
    return {"ganho": ganho, "carteira": int(resultado.get("carteira", 0))}


def cometer_crime(user_id, guild_id):
    conta = _garantir_conta(user_id, guild_id)
    pronto, restante = _cooldown_pronto(conta, "ultimo_crime", 2)
    if not pronto:
        raise ValueError(f"Você precisa esperar **{restante // 60 + 1} minutos** para cometer outro crime.")

    sucesso = random.random() < 0.55
    if sucesso:
        ganho = random.randint(250, 1200)
        resultado = hunos.find_one_and_update(
            _filtro(user_id, guild_id),
            {"$inc": {"carteira": ganho}, "$set": {"ultimo_crime": datetime.now(FUSO)}},
            return_document=ReturnDocument.AFTER,
        )
        return {"sucesso": True, "valor": ganho, "carteira": int(resultado.get("carteira", 0))}

    carteira = int(conta.get("carteira", 0) or 0)
    perda = min(carteira, random.randint(100, 600))
    resultado = hunos.find_one_and_update(
        _filtro(user_id, guild_id),
        {"$inc": {"carteira": -perda}, "$set": {"ultimo_crime": datetime.now(FUSO)}},
        return_document=ReturnDocument.AFTER,
    )
    return {"sucesso": False, "valor": perda, "carteira": int(resultado.get("carteira", 0))}


def ranking_hunos(guild_id, limite=10):
    return list(hunos.find({"guild_id": str(guild_id)}).sort([("carteira", -1), ("banco", -1)]).limit(limite))
