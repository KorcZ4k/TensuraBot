import asyncio
import discord
from discord.ext import commands

from database.python.Hunos import (
    obter_hunos,
    adicionar_hunos,
    remover_hunos,
    depositar_hunos,
    sacar_hunos,
    pagar_hunos,
    ranking_hunos,
)


class Hunos(commands.Cog):
    """Economia simples de Hunos, no estilo de comandos básicos do UnbelievaBot."""

    def __init__(self, bot):
        self.bot = bot

    def _embed(self, title, description=None, color=None):
        return discord.Embed(title=title, description=description, color=color or discord.Color.blurple(), timestamp=discord.utils.utcnow())

    async def _db(self, funcao, *args):
        """Executa chamadas síncronas do PyMongo fora do event loop do Discord."""
        return await asyncio.to_thread(funcao, *args)

    @commands.command(name="saldo")
    async def saldo(self, ctx):
        jogador = await self._db(obter_hunos, ctx.author.id, ctx.guild.id)
        carteira = jogador.get("carteira", 0)
        banco = jogador.get("banco", 0)
        total = carteira + banco
        embed = self._embed(f"💰 Saldo de {ctx.author.display_name}", "Saldo de Hunos", discord.Color.green())
        embed.add_field(name="💵 Carteira", value=f"**{carteira:,} Hunos**", inline=True)
        embed.add_field(name="🏦 Banco", value=f"**{banco:,} Hunos**", inline=True)
        embed.add_field(name="💎 Total", value=f"**{total:,} Hunos**", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="pagar")
    async def pagar(self, ctx, membro: discord.Member, quantidade: int):
        if quantidade <= 0: return await ctx.send("❌ A quantidade deve ser maior que zero.")
        if membro.bot: return await ctx.send("❌ Você não pode transferir Hunos para um bot.")
        if membro.id == ctx.author.id: return await ctx.send("❌ Você não pode transferir Hunos para si mesmo.")
        try:
            await self._db(pagar_hunos, ctx.author.id, membro.id, ctx.guild.id, quantidade)
        except ValueError as erro:
            return await ctx.send(f"❌ {erro}")
        await ctx.send(f"✅ {ctx.author.mention} pagou **{quantidade:,} Hunos** para {membro.mention}.")

    @commands.command(name="depositar")
    async def depositar(self, ctx, quantidade: int):
        if quantidade <= 0: return await ctx.send("❌ A quantidade deve ser maior que zero.")
        try:
            saldo = await self._db(depositar_hunos, ctx.author.id, ctx.guild.id, quantidade)
        except ValueError as erro:
            return await ctx.send(f"❌ {erro}")
        await ctx.send(f"🏦 Depósito realizado: **{quantidade:,} Hunos**\nCarteira: **{saldo['carteira']:,}** | Banco: **{saldo['banco']:,}**")

    @commands.command(name="sacar")
    async def sacar(self, ctx, quantidade: int):
        if quantidade <= 0: return await ctx.send("❌ A quantidade deve ser maior que zero.")
        try:
            saldo = await self._db(sacar_hunos, ctx.author.id, ctx.guild.id, quantidade)
        except ValueError as erro:
            return await ctx.send(f"❌ {erro}")
        await ctx.send(f"🏦 Saque realizado: **{quantidade:,} Hunos**\nCarteira: **{saldo['carteira']:,}** | Banco: **{saldo['banco']:,}**")

    @commands.command(name="ranking")
    async def ranking(self, ctx):
        jogadores = await self._db(ranking_hunos, ctx.guild.id, 10)
        if not jogadores: return await ctx.send("Ainda não existem jogadores no ranking de Hunos.")
        linhas = []
        for posicao, jogador in enumerate(jogadores, 1):
            total = jogador.get("carteira", 0) + jogador.get("banco", 0)
            membro = ctx.guild.get_member(int(jogador["ID"]))
            nome = membro.display_name if membro else f"Usuário {jogador['ID']}"
            linhas.append(f"**{posicao}.** {nome} — **{total:,} Hunos**")
        await ctx.send(embed=self._embed("🏆 Ranking de Hunos", "\n".join(linhas), discord.Color.gold()))

    @commands.command(name="adicionar-hunos")
    @commands.has_permissions(administrator=True)
    async def adicionar_hunos_cmd(self, ctx, membro: discord.Member, quantidade: int):
        if quantidade <= 0: return await ctx.send("❌ A quantidade deve ser maior que zero.")
        try: saldo = await self._db(adicionar_hunos, membro.id, ctx.guild.id, quantidade)
        except ValueError as erro: return await ctx.send(f"❌ {erro}")
        await ctx.send(f"✅ Adicionados **{quantidade:,} Hunos** para {membro.mention}. Carteira: **{saldo:,}**.")

    @commands.command(name="remover-hunos")
    @commands.has_permissions(administrator=True)
    async def remover_hunos_cmd(self, ctx, membro: discord.Member, quantidade: int):
        if quantidade <= 0: return await ctx.send("❌ A quantidade deve ser maior que zero.")
        try: saldo = await self._db(remover_hunos, membro.id, ctx.guild.id, quantidade)
        except ValueError as erro: return await ctx.send(f"❌ {erro}")
        await ctx.send(f"✅ Removidos **{quantidade:,} Hunos** de {membro.mention}. Carteira: **{saldo:,}**.")


async def setup(bot):
    await bot.add_cog(Hunos(bot))
