import discord
from discord.ext import commands
from database.python.mongodb import run_db
from database.python.treino import listar_treinos_disponiveis, get_cooldown_restante, obter_jogador, realizar_treino, CONFIG_TREINO


class Treino(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="treino", aliases=["treinar"], invoke_without_command=True)
    async def treino(self, ctx):
        embed = discord.Embed(title="💪 Sistema de Treino", description="Treine para ganhar Pontos de Treinamento (TP).", color=discord.Color.blue())
        treinos = await run_db(listar_treinos_disponiveis, str(ctx.author.id), str(ctx.guild.id))
        texto = ""
        for treino in treinos:
            cooldown = await run_db(get_cooldown_restante, str(ctx.author.id), str(ctx.guild.id), treino["tipo"])
            status = "✅ Disponível" if cooldown == 0 else f"⏰ {int(cooldown)}h restantes"
            faixa = f"+{treino['tp_minimo']} TP" if treino['tp_minimo'] == treino['tp_maximo'] else f"+{treino['tp_minimo']}–{treino['tp_maximo']} TP"
            texto += f"{treino['emoji']} **{treino['nome']}** - Nv. {treino['nivel_minimo']}+ - {faixa} - {status}\n"
        embed.add_field(name="📋 Treinos Disponíveis", value=texto or "Nenhum treino disponível.", inline=False)
        embed.add_field(name="📖 Comandos", value="`!treino leve` • `!treino medio` • `!treino pesado` • `!treino supremo`\n`!treino info` • `!treino cooldown`", inline=False)
        await ctx.send(embed=embed)

    @treino.command(name="leve")
    async def treino_leve(self, ctx): await self._executar_treino(ctx, "leve")

    @treino.command(name="medio")
    async def treino_medio(self, ctx): await self._executar_treino(ctx, "medio")

    @treino.command(name="pesado")
    async def treino_pesado(self, ctx): await self._executar_treino(ctx, "pesado")

    @treino.command(name="supremo")
    async def treino_supremo(self, ctx): await self._executar_treino(ctx, "supremo")

    async def _executar_treino(self, ctx, tipo):
        resultado = await run_db(realizar_treino, str(ctx.author.id), str(ctx.guild.id), tipo)
        if not resultado["sucesso"]:
            await ctx.send(resultado["mensagem"])
            return
        config = CONFIG_TREINO["treinos"][tipo]
        embed = discord.Embed(title=f"{config['emoji']} Treino concluído", description=resultado["mensagem"], color=discord.Color.green())
        embed.add_field(name="✨ TP ganho", value=f"**+{resultado['tp_ganho']} TP**", inline=True)
        embed.add_field(name="✨ TP total", value=f"**{resultado['tp_atual']} TP**", inline=True)
        embed.add_field(name="⏰ Cooldown", value=f"{config['cooldown_horas']} horas", inline=True)
        embed.set_footer(text="Use !aumentar <atributo> para gastar seus TP.")
        await ctx.send(embed=embed)

    @treino.command(name="info")
    async def treino_info(self, ctx):
        jogador = await run_db(obter_jogador, str(ctx.author.id), str(ctx.guild.id))
        nivel = jogador.get("Nivel", 1) if jogador else 1
        embed = discord.Embed(title="📖 Informações dos Treinos", color=discord.Color.blue())
        for tipo, config in CONFIG_TREINO["treinos"].items():
            pode = nivel >= config["nivel_minimo"]
            status = "✅ Disponível" if pode else f"❌ Nv. {config['nivel_minimo']} necessário"
            minimo = config.get("tp_minimo", 100)
            maximo = config.get("tp_maximo", minimo)
            faixa = f"+{minimo} TP" if minimo == maximo else f"+{minimo}–{maximo} TP"
            embed.add_field(name=f"{config['emoji']} {config['nome']}", value=f"**Nível mínimo:** {config['nivel_minimo']}\n**Cooldown:** {config['cooldown_horas']}h\n**TP:** {faixa}\n**Status:** {status}", inline=False)
        await ctx.send(embed=embed)

    @treino.command(name="cooldown")
    async def treino_cooldown(self, ctx):
        embed = discord.Embed(title="⏰ Cooldowns de Treino", color=discord.Color.blue())
        for tipo, config in CONFIG_TREINO["treinos"].items():
            cooldown = await run_db(get_cooldown_restante, str(ctx.author.id), str(ctx.guild.id), tipo)
            status = "✅ Disponível" if cooldown == 0 else (f"⏰ {int(cooldown * 60)} minutos" if cooldown < 1 else f"⏰ {int(cooldown)} horas")
            embed.add_field(name=f"{config['emoji']} {config['nome']}", value=status, inline=True)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Treino(bot))
