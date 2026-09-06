import asyncio
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

# Um único cliente compartilhado mantém o pool de conexões entre os comandos.
client = MongoClient(
    uri,
    tls=True,
    maxPoolSize=50,
    minPoolSize=1,
    maxIdleTimeMS=60000,
    serverSelectionTimeoutMS=10000,
    connectTimeoutMS=10000,
    socketTimeoutMS=20000,
    retryReads=True,
    retryWrites=True,
    appname="TensuraBot",
)

db = client[database_name]

# Força uma verificação real. O código anterior imprimia "conectado" sem testar a conexão.
try:
    client.admin.command("ping")
    print(f"MongoDB conectado! Database: {database_name}")
except Exception as e:
    print("ERRO AO CONECTAR AO MONGODB:")
    print(repr(e))
    raise


async def run_db(operation, *args, **kwargs):
    """Executa uma operação PyMongo síncrona fora do event loop do Discord."""
    return await asyncio.to_thread(operation, *args, **kwargs)


async def mongo_find_one(collection, query, projection=None):
    """Consulta um documento sem bloquear o event loop."""
    return await run_db(collection.find_one, query, projection)


async def mongo_update_one(collection, query, update, *, upsert=False):
    """Atualiza um documento sem bloquear o event loop."""
    return await run_db(collection.update_one, query, update, upsert=upsert)
