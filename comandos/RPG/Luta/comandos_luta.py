"""Comandos públicos do sistema de combate.

Este é o único ponto de registro dos comandos de luta. O motor fica em
``sistemas_luta`` e a apresentação em ``Mensagens_luta``.
"""

from __future__ import annotations

import re

from discord.ext import commands

from ..luta import (
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
from .sistemas_luta import Luta
from .Mensagens_luta import painel


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


_LUTA_COMANDOS = {
    "luta", "fight", "combate", "monstros", "pve", "pvp", "soco", "chute",
    "defesa", "defender", "def", "shield", "block", "bloquear", "bloqueio",
    "esquiva", "esquivar", "desviar", "dodge", "desvio", "fugir", "fuga",
    "escape", "escapar", "run", "matar", "desmaiar",
}
_SEND_ORIGINAL = commands.Context.send


def _dados_painel(ctx):
    cog = ctx.bot.get_cog("Luta")
    combate = cog._obter_combate(ctx.channel.id) if cog else None
    if not combate:
        return {}
    atacante = cog._obter_atacante(combate)
    ataque = combate.get("ataque_pendente") or {}
    defensor = cog._participante(combate, ataque.get("defensor_id")) if ataque else cog._obter_defensor(combate)
    return {
        "combate": combate,
        "atacante": atacante,
        "defensor": defensor,
        "turno": combate.get("numero_turno", 1),
        "ataque": ataque,
    }


async def _send_interface_luta(self, content=None, *, embed=None, **kwargs):
    """Força toda saída dos comandos de luta para o painel Moon Tensura."""
    comando = getattr(self.command, "name", "").casefold()
    parent = getattr(getattr(self.command, "parent", None), "name", "").casefold()
    if comando not in _LUTA_COMANDOS and parent not in {"luta", "fight", "combate"}:
        return await _SEND_ORIGINAL(self, content=content, embed=embed, **kwargs)

    dados = _dados_painel(self)
    atacante = dados.get("atacante") or {"nome": getattr(self.author, "display_name", "User"), "vida": 0, "mana": 0}
    defensor = dados.get("defensor") or {}
    texto = str(content or "")
    if embed is not None:
        texto = " ".join(filter(None, [embed.title or "", embed.description or ""]))
        for campo in embed.fields:
            texto += f" {campo.name}: {campo.value}"

    ataque_nome = dados.get("ataque", {}).get("nome") or comando or "Ataque"
    if comando == "soco":
        ataque_nome = "👊 Soco"
    elif comando == "chute":
        ataque_nome = "🦵 Chute"
    elif comando == "defesa":
        ataque_nome = "🛡️ Defesa"
    elif comando == "esquiva":
        ataque_nome = "💨 Esquiva"

    dano_match = re.search(r"\*\*(\d+)\s+de dano", texto, re.IGNORECASE)
    dano = dano_match.group(1) if dano_match else "-"
    efeito_match = re.search(r"Efeito:\s*\*\*([^*]+)", texto, re.IGNORECASE)
    efeito = efeito_match.group(1) if efeito_match else "Nenhum"
    if "esquivou" in texto.casefold():
        efeito = "Esquivou"
        dano = "0"

    panel = painel(
        atacante=atacante.get("nome", "User"),
        ataque=ataque_nome,
        vida=f"{max(0, int(float(atacante.get('vida', 0) or 0)))}/{max(1, int(float(atacante.get('vida_maxima', atacante.get('vida', 0)) or 1)))}",
        mana=int(float(atacante.get("mana", 0) or 0)),
        dano=dano,
        efeito=efeito,
        alvo=defensor.get("nome", "-"),
        turno=dados.get("turno", "-"),
        oponente=defensor.get("nome", "-"),
        vida_oponente=(
            f"{max(0, int(float(defensor.get('vida', 0) or 0)))}/{max(1, int(float(defensor.get('vida_maxima', defensor.get('vida', 0)) or 1)))}"
            if defensor else "-"
        ),
        extra=texto[:500] if texto and comando not in {"soco", "chute", "defesa", "esquiva"} else "",
    )
    return await _SEND_ORIGINAL(self, content=None, embed=panel, **kwargs)


# A camada visual fica aplicada apenas aos comandos de combate; comandos
# administrativos e demais módulos continuam usando o envio normal.
commands.Context.send = _send_interface_luta


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
