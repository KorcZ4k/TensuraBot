"""Helpers assíncronos para operações de status do RPG.

O projeto usa PyMongo síncrono. Estas funções mantêm a lógica existente,
mas executam as operações de status fora do event loop do Discord.
"""

from database.python.mongodb import run_db
from database.python import status as status_db


async def obter_status(user_id: int, guild_id: int):
    """Obtém a ficha sem bloquear o event loop."""
    return await run_db(status_db.obter_status, user_id, guild_id)


async def obter_atributo(user_id: int, guild_id: int, atributo: str):
    """Obtém um atributo sem bloquear o event loop."""
    return await run_db(status_db.obter_atributo, user_id, guild_id, atributo)


async def alterar_atributo(user_id: int, guild_id: int, atributo: str, valor: int):
    """Altera um atributo sem bloquear o event loop."""
    return await run_db(status_db.alterar_atributo, user_id, guild_id, atributo, valor)


async def aumentar_atributo(user_id: int, guild_id: int, atributo: str, quantidade: int):
    """Aumenta um atributo sem bloquear o event loop."""
    return await run_db(status_db.aumentar_atributo, user_id, guild_id, atributo, quantidade)


async def reduzir_atributo(user_id: int, guild_id: int, atributo: str, quantidade: int):
    """Reduz um atributo sem bloquear o event loop."""
    return await run_db(status_db.reduzir_atributo, user_id, guild_id, atributo, quantidade)


async def adicionar_xp(user_id: int, guild_id: int, quantidade: int):
    """Adiciona XP sem bloquear o event loop."""
    return await run_db(status_db.adicionar_xp, user_id, guild_id, quantidade)


async def remover_xp(user_id: int, guild_id: int, quantidade: int):
    """Remove XP sem bloquear o event loop."""
    return await run_db(status_db.remover_xp, user_id, guild_id, quantidade)


async def alterar_nivel(user_id: int, guild_id: int, nivel: int):
    """Altera o nível sem bloquear o event loop."""
    return await run_db(status_db.alterar_nivel, user_id, guild_id, nivel)


async def alterar_nome(user_id: int, guild_id: int, nome: str):
    """Altera o nome sem bloquear o event loop."""
    return await run_db(status_db.alterar_nome, user_id, guild_id, nome)


async def alterar_raca(user_id: int, guild_id: int, raca: str):
    """Altera a raça sem bloquear o event loop."""
    return await run_db(status_db.alterar_raca, user_id, guild_id, raca)


async def verificar_morte(user_id: int, guild_id: int):
    """Verifica/aplica morte sem bloquear o event loop."""
    return await run_db(status_db.verificar_morte, user_id, guild_id)


async def reviver(user_id: int, guild_id: int):
    """Revive o personagem sem bloquear o event loop."""
    return await run_db(status_db.reviver, user_id, guild_id)


async def aplicar_dano(user_id: int, guild_id: int, dano: int):
    """Aplica dano sem bloquear o event loop."""
    return await run_db(status_db.aplicar_dano, user_id, guild_id, dano)


async def aplicar_cura(user_id: int, guild_id: int, cura: int):
    """Aplica cura sem bloquear o event loop."""
    return await run_db(status_db.aplicar_cura, user_id, guild_id, cura)


async def recuperar_mana(user_id: int, guild_id: int, quantidade: int):
    """Recupera mana sem bloquear o event loop."""
    return await run_db(status_db.recuperar_mana, user_id, guild_id, quantidade)


async def get_cooldown_recuperacao(user_id: str, guild_id: str, tipo: str):
    """Obtém cooldown de recuperação sem bloquear o event loop."""
    return await run_db(status_db.get_cooldown_recuperacao, user_id, guild_id, tipo)


async def esta_morto(user_id: int, guild_id: int):
    """Verifica se o personagem está morto sem bloquear o event loop."""
    return await run_db(status_db.esta_morto, user_id, guild_id)
