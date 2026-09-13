"""Habilidades raciais usadas durante o combate."""
from __future__ import annotations

import unicodedata

import discord
from discord.ext import commands

from database.python.mongodb import db, run_db


def _normalizar(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or "")).casefold()
    return "".join(c for c in texto if not unicodedata.combining(c)).strip()


def _eh_draconico(raca: object) -> bool:
    """Aceita Dragão/Dragão Verdadeiro e híbridos que tenham Dragão como componente."""
    nome = _normalizar(raca)
    if nome in {"dragao", "dragao verdadeiro"}:
        return True
    return "dragao" in nome and (nome.startswith("hibrido ") or nome.startswith("meio-"))


async def _garras(ctx):
    if ctx.guild is None:
        await ctx.send("❌ O comando `!garras` só funciona em servidor.")
        return

    if db is None:
        await ctx.send("❌ O banco de dados não está disponível no momento.")
        return

    jogador = await run_db(
        db["Jogadores"].find_one,
        {"ID": str(ctx.author.id), "guild_id": str(ctx.guild.id)},
    )
    if not jogador:
        await ctx.send("❌ Você precisa ter um personagem registrado para usar `!garras`.")
        return

    raca = jogador.get("Raça", "")
    if not _eh_draconico(raca):
        await ctx.send("🐉❌ Apenas **Dragões** e **híbridos de Dragão** podem usar `!garras`.")
        return

    luta = ctx.bot.get_cog("Luta")
    if luta is None:
        await ctx.send("❌ O sistema de combate não foi carregado.")
        return

    combate = luta._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo"):
        await ctx.send("❌ Não há combate ativo.")
        return
    if combate.get("aguardando_finalizacao"):
        await ctx.send("❌ O combate aguarda a finalização PvP.")
        return
    if combate.get("fase") != "ataque":
        await ctx.send("❌ O ataque anterior ainda não foi defendido.")
        return

    atacante = luta._obter_atacante(combate)
    defensor = luta._obter_defensor(combate)
    if not atacante or not defensor:
        await ctx.send("❌ Não foi possível encontrar atacante e alvo.")
        return
    if atacante.get("tipo") != "jogador" or str(atacante.get("id")) != str(ctx.author.id):
        await ctx.send(f"❌ É a vez de **{atacante.get('nome', 'outro jogador')}**.")
        return

    # Garras são um ataque físico natural: não dependem de arma e recebem
    # um bônus fixo de dano para representar o poder racial do ataque.
    dano_base = 20
    ataque = luta._criar_ataque(
        combate,
        "garras",
        atacante,
        defensor,
        nome="🐉 Garras",
        dano_base=dano_base,
        com_arma=False,
    )
    await luta._anunciar_ataque(ctx)


class Garras(commands.Cog):
    """Comando racial de combate para Dragões e híbridos de Dragão."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="garras", aliases=["garra"])
    async def garras(self, ctx):
        luta = ctx.bot.get_cog("Luta")
        if luta is None:
            await _garras(ctx)
            return
        async with luta._lock(ctx.channel.id):
            await _garras(ctx)


async def setup(bot):
    await bot.add_cog(Garras(bot))
    print("[GARRAS][OK] Comando !garras carregado para Dragões e híbridos de Dragão.")
