import discord
from discord.ext import commands

from database.python.canais_comandos import (
    obter_canais_bloqueados,
    definir_canais_bloqueados,
)


class CanaisComandos(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="bloquearcomandos", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def bloquearcomandos(self, ctx):
        """Gerencia canais onde comandos ficam bloqueados."""
        canais = await obter_canais_bloqueados(ctx.guild.id)
        mencoes = []
        for channel_id in sorted(canais):
            canal = ctx.guild.get_channel(channel_id)
            if canal is not None:
                mencoes.append(canal.mention)

        descricao = (
            "Nenhum canal está bloqueado."
            if not mencoes
            else "\n".join(f"• {canal}" for canal in mencoes)
        )
        embed = discord.Embed(
            title="🚫 | Canais sem comandos",
            description=descricao,
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="Comandos",
            value=(
                "`!bloquearcomandos adicionar #canal` — bloqueia comandos\n"
                "`!bloquearcomandos remover #canal` — libera comandos\n"
                "`!bloquearcomandos lista` — mostra os canais bloqueados"
            ),
            inline=False,
        )
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        await ctx.send(embed=embed)

    @bloquearcomandos.command(name="adicionar", aliases=["add"])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def adicionar(self, ctx, canal: discord.TextChannel):
        canais = await obter_canais_bloqueados(ctx.guild.id)
        if canal.id in canais:
            await ctx.send(f"⚠️ {canal.mention} já está bloqueado para comandos.")
            return

        canais.add(canal.id)
        await definir_canais_bloqueados(ctx.guild.id, canais)
        await ctx.send(f"🚫 Comandos bloqueados em {canal.mention}.")

    @bloquearcomandos.command(name="remover", aliases=["remove", "liberar"])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def remover(self, ctx, canal: discord.TextChannel):
        canais = await obter_canais_bloqueados(ctx.guild.id)
        if canal.id not in canais:
            await ctx.send(f"⚠️ {canal.mention} não está bloqueado para comandos.")
            return

        canais.remove(canal.id)
        await definir_canais_bloqueados(ctx.guild.id, canais)
        await ctx.send(f"✅ Comandos liberados em {canal.mention}.")

    @bloquearcomandos.command(name="lista", aliases=["list"])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def lista(self, ctx):
        await self.bloquearcomandos(ctx)


async def setup(bot):
    await bot.add_cog(CanaisComandos(bot))
