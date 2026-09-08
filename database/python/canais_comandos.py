import asyncio
import copy
from database.python.mongodb import db

_collection = db["guild_configs"]
_cache = {}


async def obter_canais_bloqueados(guild_id):
    if guild_id in _cache:
        return set(_cache[guild_id])
    config = await asyncio.to_thread(_collection.find_one, {"guild_id": guild_id}, {"canais_sem_comandos": 1})
    canais = {int(value) for value in (config or {}).get("canais_sem_comandos", [])}
    _cache[guild_id] = set(canais)
    return canais


async def definir_canais_bloqueados(guild_id, canais):
    ids = sorted({int(value) for value in canais})
    await asyncio.to_thread(
        _collection.update_one,
        {"guild_id": guild_id},
        {"$set": {"canais_sem_comandos": ids}},
        upsert=True,
    )
    _cache[guild_id] = set(ids)
    return set(ids)


async def canal_bloqueado(guild_id, canal_id):
    return int(canal_id) in await obter_canais_bloqueados(guild_id)
