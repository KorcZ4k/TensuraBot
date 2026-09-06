import discord
from discord.ext import commands


class Loritta(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sistemas")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def sistema(self, ctx):
        guild_icon = ctx.guild.icon.url if ctx.guild.icon else None
        embed = discord.Embed(
            title="Tensura Moon",
            description="Painel de sistemas do bot.",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        if guild_icon:
            embed.set_thumbnail(url=guild_icon)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Loritta(bot))
