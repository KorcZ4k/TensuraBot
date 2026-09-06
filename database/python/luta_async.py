"""Facade assíncrona para operações de combate que acessam MongoDB.

Mantém a implementação síncrona existente em ``luta.py`` intacta e
executa somente as operações potencialmente bloqueantes em worker threads.
As funções puramente computacionais continuam no módulo original.
"""

from database.python.mongodb import run_db
from database.python import luta as luta_db


async def obter_jogador(user_id: str, guild_id: str):
    return await run_db(luta_db.obter_jogador, user_id, guild_id)


async def criar_participante_jogador(user_id: str, guild_id: str):
    return await run_db(
        luta_db.criar_participante_jogador,
        user_id,
        guild_id,
    )


async def pode_lutar(user_id: str, guild_id: str):
    return await run_db(luta_db.pode_lutar, user_id, guild_id)


async def finalizar_combate(combate):
    return await run_db(luta_db.finalizar_combate, combate)
