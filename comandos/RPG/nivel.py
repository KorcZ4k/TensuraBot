import math

import discord
from discord.ext import commands, tasks

from database.python.mongodb import db, run_db


CANAL_LEVEL_UP_ID = 1543041026158100480
ATRIBUTOS_POR_NIVEL = ("Força", "Defesa", "Velocidade", "Destreza", "Magia", "Sorte")


def _processar_niveis():
    """Processa a varredura do Mongo em uma thread e aplica o crescimento de nível."""
    jogadores = db["Jogadores"]
    jogadores_com_xp = jogadores.find({"Situação": "ativo"})
    level_ups = []

    for jogador in jogadores_com_xp:
        user_id = jogador.get("ID")
        guild_id = jogador.get("guild_id")
        if not user_id or not guild_id:
            continue

        xp_atual = int(jogador.get("XP", 0) or 0)
        nivel_atual = int(jogador.get("Nivel", 1) or 1)
        nivel_inicial = nivel_atual
        xp_maximo = int(jogador.get("XP_maximo", 100) or 100)

        while xp_atual >= xp_maximo:
            xp_atual -= xp_maximo
            nivel_anterior = nivel_atual
            nivel_atual += 1
            xp_maximo = math.ceil(xp_maximo * 1.75)
            level_ups.append((user_id, guild_id, nivel_anterior, nivel_atual))

        if nivel_atual > nivel_inicial:
            quantidade_niveis = nivel_atual - nivel_inicial
            atualizacoes = {
                "XP": xp_atual,
                "Nivel": nivel_atual,
                "XP_maximo": xp_maximo,
            }

            # Cada nível aumenta cada atributo existente em 10%, de forma
            # cumulativa. Ex.: 100 -> 110 -> 121.
            for atributo in ATRIBUTOS_POR_NIVEL:
                if atributo not in jogador:
                    continue
                valor = float(jogador.get(atributo, 0) or 0)
                for _ in range(quantidade_niveis):
                    valor *= 1.10
                atualizacoes[atributo] = max(1, math.floor(valor))

            jogadores.update_one(
                {"_id": jogador["_id"]},
                {"$set": atualizacoes},
            )
        else:
            jogadores.update_one(
                {"_id": jogador["_id"], "XP_maximo": {"$exists": False}},
                {"$set": {"XP_maximo": xp_maximo}},
            )

    return level_ups


class Nivel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.verificar_niveis.start()

    def cog_unload(self):
        self.verificar_niveis.cancel()

    @tasks.loop(seconds=5)
    async def verificar_niveis(self):
        level_ups = await run_db(_processar_niveis)
        for user_id, guild_id, nivel_anterior, nivel_novo in level_ups:
            await self._anunciar_level_up(user_id, guild_id, nivel_anterior, nivel_novo)

    async def _anunciar_level_up(self, user_id, guild_id, nivel_anterior, nivel_novo):
        canal = self.bot.get_channel(CANAL_LEVEL_UP_ID)
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(CANAL_LEVEL_UP_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return

        if str(canal.guild.id) != str(guild_id):
            return

        membro = canal.guild.get_member(int(user_id))
        jogador = membro.mention if membro is not None else f"<@{user_id}>"
        embed = discord.Embed(
            title="🎉 | Subiu de nível!",
            description=f"{jogador} subiu de nível.\n\n**{nivel_anterior} → {nivel_novo}**",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        if membro is not None:
            embed.set_thumbnail(url=membro.display_avatar.url)
        await canal.send(embed=embed)

    @verificar_niveis.before_loop
    async def antes_de_verificar_niveis(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Nivel(bot))
