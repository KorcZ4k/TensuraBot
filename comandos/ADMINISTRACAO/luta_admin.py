import asyncio

import discord
from discord.ext import commands

from database.python.mongodb import db, run_db


class LutaAdmin(commands.Cog):
    """Comandos administrativos para manutenção dos combates."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="rluta")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def resetar_luta(self, ctx):
        """Reseta o combate ativo no canal atual."""
        luta = self.bot.get_cog("Luta")
        if luta is None:
            await ctx.send("❌ O sistema de luta não está carregado.")
            return

        combate = luta.combates.pop(ctx.channel.id, None)
        if not combate:
            await ctx.send("ℹ️ Não há combate ativo neste canal.")
            return

        guild_id = str(ctx.guild.id)
        tarefas = []
        for participante in combate.get("participantes", []):
            if participante.get("tipo") != "jogador":
                continue
            tarefas.append(run_db(
                db["Jogadores"].update_one,
                {"ID": str(participante["id"]), "guild_id": guild_id},
                {"$set": {"Situação": "ativo"}},
            ))
        if tarefas:
            await asyncio.gather(*tarefas)

        await ctx.send(embed=discord.Embed(
            title="🔄 Luta resetada",
            description=f"O combate deste canal foi encerrado por {ctx.author.mention}.",
            color=discord.Color.orange(),
        ))

    @resetar_luta.error
    async def resetar_luta_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Apenas administradores podem usar `!rluta`.")
        elif isinstance(error, commands.NoPrivateMessage):
            return


async def setup(bot):
    # O motor Luta antigo possui um rluta interno. Removemos esse registro
    # para que exista apenas a versão administrativa, protegida por permissão.
    bot.remove_command("rluta")
    await bot.add_cog(LutaAdmin(bot))
