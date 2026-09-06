import asyncio
import copy
import logging
import os
import time
from collections import Counter
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
uri = os.getenv("MONGODB_URI")
database_name = os.getenv("MONGODB_DATABASE")
if not uri:
    raise RuntimeError("MONGODB_URI não encontrada no .env")
if not database_name:
    raise RuntimeError("MONGODB_DATABASE não encontrada no .env")

client = MongoClient(
    uri, tls=True, maxPoolSize=50, maxIdleTimeMS=60000,
    serverSelectionTimeoutMS=5000, connectTimeoutMS=5000,
    socketTimeoutMS=10000, retryReads=True, retryWrites=True, appname="TensuraBot",
)
db = client[database_name]

logger = logging.getLogger("tensurabot.mongodb")
_PERF_ENABLED = os.getenv("MONGO_PERF_LOG", "0") == "1"
_DB_STATS = Counter()


async def run_db(operation, *args, **kwargs):
    """Executa uma operação síncrona do Mongo fora do event loop."""
    if not _PERF_ENABLED:
        return await asyncio.to_thread(operation, *args, **kwargs)

    started = time.perf_counter()
    operation_name = getattr(operation, "__qualname__", repr(operation))
    try:
        result = await asyncio.to_thread(operation, *args, **kwargs)
    except Exception:
        elapsed_ms = (time.perf_counter() - started) * 1000
        _DB_STATS["errors"] += 1
        logger.warning("MongoDB erro em %s (%.1f ms)", operation_name, elapsed_ms)
        raise
    else:
        elapsed_ms = (time.perf_counter() - started) * 1000
        _DB_STATS["calls"] += 1
        _DB_STATS["total_ms"] += elapsed_ms
        if elapsed_ms >= 250:
            _DB_STATS["slow_calls"] += 1
        logger.info("MongoDB %s (%.1f ms)", operation_name, elapsed_ms)
        return result


async def get_db_stats():
    stats = dict(_DB_STATS)
    calls = stats.get("calls", 0)
    stats["avg_ms"] = (stats.get("total_ms", 0.0) / calls) if calls else 0.0
    return stats


async def reset_db_stats():
    _DB_STATS.clear()


async def mongo_healthcheck():
    await run_db(client.admin.command, "ping")
    return True


async def close_db():
    await run_db(client.close)


async def mongo_find_one(collection, query, projection=None):
    return await run_db(collection.find_one, query, projection)


async def mongo_update_one(collection, query, update, *, upsert=False):
    return await run_db(collection.update_one, query, update, upsert=upsert)


_CONFIG_CACHE = {}


async def get_guild_config(collection, guild_id):
    cached = _CONFIG_CACHE.get(guild_id)
    if cached is not None:
        return copy.deepcopy(cached)
    config = await mongo_find_one(collection, {"guild_id": guild_id}) or {"guild_id": guild_id}
    _CONFIG_CACHE[guild_id] = copy.deepcopy(config)
    return copy.deepcopy(config)


async def update_guild_config(collection, guild_id, data):
    result = await mongo_update_one(collection, {"guild_id": guild_id}, {"$set": data}, upsert=True)
    cached = _CONFIG_CACHE.get(guild_id, {"guild_id": guild_id})
    cached.update(copy.deepcopy(data))
    cached["guild_id"] = guild_id
    _CONFIG_CACHE[guild_id] = cached
    return result


async def invalidate_guild_config(guild_id):
    _CONFIG_CACHE.pop(guild_id, None)
