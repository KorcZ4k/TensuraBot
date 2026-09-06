import math

import discord
from discord.ext import commands, tasks

from database.python.mongodb import db, run_db


CANAL_LEVEL_UP_ID = 1543041026158100480


def _processar_niveis():
    """Processa toda a varredura do Mongo em uma thread, nunca no event loop."""
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
        xp_maximo = int(jogador.get("XP_maximo", 100) or 100)
        subiu_nivel = False

        while xp_atual >= xp_maximo:
            xp_atual -= xp_maximo
            nivel_anterior = nivel_atual
            nivel_atual += 1
            xp_maximo = math.ceil(xp_maximo * 1.75)
            subiu_nivel = True
            level_ups.append((user_id, guild_id, nivel_anterior, nivel_atual))

        if subiu_nivel:
            jogadores.update_one(
                {"_id": jogador["_id"]},
                {"$set": {"XP": xp_atual, "Nivel": nivel_atual, "XP_maximo": xp_maximo}},
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
