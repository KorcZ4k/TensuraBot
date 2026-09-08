import discord
from discord.ext import commands

from database.python.mongodb import db


class Recuperacao(commands.Cog):
    """Comandos de descanso e meditação para recuperar recursos separadamente."""

    def __init__(self, bot):
        self.bot = bot

    def _jogador(self, ctx):
        if db is None or not ctx.guild:
            return None
        return db["Jogadores"].find_one({"ID": str(ctx.author.id), "guild_id": str(ctx.guild.id)})

    def _salvar(self, ctx, vida, mana):
        db["Jogadores"].update_one(
            {"ID": str(ctx.author.id), "guild_id": str(ctx.guild.id)},
            {"$set": {"Vida": int(vida), "Mana": int(mana)}},
        )

    async def _recuperar(self, ctx, titulo):
        jogador = self._jogador(ctx)
        if not jogador:
            await ctx.send("❌ Você não possui um personagem registrado.")
            return

        vida_maxima = max(0, int(jogador.get("Vida_Maxima", jogador.get("Vida Maxima", 0)) or 0))
        mana_maxima = max(0, int(jogador.get("Mana Total", jogador.get("Mana_Maxima", 0)) or 0))
        vida_atual = max(0, int(jogador.get("Vida", 0) or 0))
        mana_atual = max(0, int(jogador.get("Mana", 0) or 0))

        # Os recursos são independentes: estar com Mana cheia não impede a
        # recuperação da Vida, e estar com Vida cheia não impede a da Mana.
        nova_vida = min(vida_maxima, vida_atual + max(1, vida_maxima // 2)) if vida_atual < vida_maxima else vida_atual
        nova_mana = min(mana_maxima, mana_atual + max(1, mana_maxima // 2)) if mana_atual < mana_maxima else mana_atual

        recuperou_vida = nova_vida - vida_atual
        recuperou_mana = nova_mana - mana_atual
        self._salvar(ctx, nova_vida, nova_mana)

        if recuperou_vida == 0 and recuperou_mana == 0:
            descricao = "✨ Você já está com Vida e Mana no máximo."
        else:
            descricao = (
                f"❤️ Vida: **+{recuperou_vida}** ({nova_vida}/{vida_maxima})\n"
                if recuperou_vida > 0 else f"❤️ Vida: **cheia** ({nova_vida}/{vida_maxima})\n"
            )
            descricao += (
                f"💙 Mana: **+{recuperou_mana}** ({nova_mana}/{mana_maxima})"
                if recuperou_mana > 0 else f"💙 Mana: **cheia** ({nova_mana}/{mana_maxima})"
            )

        embed = discord.Embed(title=titulo, description=descricao, color=discord.Color.green())
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        await ctx.send(embed=embed)

    @commands.command(name="descanso", aliases=["descansar", "rest"])
    async def descanso(self, ctx):
        await self._recuperar(ctx, "😴 Descanso")

    @commands.command(name="meditacao", aliases=["meditação", "meditar", "meditate"])
    async def meditacao(self, ctx):
        await self._recuperar(ctx, "🧘 Meditação")


async def setup(bot):
    await bot.add_cog(Recuperacao(bot))
