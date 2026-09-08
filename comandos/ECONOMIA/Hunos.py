import asyncio

import discord
from discord.ext import commands

from database.python.Hunos import (
    obter_hunos, pagar_hunos, depositar_hunos, sacar_hunos,
    trabalhar_hunos, cometer_crime, adicionar_hunos, remover_hunos,
    ranking_hunos,
)


class Hunos(commands.Cog):
    """Economia de Hunos, separada da economia de Mora."""

    def __init__(self, bot):
        self.bot = bot

    async def _db(self, funcao, *args):
        return await asyncio.to_thread(funcao, *args)

    @commands.command(name="saldo", aliases=["hunos", "hunosaldo"])
    @commands.guild_only()
    async def saldo(self, ctx):
        saldo = await self._db(obter_hunos, ctx.author.id, ctx.guild.id)
        carteira, banco = saldo["carteira"], saldo["banco"]
        embed = discord.Embed(
            title=f"💰 Saldo de {ctx.author.display_name}",
            description="Economia em **Hunos**",
            color=discord.Color.green(), timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="💵 Carteira", value=f"**{carteira:,} Hunos**", inline=True)
        embed.add_field(name="🏦 Banco", value=f"**{banco:,} Hunos**", inline=True)
        embed.add_field(name="💎 Total", value=f"**{carteira + banco:,} Hunos**", inline=False)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="pagar", aliases=["pay", "transferir"])
    @commands.guild_only()
    async def pagar(self, ctx, membro: discord.Member, quantidade: int):
        if membro.bot:
            return await ctx.send("❌ Você não pode transferir Hunos para um bot.")
        if membro.id == ctx.author.id:
            return await ctx.send("❌ Você não pode pagar a si mesmo.")
        if quantidade <= 0:
            return await ctx.send("❌ A quantidade deve ser maior que zero.")
        try:
            await self._db(pagar_hunos, ctx.author.id, membro.id, ctx.guild.id, quantidade)
        except (ValueError, RuntimeError) as erro:
            return await ctx.send(f"❌ {erro}")
        await ctx.send(f"✅ {ctx.author.mention} pagou **{quantidade:,} Hunos** para {membro.mention}.")

    @commands.command(name="depositar", aliases=["dep", "deposit"])
    @commands.guild_only()
    async def depositar(self, ctx, quantidade: str = "tudo"):
        try:
            valor = None if quantidade.casefold() in {"tudo", "all", "tudo!"} else int(quantidade)
            saldo = await self._db(depositar_hunos, ctx.author.id, ctx.guild.id, valor)
        except ValueError as erro:
            return await ctx.send(f"❌ {erro}")
        texto = "todo o saldo da carteira" if valor is None else f"**{valor:,} Hunos**"
        await ctx.send(f"🏦 Você depositou {texto}.\n💵 Carteira: **{saldo['carteira']:,}** | 🏦 Banco: **{saldo['banco']:,}**")

    @commands.command(name="sacar", aliases=["saque", "withdraw"])
    @commands.guild_only()
    async def sacar(self, ctx, quantidade: str = "tudo"):
        try:
            valor = None if quantidade.casefold() in {"tudo", "all", "tudo!"} else int(quantidade)
            saldo = await self._db(sacar_hunos, ctx.author.id, ctx.guild.id, valor)
        except ValueError as erro:
            return await ctx.send(f"❌ {erro}")
        texto = "todo o saldo do banco" if valor is None else f"**{valor:,} Hunos**"
        await ctx.send(f"💵 Você sacou {texto}.\n💵 Carteira: **{saldo['carteira']:,}** | 🏦 Banco: **{saldo['banco']:,}**")

    @commands.command(name="trabalhar", aliases=["work", "trabalho"])
    @commands.guild_only()
    async def trabalhar(self, ctx):
        try:
            resultado = await self._db(trabalhar_hunos, ctx.author.id, ctx.guild.id)
        except ValueError as erro:
            return await ctx.send(f"❌ {erro}")
        await ctx.send(
            f"💼 {ctx.author.mention} trabalhou e recebeu **{resultado['ganho']:,} Hunos**!\n"
            f"💰 Carteira: **{resultado['carteira']:,} Hunos**"
        )

    @commands.command(name="crime", aliases=["criminoso", "crimehunos"])
    @commands.guild_only()
    async def crime(self, ctx):
        try:
            resultado = await self._db(cometer_crime, ctx.author.id, ctx.guild.id)
        except ValueError as erro:
            return await ctx.send(f"❌ {erro}")
        if resultado["sucesso"]:
            await ctx.send(
                f"🕵️ {ctx.author.mention} o crime deu certo! Você ganhou **{resultado['valor']:,} Hunos**.\n"
                f"💰 Carteira: **{resultado['carteira']:,} Hunos**"
            )
        else:
            await ctx.send(
                f"🚨 {ctx.author.mention} você foi pego! Perdeu **{resultado['valor']:,} Hunos**.\n"
                f"💰 Carteira: **{resultado['carteira']:,} Hunos**"
            )

    @commands.command(name="rankinghunos", aliases=["top", "top-hunos"])
    @commands.guild_only()
    async def ranking(self, ctx):
        jogadores = await self._db(ranking_hunos, ctx.guild.id, 10)
        if not jogadores:
            return await ctx.send("Ainda não existem jogadores no ranking de Hunos.")
        linhas = []
        for posicao, jogador in enumerate(jogadores, 1):
            total = int(jogador.get("carteira", 0) or 0) + int(jogador.get("banco", 0) or 0)
            membro = ctx.guild.get_member(int(jogador["ID"]))
            nome = membro.display_name if membro else f"Usuário {jogador['ID']}"
            linhas.append(f"**{posicao}.** {nome} — **{total:,} Hunos**")
        embed = discord.Embed(title="🏆 Ranking de Hunos", description="\n".join(linhas), color=discord.Color.gold(), timestamp=discord.utils.utcnow())
        await ctx.send(embed=embed)

    @commands.command(name="adicionar-hunos")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def admin_adicionar(self, ctx, membro: discord.Member, quantidade: int):
        if quantidade <= 0:
            return await ctx.send("❌ A quantidade deve ser maior que zero.")
        try:
            saldo = await self._db(adicionar_hunos, membro.id, ctx.guild.id, quantidade)
        except ValueError as erro:
            return await ctx.send(f"❌ {erro}")
        await ctx.send(f"✅ Adicionados **{quantidade:,} Hunos** para {membro.mention}. Carteira: **{saldo:,} Hunos**.")

    @commands.command(name="remover-hunos")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def admin_remover(self, ctx, membro: discord.Member, quantidade: int):
        if quantidade <= 0:
            return await ctx.send("❌ A quantidade deve ser maior que zero.")
        try:
            saldo = await self._db(remover_hunos, membro.id, ctx.guild.id, quantidade)
        except ValueError as erro:
            return await ctx.send(f"❌ {erro}")
        await ctx.send(f"✅ Removidos **{quantidade:,} Hunos** de {membro.mention}. Carteira: **{saldo:,} Hunos**.")


async def setup(bot):
    await bot.add_cog(Hunos(bot))
