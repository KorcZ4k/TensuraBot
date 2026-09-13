"""Comandos públicos do sistema de combate.

Este é o único ponto de registro dos comandos de luta. O motor fica em
``sistemas_luta`` e a apresentação em ``Mensagens_luta``.
"""

from __future__ import annotations

from discord.ext import commands

from ..luta import (
    Luta,
    _desmaiar as _legacy_desmaiar,
    _defesa as _legacy_defesa,
    _esquiva as _legacy_esquiva,
    _fugir as _legacy_fugir,
    _luta as _legacy_luta,
    _matar as _legacy_matar,
    _monstros as _legacy_monstros,
    _pve as _legacy_pve,
    _pvp as _legacy_pvp,
    _soco as _legacy_soco,
    _chute as _legacy_chute,
)


async def luta(ctx):
    await _legacy_luta(ctx)


async def monstros(ctx):
    await _legacy_monstros(ctx)


async def pve(ctx, *, monstro_tipo: str = ""):
    await _legacy_pve(ctx, monstro_tipo=monstro_tipo)


async def pvp(ctx, membro=None):
    await _legacy_pvp(ctx, membro)


async def soco(ctx):
    await _legacy_soco(ctx)


async def chute(ctx):
    await _legacy_chute(ctx)


async def defesa(ctx):
    await _legacy_defesa(ctx)


async def esquiva(ctx):
    await _legacy_esquiva(ctx)


async def fugir(ctx):
    await _legacy_fugir(ctx)


async def matar(ctx):
    await _legacy_matar(ctx)


async def desmaiar(ctx):
    await _legacy_desmaiar(ctx)


def _comando(callback, nome, **kwargs):
    return commands.Command(callback, name=nome, **kwargs)


async def setup(bot):
    """Carrega um único Cog de luta e registra todos os comandos aqui."""
    cog = bot.get_cog("Luta")
    if cog is None:
        cog = Luta(bot)
        await bot.add_cog(cog)

    nomes = (
        "luta", "fight", "combate", "soco", "chute", "defesa", "defender",
        "def", "shield", "block", "bloquear", "bloqueio", "esquiva", "esquivar",
        "desviar", "dodge", "desvio", "fugir", "fuga", "escape", "escapar", "run",
        "matar", "desmaiar",
    )
    for nome in nomes:
        bot.remove_command(nome)

    grupo = commands.Group(
        luta,
        name="luta",
        aliases=["fight", "combate"],
        invoke_without_command=True,
        help="Sistema de combate.",
    )
    grupo.add_command(_comando(monstros, "monstros", help="Lista os monstros disponíveis."))
    grupo.add_command(_comando(pve, "pve", help="Inicia um combate PvE."))
    grupo.add_command(_comando(pvp, "pvp", help="Inicia um combate PvP."))
    bot.add_command(grupo)

    comandos = (
        (soco, "soco", {}),
        (chute, "chute", {}),
        (defesa, "defesa", {"aliases": ["defender", "def", "shield", "block", "bloquear", "bloqueio"]}),
        (esquiva, "esquiva", {"aliases": ["esquivar", "desviar", "dodge", "desvio"]}),
        (fugir, "fugir", {"aliases": ["fuga", "escape", "escapar", "run"]}),
        (matar, "matar", {}),
        (desmaiar, "desmaiar", {}),
    )
    for callback, nome, opcoes in comandos:
        bot.add_command(_comando(callback, nome, **opcoes))

    comando_luta = bot.get_command("luta")
    print(
        "[LUTA][REGISTRO]",
        f"luta={bool(comando_luta)}",
        f"monstros={bool(comando_luta and comando_luta.get_command('monstros'))}",
        f"pve={bool(comando_luta and comando_luta.get_command('pve'))}",
        "origem=comandos.RPG.Luta.comandos_luta",
    )
