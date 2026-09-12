"""Correcoes de compatibilidade do sistema de luta.

Mantem as regras principais no Cog Luta e corrige o fluxo de inicio de PvE:
o cooldown do monstro precisa ser reservado atomicamente antes de criar o combate.
"""

from database.python.mongodb import run_db
from database.python import luta as luta_db


async def setup(bot):
    luta = bot.get_cog("Luta")
    if luta is None:
        return

    comando_luta = bot.get_command("luta")
    comando_pve = comando_luta.get_command("pve") if comando_luta else None
    if comando_pve is None:
        return

    callback_original = comando_pve.callback
    if getattr(callback_original, "_cooldown_monstro_corrigido", False):
        return

    async def pve_com_cooldown(self, ctx, *, monstro_tipo: str):
        if not ctx.guild or self._combate_ativo(ctx.channel.id):
            return await callback_original(self, ctx, monstro_tipo=monstro_tipo)

        guild_id = str(ctx.guild.id)
        monstro_id = self._encontrar_monstro(monstro_tipo)
        if not monstro_id:
            return await callback_original(self, ctx, monstro_tipo=monstro_tipo)

        verificacao = await run_db(luta_db.pode_lutar, str(ctx.author.id), guild_id)
        if not verificacao.get("pode"):
            return await callback_original(self, ctx, monstro_tipo=monstro_tipo)

        reserva = await run_db(
            luta_db.iniciar_cooldown_monstro,
            str(ctx.author.id), guild_id, str(monstro_id),
        )
        if not reserva.get("sucesso"):
            segundos = int(reserva.get("segundos_restantes", 0) or 0)
            horas, resto = divmod(segundos, 3600)
            minutos = resto // 60
            restante = f"{horas}h {minutos}min" if horas > 0 else f"{max(1, minutos)}min"
            nome = luta_db.MONSTROS.get(str(monstro_id), {}).get("nome", monstro_tipo)
            await ctx.send(f"⏳ Você já lutou contra **{nome}**. Tente novamente em **{restante}**.")
            return

        fim = reserva.get("fim")
        try:
            await callback_original(self, ctx, monstro_tipo=monstro_tipo)
        except Exception:
            await run_db(luta_db.cancelar_cooldown_monstro, str(ctx.author.id), guild_id, str(monstro_id), fim)
            raise

        # O callback original pode recusar a criacao sem levantar excecao.
        # Nesse caso, desfazemos apenas a reserva criada por esta tentativa.
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await run_db(luta_db.cancelar_cooldown_monstro, str(ctx.author.id), guild_id, str(monstro_id), fim)

    pve_com_cooldown._cooldown_monstro_corrigido = True
    comando_pve.callback = pve_com_cooldown
