"""Facade assíncrona para operações de magias que acessam MongoDB."""

from database.python.mongodb import run_db
from database.python.magias import DatabaseMagias


async def get_magia_doc(db, user_id: str, guild_id: str):
    """Busca o documento de magias sem bloquear o event loop."""
    database = DatabaseMagias(db)
    return await run_db(database.get_magia_doc, user_id, guild_id)


async def criar_documento(db, user_id: str, guild_id: str, situacao="ativo"):
    database = DatabaseMagias(db)
    return await run_db(database.criar_documento, user_id, guild_id, situacao)


async def add_magia(db, user_id: str, guild_id: str, forma_id: str):
    database = DatabaseMagias(db)
    return await run_db(database.add_magia, user_id, guild_id, forma_id)


async def add_multiplas_magias(db, user_id: str, guild_id: str, formas):
    database = DatabaseMagias(db)
    return await run_db(database.add_multiplas_magias, user_id, guild_id, formas)


async def remove_magia(db, user_id: str, guild_id: str, forma_id: str):
    database = DatabaseMagias(db)
    return await run_db(database.remove_magia, user_id, guild_id, forma_id)


async def add_tipo(db, user_id: str, guild_id: str, elemento_id: str):
    database = DatabaseMagias(db)
    return await run_db(database.add_tipo, user_id, guild_id, elemento_id)


async def add_multiplos_tipos(db, user_id: str, guild_id: str, elementos):
    database = DatabaseMagias(db)
    return await run_db(database.add_multiplos_tipos, user_id, guild_id, elementos)


async def remove_tipo(db, user_id: str, guild_id: str, elemento_id: str):
    database = DatabaseMagias(db)
    return await run_db(database.remove_tipo, user_id, guild_id, elemento_id)


async def deletar_documento(db, user_id: str, guild_id: str):
    database = DatabaseMagias(db)
    return await run_db(database.deletar_documento, user_id, guild_id)
