"""Compatibilidade do sistema de luta.

O PvE continua usando o callback original do Cog Luta.
O cooldown e aplicado como before_invoke do proprio comando, depois que
o discord.py ja resolveu e validou os argumentos do comando.
"""

from discord.ext import commands

from database.python.mongodb import run_db
from database.python import luta as luta_db


async def setup(bot):
    luta = bot.get_cog("Luta")
    if luta is None:
        raise RuntimeError("Cog Luta precisa estar carregado antes de correcoes_luta.")

    comando_luta = bot.get_command("luta")
    if comando_luta is None:
        raise RuntimeError("Comando !luta nao foi registrado.")

    comando_pve = comando_luta.get_command("pve")
    if comando_pve is None:
        raise RuntimeError("Subcomando !luta pve nao foi registrado.")

    async def verificar_cooldown_pve(ctx):
        # Esta mensagem acontece depois do parser do discord.py e antes do acesso
        # ao MongoDB. Assim, se o banco travar ou o callback falhar, o usuario
        # ainda recebe uma confirmacao de que !luta pve foi realmente reconhecido.
        await ctx.send("⚔️ Iniciando combate PvE...")

        if ctx.guild is None or luta._combate_ativo(ctx.channel.id):
            return

        monstro_tipo = ctx.kwargs.get("monstro_tipo")
        if not monstro_tipo:
            return

        monstro_id = luta._encontrar_monstro(monstro_tipo)
        if not monstro_id:
            return

        guild_id = str(ctx.guild.id)
        verificacao = await run_db(
            luta_db.pode_lutar,
            str(ctx.author.id),
            guild_id,
        )
        if not verificacao.get("pode"):
            await ctx.send(verificacao.get("mensagem", "❌ Você não pode lutar."))
            raise commands.CommandError("PvE bloqueado pela validação do jogador.")

        reserva = await run_db(
            luta_db.iniciar_cooldown_monstro,
            str(ctx.author.id),
            guild_id,
            str(monstro_id),
        )
        if reserva.get("sucesso"):
            return

        segundos = int(reserva.get("segundos_restantes", 0) or 0)
        horas, resto = divmod(segundos, 3600)
        minutos = resto // 60
        restante = f"{horas}h {minutos}min" if horas > 0 else f"{max(1, minutos)}min"
        nome = luta_db.MONSTROS.get(str(monstro_id), {}).get("nome", monstro_tipo)
        await ctx.send(f"⏳ Você já lutou contra **{nome}**. Tente novamente em **{restante}**.")
        raise commands.CommandError("Cooldown PvE ativo.")

    comando_pve.before_invoke = verificar_cooldown_pve
