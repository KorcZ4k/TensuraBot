"""Helpers assíncronos para operações de status do RPG.

O projeto usa PyMongo síncrono. Estas funções mantêm a lógica existente,
mas executam as operações de status fora do event loop do Discord.
"""

from database.python.mongodb import run_db
from database.python import status as status_db


def _recuperar_vida_apos_recuperacao(user_id: int, guild_id: int, percentual: float):
    jogador = status_db.jogadores.find_one({
        "ID": str(user_id),
        "guild_id": str(guild_id)
    })
    if not jogador or jogador.get("Situação") == "morto":
        return {"vida_recuperada": 0, "vida_atual": 0, "vida_maxima": 0}

    vida_atual = jogador.get("Vida", 0)
    vida_maxima = jogador.get("Vida_Maxima", 0)
    cura = max(0, int(vida_maxima * percentual))
    nova_vida = min(vida_maxima, vida_atual + cura)

    status_db.jogadores.update_one(
        {"ID": str(user_id), "guild_id": str(guild_id)},
        {"$set": {"Vida": nova_vida}}
    )

    return {
        "vida_recuperada": nova_vida - vida_atual,
        "vida_atual": nova_vida,
        "vida_maxima": vida_maxima,
    }


async def obter_status(user_id: int, guild_id: int):
    return await run_db(status_db.obter_status, user_id, guild_id)


async def obter_atributo(user_id: int, guild_id: int, atributo: str):
    return await run_db(status_db.obter_atributo, user_id, guild_id, atributo)


async def alterar_atributo(user_id: int, guild_id: int, atributo: str, valor: int):
    return await run_db(status_db.alterar_atributo, user_id, guild_id, atributo, valor)


async def aumentar_atributo(user_id: int, guild_id: int, atributo: str, quantidade: int):
    return await run_db(status_db.aumentar_atributo, user_id, guild_id, atributo, quantidade)


async def reduzir_atributo(user_id: int, guild_id: int, atributo: str, quantidade: int):
    return await run_db(status_db.reduzir_atributo, user_id, guild_id, atributo, quantidade)


async def adicionar_xp(user_id: int, guild_id: int, quantidade: int):
    return await run_db(status_db.adicionar_xp, user_id, guild_id, quantidade)


async def remover_xp(user_id: int, guild_id: int, quantidade: int):
    return await run_db(status_db.remover_xp, user_id, guild_id, quantidade)


async def alterar_nivel(user_id: int, guild_id: int, nivel: int):
    return await run_db(status_db.alterar_nivel, user_id, guild_id, nivel)


async def alterar_nome(user_id: int, guild_id: int, nome: str):
    return await run_db(status_db.alterar_nome, user_id, guild_id, nome)


async def alterar_raca(user_id: int, guild_id: int, raca: str):
    return await run_db(status_db.alterar_raca, user_id, guild_id, raca)


async def verificar_morte(user_id: int, guild_id: int):
    return await run_db(status_db.verificar_morte, user_id, guild_id)


async def reviver(user_id: int, guild_id: int):
    return await run_db(status_db.reviver, user_id, guild_id)


async def aplicar_dano(user_id: int, guild_id: int, dano: int):
    return await run_db(status_db.aplicar_dano, user_id, guild_id, dano)


async def aplicar_cura(user_id: int, guild_id: int, cura: int):
    return await run_db(status_db.aplicar_cura, user_id, guild_id, cura)


async def recuperar_mana(user_id: int, guild_id: int, tipo: str):
    """Recupera mana e vida usando o mesmo cooldown de descanso/meditação."""
    resultado = await run_db(status_db.recuperar_mana, user_id, guild_id, tipo)

    if not resultado.get("sucesso"):
        return resultado

    vida = await run_db(
        _recuperar_vida_apos_recuperacao,
        user_id,
        guild_id,
        resultado.get("percentual", 0) / 100,
    )
    resultado.update(vida)
    resultado["mensagem"] += (
        f"\n❤️ Vida recuperada: +{vida['vida_recuperada']} "
        f"({vida['vida_atual']}/{vida['vida_maxima']})"
    )
    return resultado


async def get_cooldown_recuperacao(user_id: str, guild_id: str, tipo: str):
    return await run_db(status_db.get_cooldown_recuperacao, user_id, guild_id, tipo)


async def esta_morto(user_id: int, guild_id: int):
    return await run_db(status_db.esta_morto, user_id, guild_id)
