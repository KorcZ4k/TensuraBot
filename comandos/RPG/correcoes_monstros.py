"""Correcoes de monstros e controle de cooldown do PvE."""

import discord
from discord.ext import commands

from database.python.luta import MONSTROS
from database.python import luta as luta_db


def _formatar_tempo(segundos):
    segundos = max(0, int(segundos or 0))
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    if horas:
        return f"{horas}h {minutos:02d}min"
    if minutos:
        return f"{minutos}min {segundos:02d}s"
    return f"{segundos}s"


async def _listar_monstros(self, ctx):
    if not MONSTROS:
        await ctx.send("❌ Nenhum monstro foi carregado.")
        return

    itens = list(MONSTROS.items())
    total_paginas = (len(itens) + 24) // 25
    for inicio in range(0, len(itens), 25):
        pagina = inicio // 25 + 1
        embed = discord.Embed(
            title="🐉 Monstros Disponíveis",
            color=discord.Color.dark_red(),
        )
        for monstro_id, dados in itens[inicio:inicio + 25]:
            embed.add_field(
                name=f"{dados.get('emoji', '👹')} {dados.get('nome', monstro_id)}",
                value=(
                    f"ID: `{monstro_id}`\n"
                    f"❤️ Vida: {dados.get('vida_base', 0)}\n"
                    f"⚔️ Dano: {dados.get('dano_base', 0)}\n"
                    f"✨ XP: {dados.get('xp_recompensa', 0)}\n"
                    f"💰 Hunos: {dados.get('hunos_recompensa', 0)}\n"
                    f"⏱️ Cooldown: **6h**"
                ),
                inline=True,
            )
        embed.set_footer(text=f"Página {pagina}/{total_paginas} • Use !luta pve <id> para iniciar")
        await ctx.send(embed=embed)


class CooldownMonstros(commands.Cog):
    """Impede repeticao do mesmo monstro antes de 6 horas."""

    async def _verificar_e_reservar(self, ctx):
        if getattr(ctx.command, "name", "").casefold() != "pve":
            return True
        parent = getattr(ctx.command, "parent", None)
        if getattr(parent, "name", "").casefold() != "luta":
            return True
        monstro_tipo = ctx.kwargs.get("monstro_tipo")
        luta = ctx.bot.get_cog("Luta")
        monstro_id = luta._encontrar_monstro(monstro_tipo) if luta else None
        if not monstro_id:
            return True

        verificacao = luta_db.verificar_cooldown_monstro(
            str(ctx.author.id), str(ctx.guild.id), monstro_id
        )
        if not verificacao["disponivel"]:
            await ctx.send(
                f"⏳ Você já enfrentou **{MONSTROS[monstro_id].get('nome', monstro_id)}**. "
                f"Tente novamente em **{_formatar_tempo(verificacao['segundos_restantes'])}**."
            )
            return False

        reserva = luta_db.iniciar_cooldown_monstro(
            str(ctx.author.id), str(ctx.guild.id), monstro_id
        )
        if not reserva["sucesso"]:
            await ctx.send(
                f"⏳ Você já enfrentou **{MONSTROS[monstro_id].get('nome', monstro_id)}**. "
                f"Tente novamente em **{_formatar_tempo(reserva['segundos_restantes'])}**."
            )
            return False
        ctx._monstro_cooldown_reserva = (str(monstro_id), reserva["fim"])
        return True

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        reserva = getattr(ctx, "_monstro_cooldown_reserva", None)
        if not reserva:
            return
        monstro_id, fim = reserva
        await luta_db.cancelar_cooldown_monstro(
            str(ctx.author.id), str(ctx.guild.id), monstro_id, fim
        )

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        if hasattr(ctx, "_monstro_cooldown_reserva"):
            delattr(ctx, "_monstro_cooldown_reserva")


async def setup(bot):
    grupo = bot.get_command("luta")
    comando = grupo.get_command("monstros") if grupo is not None else None
    if comando is None:
        raise RuntimeError("O comando !luta monstros não foi encontrado para aplicar a correção.")
    comando.callback = _listar_monstros

    pve = grupo.get_command("pve") if grupo is not None else None
    if pve is None:
        raise RuntimeError("O comando !luta pve não foi encontrado para aplicar o cooldown.")

    cog = CooldownMonstros(bot)
    await bot.add_cog(cog)
    pve.add_check(cog._verificar_e_reservar)
