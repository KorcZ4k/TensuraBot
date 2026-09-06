import asyncio
from pymongo import UpdateOne
from database.python.mongodb import db, run_db


players = db["Jogadores"]
mora = db["Mora"]
inv = db["Inventários"]
mag = db["Magias"]
hab = db["Habilidades"]


def _build_cadastro_ops(membros):
    players_ops = []
    mora_ops = []
    inv_ops = []
    mag_ops = []
    hab_ops = []

    for member in membros:
        if member.bot:
            continue

        user_id = str(member.id)
        guild_id = str(member.guild.id)
        filtro = {"ID": user_id, "guild_id": guild_id}

        players_ops.append(UpdateOne(filtro, {"$setOnInsert": {
            "ID": user_id, "guild_id": guild_id,
            "Nome do Discord": member.display_name,
            "nome de usuario do disc": member.name,
            "Situação": "pendente", "Nome": None, "Raça": None,
            "Nivel": 1, "inteligencia": 0, "XP": 0, "XP_maximo": 100,
            "Vida": 100, "Vida_Maxima": 100, "Vitalidade": 0,
            "Mana": 100, "Mana Total": 100, "Magiculas": 0,
            "Força": 0, "Defesa": 0, "Velocidade": 0,
            "Destreza": 0, "Magia": 0, "Sorte": 0,
        }}, upsert=True))

        mora_ops.append(UpdateOne(filtro, {"$setOnInsert": {
            "Situação": "pendente", "ID": user_id, "guild_id": guild_id,
            "carteira": 0, "banco": 0,
        }}, upsert=True))

        inv_ops.append(UpdateOne(filtro, {"$setOnInsert": {
            "ID": user_id, "guild_id": guild_id, "Situação": "pendente",
            "itens": [],
        }}, upsert=True))

        mag_ops.append(UpdateOne(filtro, {"$setOnInsert": {
            "ID": user_id, "guild_id": guild_id, "Situação": "pendente",
            "tipos": [], "magias": [],
        }}, upsert=True))

        hab_ops.append(UpdateOne(filtro, {"$setOnInsert": {
            "ID": user_id, "guild_id": guild_id, "Situação": "pendente",
            "habilidades": [],
        }}, upsert=True))

    return (players_ops, mora_ops, inv_ops, mag_ops, hab_ops)


def cadastro(membros):
    """API síncrona legada; use cadastro_async no event loop do Discord."""
    ops = _build_cadastro_ops(membros)
    for collection, collection_ops in zip(
        (players, mora, inv, mag, hab), ops
    ):
        if collection_ops:
            collection.bulk_write(collection_ops)
    return len(ops[0])


async def cadastro_async(membros):
    """Cadastra usuários sem bloquear o event loop e em paralelo por coleção."""
    ops = _build_cadastro_ops(membros)
    tasks = [
        run_db(collection.bulk_write, collection_ops)
        for collection, collection_ops in zip(
            (players, mora, inv, mag, hab), ops
        )
        if collection_ops
    ]
    if tasks:
        await asyncio.gather(*tasks)
    return len(ops[0])
