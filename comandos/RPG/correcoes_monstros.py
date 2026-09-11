"""Correcoes de monstros e controle de cooldown do PvE."""

import discord
from discord.ext import commands

from database.python.luta import MONSTROS
from database.python import luta as luta_db


COOLDOWN_MONSTRO_HORAS = 6


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
        embed = discord.Embed(title="🐉 Monstros Disponíveis", color=discord.Color.dark_red())
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
    """Bloqueia o mesmo monstro por 6 horas para cada jogador."""

    async def _verificar_e_reservar(self, ctx):
        comando = getattr(ctx.command, "name", "").casefold()
        parent = getattr(ctx.command, "parent", None)
        if comando != "pve" or getattr(parent, "name", "").casefold() != "luta" or ctx.guild is None:
            return True

        monstro_tipo = ctx.kwargs.get("monstro_tipo")
        if not monstro_tipo:
            partes = str(getattr(getattr(ctx, "message", None), "content", "")).split()
            if len(partes) >= 3 and partes[0].casefold() == "!luta" and partes[1].casefold() == "pve":
                monstro_tipo = " ".join(partes[2:])

        luta = ctx.bot.get_cog("Luta")
        monstro_id = luta._encontrar_monstro(monstro_tipo) if luta and monstro_tipo else None
        if not monstro_id:
            return True

        # A reserva é feita antes da execução da luta. O filtro atômico no banco
        # impede duas chamadas simultâneas de iniciarem o mesmo monstro.
        reserva = await luta_db.run_db(
            luta_db.iniciar_cooldown_monstro,
            str(ctx.author.id),
            str(ctx.guild.id),
            str(monstro_id),
        )

        if not reserva.get("sucesso"):
            segundos = reserva.get("segundos_restantes", 0)
            nome = MONSTROS[monstro_id].get("nome", monstro_id)
            await ctx.send(
                f"⏳ Você já enfrentou **{nome}**. "
                f"Tente novamente em **{_formatar_tempo(segundos)}**."
            )
            return False

        # Força exatamente 6h, independentemente da configuração individual
        # encontrada no JSON, preservando a reserva criada por esta execução.
        fim = reserva.get("fim")
        if fim is not None and luta_db.db is not None:
            from datetime import datetime, timedelta, timezone

            agora = datetime.now(timezone.utc)
            fim_forcado = agora + timedelta(hours=COOLDOWN_MONSTRO_HORAS)
            campo = f"Cooldowns_Monstros.{str(monstro_id)}"
            await luta_db.run_db(
                luta_db.db["Jogadores"].update_one,
                {"ID": str(ctx.author.id), "guild_id": str(ctx.guild.id), campo: fim},
                {"$set": {campo: fim_forcado}},
            )
            fim = fim_forcado

        ctx._monstro_cooldown_reserva = (str(monstro_id), fim)
        return True

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        reserva = getattr(ctx, "_monstro_cooldown_reserva", None)
        if not reserva or ctx.guild is None:
            return

        monstro_id, fim = reserva
        await luta_db.run_db(
            luta_db.cancelar_cooldown_monstro,
            str(ctx.author.id),
            str(ctx.guild.id),
            monstro_id,
            fim,
        )

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        if hasattr(ctx, "_monstro_cooldown_reserva"):
            delattr(ctx, "_monstro_cooldown_reserva")


async def setup(bot):
    grupo = bot.get_command("luta")
    if grupo is None:
        raise RuntimeError("O comando !luta não foi encontrado para aplicar a correção.")

    comando = grupo.get_command("monstros")
    if comando is not None:
        comando.callback = _listar_monstros

    pve = grupo.get_command("pve")
    if pve is None:
        raise RuntimeError("O comando !luta pve não foi encontrado para aplicar o cooldown.")

    cog = CooldownMonstros(bot)
    await bot.add_cog(cog)
    pve.add_check(cog._verificar_e_reservar)
