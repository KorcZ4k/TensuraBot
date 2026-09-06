import asyncio
import discord
from discord.ext import commands

from database.python.Mora import (
    obter_mora, adicionar_mora, remover_mora, depositar_mora,
    sacar_mora, pagar_mora, ranking_mora,
)


class Mora(commands.Cog):
    """Economia simples de Mora, no estilo de comandos básicos do UnbelievaBot."""

    def __init__(self, bot): self.bot = bot

    def _embed(self, title, description=None, color=None):
        return discord.Embed(title=title, description=description, color=color or discord.Color.blurple(), timestamp=discord.utils.utcnow())

    async def _db(self, funcao, *args):
        return await asyncio.to_thread(funcao, *args)

    @commands.command(name="msaldo")
    async def msaldo(self, ctx):
        jogador = await self._db(obter_mora, ctx.author.id, ctx.guild.id)
        carteira, banco = jogador.get("carteira", 0), jogador.get("banco", 0)
        embed = self._embed(f"💰 Saldo de {ctx.author.display_name}", "Saldo de Mora", discord.Color.green())
        embed.add_field(name="💵 Carteira", value=f"**{carteira:,} Mora**", inline=True)
        embed.add_field(name="🏦 Banco", value=f"**{banco:,} Mora**", inline=True)
        embed.add_field(name="💎 Total", value=f"**{carteira + banco:,} Mora**", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="mpagar")
    async def mpagar(self, ctx, membro: discord.Member, quantidade: int):
        if quantidade <= 0: return await ctx.send("❌ A quantidade deve ser maior que zero.")
        if membro.bot: return await ctx.send("❌ Você não pode transferir Mora para um bot.")
        if membro.id == ctx.author.id: return await ctx.send("❌ Você não pode transferir Mora para si mesmo.")
        try: await self._db(pagar_mora, ctx.author.id, membro.id, ctx.guild.id, quantidade)
        except ValueError as erro: return await ctx.send(f"❌ {erro}")
        await ctx.send(f"✅ {ctx.author.mention} pagou **{quantidade:,} Mora** para {membro.mention}.")

    @commands.command(name="mdepositar")
    async def mdepositar(self, ctx, quantidade: int):
        if quantidade <= 0: return await ctx.send("❌ A quantidade deve ser maior que zero.")
        try: saldo = await self._db(depositar_mora, ctx.author.id, ctx.guild.id, quantidade)
        except ValueError as erro: return await ctx.send(f"❌ {erro}")
        await ctx.send(f"🏦 Depósito realizado: **{quantidade:,} Mora**\nCarteira: **{saldo['carteira']:,}** | Banco: **{saldo['banco']:,}**")

    @commands.command(name="msacar")
    async def msacar(self, ctx, quantidade: int):
        if quantidade <= 0: return await ctx.send("❌ A quantidade deve ser maior que zero.")
        try: saldo = await self._db(sacar_mora, ctx.author.id, ctx.guild.id, quantidade)
        except ValueError as erro: return await ctx.send(f"❌ {erro}")
        await ctx.send(f"🏦 Saque realizado: **{quantidade:,} Mora**\nCarteira: **{saldo['carteira']:,}** | Banco: **{saldo['banco']:,}**")

    @commands.command(name="mranking")
    async def mranking(self, ctx):
        jogadores = await self._db(ranking_mora, ctx.guild.id, 10)
        if not jogadores: return await ctx.send("Ainda não existem jogadores no ranking de Mora.")
        linhas = []
        for posicao, jogador in enumerate(jogadores, 1):
            total = jogador.get("carteira", 0) + jogador.get("banco", 0)
            membro = ctx.guild.get_member(int(jogador["ID"]))
            nome = membro.display_name if membro else f"Usuário {jogador['ID']}"
            linhas.append(f"**{posicao}.** {nome} — **{total:,} Mora**")
        await ctx.send(embed=self._embed("🏆 Ranking de Mora", "\n".join(linhas), discord.Color.gold()))

    @commands.command(name="madicionar-mora")
    @commands.has_permissions(administrator=True)
    async def adicionar_mora_cmd(self, ctx, membro: discord.Member, quantidade: int):
        if quantidade <= 0: return await ctx.send("❌ A quantidade deve ser maior que zero.")
        try: saldo = await self._db(adicionar_mora, membro.id, ctx.guild.id, quantidade)
        except ValueError as erro: return await ctx.send(f"❌ {erro}")
        await ctx.send(f"✅ Adicionados **{quantidade:,} Mora** para {membro.mention}. Carteira: **{saldo:,}**.")

    @commands.command(name="mremover-mora")
    @commands.has_permissions(administrator=True)
    async def remover_mora_cmd(self, ctx, membro: discord.Member, quantidade: int):
        if quantidade <= 0: return await ctx.send("❌ A quantidade deve ser maior que zero.")
        try: saldo = await self._db(remover_mora, membro.id, ctx.guild.id, quantidade)
        except ValueError as erro: return await ctx.send(f"❌ {erro}")
        await ctx.send(f"✅ Removidos **{quantidade:,} Mora** de {membro.mention}. Carteira: **{saldo:,}**.")


async def setup(bot):
    await bot.add_cog(Mora(bot))
