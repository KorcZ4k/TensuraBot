import discord
from discord.ext import commands
from database.python.mongodb import run_db
from database.python.cooldowns import restante, iniciar, formatar

class CooldownsRPG(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.Cog.listener()
    async def on_command(self, ctx):
        if not ctx.guild or not ctx.command: return
        nome = getattr(ctx.command, "qualified_name", ctx.command.name)
        # Combate PVE: aplica cooldown somente quando o comando de início é executado.
        if nome in {"luta pve", "luta pve_monstro", "pve", "luta monstro"}:
            chave = "pve_monstros"
            r = await run_db(restante, ctx.author.id, ctx.guild.id, chave)
            if r > 0:
                raise commands.CommandError(f"⏳ PVE em recarga. Aguarde **{formatar(r)}**.")
            await run_db(iniciar, ctx.author.id, ctx.guild.id, chave, 3600)

async def setup(bot):
    await bot.add_cog(CooldownsRPG(bot))
