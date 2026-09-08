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

        # Vida e Mana são independentes: um recurso cheio não bloqueia o outro.
        nova_vida = min(vida_maxima, vida_atual + max(1, vida_maxima // 2)) if vida_atual < vida_maxima else vida_atual
        nova_mana = min(mana_maxima, mana_atual + max(1, mana_maxima // 2)) if mana_atual < mana_maxima else mana_atual

        recuperou_vida = nova_vida - vida_atual
        recuperou_mana = nova_mana - mana_atual
        self._salvar(ctx, nova_vida, nova_mana)

        if recuperou_vida == 0 and recuperou_mana == 0:
            descricao = "✨ Você já está com Vida e Mana no máximo."
        else:
            vida_texto = f"+{recuperou_vida}" if recuperou_vida > 0 else "cheia"
            mana_texto = f"+{recuperou_mana}" if recuperou_mana > 0 else "cheia"
            descricao = (
                f"❤️ Vida: **{vida_texto}** ({nova_vida}/{vida_maxima})\n"
                f"💙 Mana: **{mana_texto}** ({nova_mana}/{mana_maxima})"
            )

        embed = discord.Embed(title=titulo, description=descricao, color=discord.Color.green())
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        await ctx.send(embed=embed)

    async def _registrar_comando(self, nome, callback, aliases):
        # Algumas versões anteriores do bot já registravam esses comandos em
        # outro módulo. Removemos o registro antigo antes de instalar a versão
        # corrigida, evitando CommandRegistrationError e mantendo um único dono.
        for nome_comando in [nome, *aliases]:
            self.bot.remove_command(nome_comando)

        comando = commands.Command(callback, name=nome, aliases=aliases)
        self.bot.add_command(comando)

    async def cog_load(self):
        async def descanso_callback(ctx):
            await self._recuperar(ctx, "😴 Descanso")

        async def meditacao_callback(ctx):
            await self._recuperar(ctx, "🧘 Meditação")

        await self._registrar_comando("descanso", descanso_callback, ["descansar", "rest"])
        await self._registrar_comando("meditacao", meditacao_callback, ["meditação", "meditar", "meditate"])


async def setup(bot):
    await bot.add_cog(Recuperacao(bot))
