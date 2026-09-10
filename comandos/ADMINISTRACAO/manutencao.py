import discord
from discord.ext import commands

MENSAGEM_MANUTENCAO = "O bot está em manutenção nesse momento, aguarde até ser reativado."


class Manutencao(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.em_manutencao = False

    @commands.command(name="manutencao")
    @commands.has_guild_permissions(administrator=True)
    @commands.guild_only()
    async def manutencao(self, ctx):
        self.bot.em_manutencao = not getattr(self.bot, "em_manutencao", False)
        estado = "ativada" if self.bot.em_manutencao else "desativada"
        if self.bot.em_manutencao:
            embed = discord.Embed(
                title="🔧 Manutenção",
                description=MENSAGEM_MANUTENCAO,
                color=discord.Color.orange(),
            )
        else:
            embed = discord.Embed(
                title="✅ Manutenção encerrada",
                description="O bot foi reativado e os comandos estão disponíveis novamente.",
                color=discord.Color.green(),
            )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Manutencao(bot))
