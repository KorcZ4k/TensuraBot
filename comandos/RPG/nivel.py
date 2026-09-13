import math

import discord
from discord.ext import commands, tasks

from database.python.mongodb import db, run_db


CANAL_LEVEL_UP_ID = 1543041026158100480
TP_POR_NIVEL = 100
FATOR_XP_POR_NIVEL = 1.30


def _calcular_mana_por_magiculas(magiculas):
    return float(magiculas or 0) * 0.1


def _processar_niveis():
    """Sobe níveis; TP continua sendo ganho por nível e Mana acompanha Magiculas."""
    jogadores = db["Jogadores"]
    level_ups = []
    for jogador in jogadores.find({"Situação": "ativo"}):
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
            xp_maximo = math.ceil(xp_maximo * FATOR_XP_POR_NIVEL)
            level_ups.append((user_id, guild_id, nivel_anterior, nivel_atual))

        magiculas = float(jogador.get("Magiculas", 0) or 0)
        mana_maxima = _calcular_mana_por_magiculas(magiculas)
        mana_atual = min(float(jogador.get("Mana", 0) or 0), mana_maxima)

        if nivel_atual > nivel_inicial:
            quantidade_niveis = nivel_atual - nivel_inicial
            jogadores.update_one(
                {"_id": jogador["_id"]},
                {
                    "$set": {
                        "XP": xp_atual,
                        "Nivel": nivel_atual,
                        "XP_maximo": xp_maximo,
                        "Mana": mana_atual,
                        "Mana Total": mana_maxima,
                    },
                    "$inc": {"TP": quantidade_niveis * TP_POR_NIVEL},
                },
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

    def cog_unload(self):
        self.verificar_niveis.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.verificar_niveis.is_running():
            self.verificar_niveis.start()

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
        magiculas = None
        try:
            documento = db["Jogadores"].find_one({"ID": str(user_id), "guild_id": str(guild_id)})
            if documento:
                magiculas = float(documento.get("Magiculas", 0) or 0)
        except Exception:
            pass
        mana_maxima = _calcular_mana_por_magiculas(magiculas or 0)
        embed = discord.Embed(
            title="🎉 | Subiu de nível!",
            description=(
                f"{jogador} subiu de nível.\n\n"
                f"**{nivel_anterior} → {nivel_novo}**\n"
                f"✨ TP ganho: **+{(nivel_novo - nivel_anterior) * TP_POR_NIVEL}**\n"
                f"🔮 Mana máxima: **{mana_maxima:g}** (Magículas × 0,1)"
            ),
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        if membro is not None:
            embed.set_thumbnail(url=membro.display_avatar.url)
        await canal.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Nivel(bot))
