"""Compatibilidade do sistema de luta.

O PvE continua sendo executado pelo callback original do Cog Luta.
O cooldown e reservado em um check do comando, sem substituir o callback.
"""

from database.python.mongodb import run_db
from database.python import luta as luta_db


async def setup(bot):
    async def verificar_cooldown_pve(ctx):
        comando = getattr(ctx, "command", None)
        parent = getattr(comando, "parent", None)
        if getattr(comando, "name", "") != "pve" or getattr(parent, "name", "") != "luta":
            return True
        if ctx.guild is None:
            return True

        luta = bot.get_cog("Luta")
        if luta is None or luta._combate_ativo(ctx.channel.id):
            return True

        monstro_tipo = getattr(getattr(comando, "params", {}).get("monstro_tipo"), "name", None)
        if not monstro_tipo:
            return True

        try:
            valor = ctx.kwargs.get("monstro_tipo")
        except AttributeError:
            valor = None
        if not valor:
            return True

        monstro_id = luta._encontrar_monstro(valor)
        if not monstro_id:
            return True

        guild_id = str(ctx.guild.id)
        verificacao = await run_db(luta_db.pode_lutar, str(ctx.author.id), guild_id)
        if not verificacao.get("pode"):
            await ctx.send(verificacao.get("mensagem", "❌ Você não pode lutar."))
            return False

        reserva = await run_db(
            luta_db.iniciar_cooldown_monstro,
            str(ctx.author.id), guild_id, str(monstro_id),
        )
        if reserva.get("sucesso"):
            return True

        segundos = int(reserva.get("segundos_restantes", 0) or 0)
        horas, resto = divmod(segundos, 3600)
        minutos = resto // 60
        restante = f"{horas}h {minutos}min" if horas > 0 else f"{max(1, minutos)}min"
        nome = luta_db.MONSTROS.get(str(monstro_id), {}).get("nome", valor)
        await ctx.send(f"⏳ Você já lutou contra **{nome}**. Tente novamente em **{restante}**.")
        return False

    bot.add_check(verificar_cooldown_pve)
