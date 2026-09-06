import asyncio
import discord
from discord.ext import commands
from database.python.mongodb import run_db
from database.python.treino import (
    realizar_treino,
    listar_treinos_disponiveis,
    get_cooldown_restante,
    CONFIG_TREINO
)


class Treino(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="treino", aliases=["treinar"], invoke_without_command=True)
    async def treino(self, ctx):
        """Comando principal de treino"""
        embed = discord.Embed(
            title="💪 Sistema de Treino",
            description="Treine para aumentar seus atributos!",
            color=discord.Color.blue()
        )

        treinos = await run_db(
            listar_treinos_disponiveis,
            str(ctx.author.id),
            str(ctx.guild.id)
        )

        if not treinos:
            embed.add_field(
                name="❌ Nenhum treino disponível",
                value="Você não tem nível suficiente para nenhum treino.",
                inline=False
            )
        else:
            texto = ""
            for treino in treinos:
                cooldown = await run_db(
                    get_cooldown_restante,
                    str(ctx.author.id),
                    str(ctx.guild.id),
                    treino["tipo"]
                )

                if cooldown == 0:
                    status = "✅ Disponível"
                else:
                    status = f"⏰ {int(cooldown)}h restantes"

                texto += f"{treino['emoji']} **{treino['nome']}** - Nv. {treino['nivel_minimo']}+ - {status}\n"

            embed.add_field(
                name="📋 Treinos Disponíveis",
                value=texto,
                inline=False
            )

        embed.add_field(
            name="📖 Comandos",
            value=(
                "`!treino leve` - Treino Leve (Nv. 1+)\n"
                "`!treino medio` - Treino Médio (Nv. 10+)\n"
                "`!treino pesado` - Treino Pesado (Nv. 20+)\n"
                "`!treino supremo` - Treino Supremo (Nv. 50+)\n"
                "`!treino info` - Ver detalhes dos treinos\n"
                "`!treino cooldown` - Ver seus cooldowns"
            ),
            inline=False
        )

        await ctx.send(embed=embed)

    @treino.command(name="leve")
    async def treino_leve(self, ctx):
        await self._executar_treino(ctx, "leve")

    @treino.command(name="medio")
    async def treino_medio(self, ctx):
        await self._executar_treino(ctx, "medio")

    @treino.command(name="pesado")
    async def treino_pesado(self, ctx):
        await self._executar_treino(ctx, "pesado")

    @treino.command(name="supremo")
    async def treino_supremo(self, ctx):
        await self._executar_treino(ctx, "supremo")

    async def _executar_treino(self, ctx, tipo: str):
        """Executa o fluxo completo de treino fora do event loop."""
        resultado = await run_db(
            realizar_treino,
            str(ctx.author.id),
            str(ctx.guild.id),
            tipo
        )

        if not resultado["sucesso"]:
            await ctx.send(resultado["mensagem"])
            return

        treino_config = CONFIG_TREINO["treinos"][tipo]
        embed = discord.Embed(
            title=f"{treino_config['emoji']} {resultado['mensagem']}",
            description="Seus atributos aumentaram!",
            color=discord.Color.green()
        )

        texto_aumentos = ""
        for atributo, aumento in resultado["aumentos"].items():
            novo_valor = resultado["novos_valores"][atributo]
            texto_aumentos += f"• **{atributo}:** +{aumento:.2f} → {novo_valor:.1f}\n"

        embed.add_field(
            name="📈 Aumentos",
            value=texto_aumentos,
            inline=False
        )
        embed.add_field(
            name="⏰ Cooldown",
            value=f"{treino_config['cooldown_horas']} horas",
            inline=True
        )
        embed.set_footer(text="Volte depois do cooldown para treinar novamente!")
        await ctx.send(embed=embed)

    @treino.command(name="info")
    async def treino_info(self, ctx):
        embed = discord.Embed(
            title="📖 Informações dos Treinos",
            description="Detalhes de cada tipo de treino",
            color=discord.Color.blue()
        )

        jogador = await run_db(
            __import__("database.python.treino", fromlist=["obter_jogador"]).obter_jogador,
            str(ctx.author.id),
            str(ctx.guild.id)
        )
        nivel = jogador.get("Nivel", 1) if jogador else 1

        for tipo, config in CONFIG_TREINO["treinos"].items():
            pode = nivel >= config["nivel_minimo"]
            status = "✅ Disponível" if pode else f"❌ Nv. {config['nivel_minimo']} necessário"

            if config["min_aumento"] == config["max_aumento"]:
                aumento_texto = f"{config['min_aumento']:.2f}"
            else:
                aumento_texto = f"{config['min_aumento']:.2f} - {config['max_aumento']:.2f}"

            embed.add_field(
                name=f"{config['emoji']} {config['nome']}",
                value=(
                    f"**Nível mínimo:** {config['nivel_minimo']}\n"
                    f"**Cooldown:** {config['cooldown_horas']} horas\n"
                    f"**Aumento:** {aumento_texto} por atributo\n"
                    f"**Status:** {status}\n"
                    f"*{config.get('descricao', '')}*"
                ),
                inline=False
            )

        await ctx.send(embed=embed)

    @treino.command(name="cooldown")
    async def treino_cooldown(self, ctx):
        embed = discord.Embed(
            title="⏰ Cooldowns de Treino",
            description="Tempo restante para cada treino",
            color=discord.Color.blue()
        )

        for tipo, config in CONFIG_TREINO["treinos"].items():
            cooldown = await run_db(
                get_cooldown_restante,
                str(ctx.author.id),
                str(ctx.guild.id),
                tipo
            )

            if cooldown == 0:
                status = "✅ Disponível"
            elif cooldown < 1:
                status = f"⏰ {int(cooldown * 60)} minutos"
            else:
                status = f"⏰ {int(cooldown)} horas"

            embed.add_field(
                name=f"{config['emoji']} {config['nome']}",
                value=status,
                inline=True
            )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Treino(bot))
