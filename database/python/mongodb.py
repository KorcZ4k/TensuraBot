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
