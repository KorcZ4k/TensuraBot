import asyncio
import copy
import os
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
    uri, tls=True, maxPoolSize=50, minPoolSize=1, maxIdleTimeMS=60000,
    serverSelectionTimeoutMS=10000, connectTimeoutMS=10000,
    socketTimeoutMS=20000, retryReads=True, retryWrites=True, appname="TensuraBot",
)
db = client[database_name]

try:
    client.admin.command("ping")
    print(f"MongoDB conectado! Database: {database_name}")
except Exception as e:
    print("ERRO AO CONECTAR AO MONGODB:")
    print(repr(e))
    raise

async def run_db(operation, *args, **kwargs):
    return await asyncio.to_thread(operation, *args, **kwargs)

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
