import discord
from discord.ext import commands
from database.python.mongodb import db


class Recuperacao(commands.Cog):
    """Descanso e meditação, ambos com cooldown individual de 30 minutos."""

    def __init__(self, bot):
        self.bot = bot

    def _jogador(self, ctx):
        return (
            db["Jogadores"].find_one(
                {"ID": str(ctx.author.id), "guild_id": str(ctx.guild.id)}
            )
            if db is not None and ctx.guild
            else None
        )

    async def _recuperar(self, ctx, tipo, titulo):
        from database.python import status_async

        resultado = await status_async.recuperar_mana(
            str(ctx.author.id), str(ctx.guild.id), tipo
        )
        if not resultado.get("sucesso"):
            await ctx.send(resultado["mensagem"])
            return

        embed = discord.Embed(
            title=titulo,
            description=resultado["mensagem"],
            color=discord.Color.green(),
        )
        embed.add_field(
            name="❤️ Vida",
            value=f"{resultado.get('vida_atual', 0)}/{resultado.get('vida_maxima', 0)}",
            inline=True,
        )
        embed.add_field(
            name="💧 Mana",
            value=f"{resultado.get('mana_atual', 0)}/{resultado.get('mana_maxima', 0)}",
            inline=True,
        )
        embed.add_field(name="⏰ Cooldown", value="30 minutos", inline=True)
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        await ctx.send(embed=embed)

    @commands.command(name="descanso", aliases=["descansar", "rest"])
    async def descanso(self, ctx):
        await self._recuperar(ctx, "descanso", "😴 Descanso")

    @commands.command(
        name="meditacao",
        aliases=["meditação", "meditar", "meditate"],
    )
    async def meditacao(self, ctx):
        await self._recuperar(ctx, "meditacao", "🧘 Meditação")


async def setup(bot):
    await bot.add_cog(Recuperacao(bot))
