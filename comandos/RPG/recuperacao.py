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
        return db["Jogadores"].find_one({
            "ID": str(ctx.author.id),
            "guild_id": str(ctx.guild.id),
        })

    def _salvar(self, ctx, vida, mana):
        db["Jogadores"].update_one(
            {"ID": str(ctx.author.id), "guild_id": str(ctx.guild.id)},
            {"$set": {"Vida": int(vida), "Mana": int(mana)}},
        )

    async def _recuperar(self, ctx, recuperar_vida=False, recuperar_mana=False, titulo="Recuperação"):
        jogador = self._jogador(ctx)
        if not jogador:
            await ctx.send("❌ Você não possui um personagem registrado.")
            return

        vida_maxima = max(0, int(jogador.get("Vida_Maxima", jogador.get("Vida Maxima", 0)) or 0))
        mana_maxima = max(0, int(jogador.get("Mana Total", jogador.get("Mana_Maxima", 0)) or 0))
        vida_atual = max(0, int(jogador.get("Vida", 0) or 0))
        mana_atual = max(0, int(jogador.get("Mana", 0) or 0))

        # Cada ação recupera 50% do recurso correspondente. Recursos já cheios
        # não bloqueiam a recuperação do outro recurso.
        nova_vida = min(vida_maxima, vida_atual + max(1, vida_maxima // 2)) if recuperar_vida else vida_atual
        nova_mana = min(mana_maxima, mana_atual + max(1, mana_maxima // 2)) if recuperar_mana else mana_atual

        recuperou_vida = nova_vida - vida_atual
        recuperou_mana = nova_mana - mana_atual

        self._salvar(ctx, nova_vida, nova_mana)

        if recuperou_vida == 0 and recuperou_mana == 0:
            descricao = "✨ Você já está com todos os recursos desta ação no máximo."
        else:
            linhas = []
            if recuperar_vida:
                linhas.append(f"❤️ Vida: **+{recuperou_vida}** ({nova_vida}/{vida_maxima})")
            if recuperar_mana:
                linhas.append(f"💙 Mana: **+{recuperou_mana}** ({nova_mana}/{mana_maxima})")
            descricao = "\n".join(linhas)

        embed = discord.Embed(title=titulo, description=descricao, color=discord.Color.green())
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        await ctx.send(embed=embed)

    @commands.command(name="descanso", aliases=["descansar", "rest"])
    async def descanso(self, ctx):
        # Descanso sempre tenta recuperar vida e mana; se um deles estiver cheio,
        # o outro continua sendo recuperado normalmente.
        await self._recuperar(ctx, recuperar_vida=True, recuperar_mana=True, titulo="😴 Descanso")

    @commands.command(name="meditacao", aliases=["meditação", "meditar", "meditate"])
    async def meditacao(self, ctx):
        # Meditação recupera mana sem impedir que a ação seja executada quando
        # a mana já estiver cheia. Vida baixa permanece intacta nesta ação.
        await self._recuperar(ctx, recuperar_vida=False, recuperar_mana=True, titulo="🧘 Meditação")


async def setup(bot):
    await bot.add_cog(Recuperacao(bot))
