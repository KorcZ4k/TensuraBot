"""Compatibilidade do sistema de luta.

O discord.py injeta a instancia do Cog como primeiro argumento dos callbacks
registrados em um Cog. Este modulo envolve os subcomandos de luta com
callbacks que preservam explicitamente essa assinatura.
"""

from discord.ext import commands

from database.python.mongodb import run_db
from database.python import luta as luta_db


async def setup(bot):
    luta = bot.get_cog("Luta")
    if luta is None:
        raise RuntimeError("Cog Luta precisa estar carregado antes de correcoes_luta.")

    grupo = bot.get_command("luta")
    if grupo is None:
        raise RuntimeError("Comando !luta nao foi registrado.")

    pve = grupo.get_command("pve")
    monstros = grupo.get_command("monstros")
    if pve is None:
        raise RuntimeError("Subcomando !luta pve nao foi registrado.")
    if monstros is None:
        raise RuntimeError("Subcomando !luta monstros nao foi registrado.")

    callback_pve_original = pve.callback
    callback_monstros_original = monstros.callback

    async def pve_callback(cog, ctx, *, monstro_tipo: str):
        # Assinatura completa: discord.py fornece (Cog, Context, argumentos).
        await ctx.send("⚔️ Iniciando combate PvE...")

        if ctx.guild is None or cog._combate_ativo(ctx.channel.id):
            return await callback_pve_original(cog, ctx, monstro_tipo=monstro_tipo)

        monstro_id = cog._encontrar_monstro(monstro_tipo)
        if not monstro_id:
            return await callback_pve_original(cog, ctx, monstro_tipo=monstro_tipo)

        guild_id = str(ctx.guild.id)
        verificacao = await run_db(
            luta_db.pode_lutar,
            str(ctx.author.id),
            guild_id,
        )
        if not verificacao.get("pode"):
            await ctx.send(verificacao.get("mensagem", "❌ Você não pode lutar."))
            return

        reserva = await run_db(
            luta_db.iniciar_cooldown_monstro,
            str(ctx.author.id),
            guild_id,
            str(monstro_id),
        )
        if not reserva.get("sucesso"):
            segundos = int(reserva.get("segundos_restantes", 0) or 0)
            horas, resto = divmod(segundos, 3600)
            minutos = resto // 60
            restante = f"{horas}h {minutos}min" if horas > 0 else f"{max(1, minutos)}min"
            nome = luta_db.MONSTROS.get(str(monstro_id), {}).get("nome", monstro_tipo)
            await ctx.send(f"⏳ Você já lutou contra **{nome}**. Tente novamente em **{restante}**.")
            return

        return await callback_pve_original(cog, ctx, monstro_tipo=monstro_tipo)

    async def monstros_callback(cog, ctx):
        # Mesmo tratamento para !luta monstros: preserva explicitamente ctx.
        return await callback_monstros_original(cog, ctx)

    pve.callback = pve_callback
    monstros.callback = monstros_callback
